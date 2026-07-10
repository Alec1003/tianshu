import asyncio
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from mcp.server import Server
from mcp.server.streamable_http import StreamableHTTPServerTransport
from mcp.types import (
    CallToolResult,
    ListResourcesResult,
    ListToolsResult,
    Resource,
    TextContent,
    Tool,
)
from starlette.applications import Starlette
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route
import anyio
import uvicorn

OUTPUT_DIR = Path("/output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

server = Server("doc-tools-mcp")


def _make_docx(title: str, sections: list[dict], output_path: str | Path) -> str:
    doc = Document()
    p = doc.add_heading(title, level=0)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph()
    for h in sections:
        level = h.get("level", 1)
        text = h.get("text", "")
        body = h.get("body", "")
        doc.add_heading(text, level=min(level, 4))
        for line in body.split("\n"):
            if line.strip():
                doc.add_paragraph(line.strip())
        doc.add_paragraph()
    filepath = Path(output_path)
    doc.save(str(filepath))
    return filepath.name


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="create_docx",
            description="Create a Word (.docx) document with structured content.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Document title."},
                    "sections": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string", "description": "Section heading."},
                                "level": {"type": "integer", "description": "Heading level 1-4.", "default": 1},
                                "body": {"type": "string", "description": "Body content."},
                            },
                            "required": ["text", "body"],
                        },
                    },
                    "filename": {"type": "string", "description": "Optional output filename."},
                },
                "required": ["title", "sections"],
            },
        ),
        Tool(
            name="save_file",
            description="Save any text content (markdown, code, JSON, etc.) to the AI_Output directory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Output filename with extension."},
                    "content": {"type": "string", "description": "Text content to save."},
                    "title": {"type": "string", "description": "Optional title for response."},
                },
                "required": ["filename", "content"],
            },
        ),
        Tool(
            name="list_documents",
            description="List previously generated documents and files.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
    if name == "create_docx":
        title = arguments.get("title", "Untitled")
        sections = arguments.get("sections", [])
        filename = arguments.get("filename")
        if not filename:
            safe_title = re.sub(r"[^一-鿿\w]", "_", title)[:20]
            now = datetime.now()
            ts = now.strftime("%Y%m%d_%H%M%S")
            filename = f"{safe_title}_{ts}.docx"
        output_path = OUTPUT_DIR / filename
        _make_docx(title, sections, output_path)
        size_kb = output_path.stat().st_size / 1024
        text = (
            f"? Word ??????????????\n"
            f"??????????????????????\n"
            f"???: {filename}\n"
            f"??: {title}\n"
            f"???: {len(sections)}\n"
            f"??: {size_kb:.1f} KB\n"
            f"????: AI_Output/{filename}\n"
            f"??????????????????????\n"
            f"????????????:\n"
            f"http://localhost:8000/api/doc/download/{filename}"
        )
        return CallToolResult(content=[TextContent(type="text", text=text)])
    elif name == "save_file":
        filename = arguments.get("filename", "unnamed.txt")
        content_str = arguments.get("content", "")
        title = arguments.get("title", "") or filename
        output_path = OUTPUT_DIR / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content_str, encoding="utf-8")
        size_kb = output_path.stat().st_size / 1024
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        labels = {"md": "Markdown", "json": "JSON", "txt": "Text", "py": "Python", "js": "JavaScript", "ts": "TypeScript", "html": "HTML", "css": "CSS", "yaml": "YAML", "yml": "YAML", "xml": "XML", "csv": "CSV", "log": "Log"}
        type_label = labels.get(ext, "File")
        text = (
            f"{type_label} saved: {filename}\n"
            f"Title: {title}\n"
            f"Size: {size_kb:.1f} KB\n"
            f"Saved to: AI_Output/{filename}\n"
            f"Download: http://localhost:8000/api/doc/download/{filename}"
        )
        return CallToolResult(content=[TextContent(type="text", text=text)])

    elif name == "list_documents":
        files = sorted(OUTPUT_DIR.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
        if not files:
            return CallToolResult(content=[TextContent(type="text", text="No documents generated.")])
        lines = ["### Generated documents"]
        for f in files:
            sz = f.stat().st_size / 1024
            mt = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            lines.append(f"- **{f.name}** ({sz:.1f} KB, {mt})")
        return CallToolResult(content=[TextContent(type="text", text="\n".join(lines))])
    else:
        return CallToolResult(content=[TextContent(type="text", text=f"Unknown tool: {name}")])


@server.list_resources()
async def list_resources() -> ListResourcesResult:
    files = sorted(OUTPUT_DIR.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
    resources = []
    for f in files:
        resources.append(Resource(
            uri=f"doc-tools://documents/{f.name}",
            name=f.name,
            description=f"Generated document ({f.stat().st_size / 1024:.1f} KB)",
            mimeType="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ))
    return ListResourcesResult(resources=resources)


async def main():
    transport = StreamableHTTPServerTransport(mcp_session_id=None)

    async def handle_mcp(request):
        await transport.handle_request(request.scope, request.receive, request._send)

    async def health(request):
        return JSONResponse({"status": "ok"})

    async def download_file(request):
        filename = request.path_params["filename"]
        filepath = OUTPUT_DIR / filename
        if filepath.exists():
            return FileResponse(
                str(filepath),
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                filename=filename,
            )
        return JSONResponse({"error": "File not found"}, status_code=404)

    app = Starlette(routes=[
        Route("/health", endpoint=health),
        Route("/", endpoint=handle_mcp, methods=["GET", "POST"]),
        Route("/download/{filename}", endpoint=download_file),
    ])

    async with transport.connect() as (read, write):
        async with anyio.create_task_group() as tg:
            tg.start_soon(server.run, read, write, server.create_initialization_options())
            config = uvicorn.Config(app, host="0.0.0.0", port=3010, log_level="info")
            server_uv = uvicorn.Server(config)
            await server_uv.serve()


if __name__ == "__main__":
    asyncio.run(main())
