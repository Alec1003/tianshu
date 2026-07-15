from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai.bridge_registry import TianShuBridgeRegistry
from app.api.ai import router as ai_router
from app.auth.router import router as auth_router
from app.config import get_settings, validate_production_settings
from app.db.session import create_db_and_tables
from app.mcp.http_auth import BearerAuthASGI
from app.mcp.server import (
    mcp,
    set_shared_bridge_provider,
    set_shared_runtime,
    set_shared_runtime_provider,
)
from app.scenarios.router import router as scenarios_router
from app.scenarios.seed import seed_system_templates
from app.unit_assets.router import router as unit_assets_router
from app.unit_assets.seed import seed_system_unit_assets

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: DB schema + seed templates + MCP session manager.

    The MCP runtime intentionally piggy-backs on the FastAPI bridge:
    ``set_shared_runtime`` makes ``app.mcp.server.mcp_lifespan`` skip its
    own ``TianShuRuntime`` boot and reuse the one driving
    ``/api/ai/command``. That single shared instance is the whole reason
    HTTP-mounted MCP can let an external LLM see / mutate the same live
    scenario the browser front-end is looking at.

    Order matters:
        1. DB / templates (cheap, idempotent).
        2. Bridge registry construction -> owns per-user runtime sessions.
        3. ``set_shared_runtime_provider`` BEFORE opening
           ``mcp.session_manager.run()`` (mcp_lifespan reads the slot during
           enter).
        4. ``async with session_manager.run()`` starts MCP's task group;
           must wrap ``yield`` so it stays alive for the whole app lifetime.
    """
    await create_db_and_tables()
    try:
        await seed_system_templates()
    except Exception:
        logger.exception("seed_system_templates failed; continuing without templates")
    try:
        await seed_system_unit_assets()
    except Exception:
        logger.exception("seed_system_unit_assets failed; continuing without units")

    app.state.bridge_registry = TianShuBridgeRegistry.from_env()
    set_shared_bridge_provider(app.state.bridge_registry.get_bridge_for_user)
    set_shared_runtime_provider(app.state.bridge_registry.get_runtime_for_user)

    mcp.streamable_http_app()
    async with mcp.session_manager.run():
        logger.info("mcp.http: mounted at /api/mcp (per-user runtime registry)")
        yield
    set_shared_runtime_provider(None)
    set_shared_bridge_provider(None)
    set_shared_runtime(None)
    app.state.bridge_registry.clear()


def create_app() -> FastAPI:
    settings = get_settings()
    validate_production_settings(settings)
    app = FastAPI(
        title="天枢平台后端",
        version="0.2.0",
        description="FastAPI backend: AI skill bridge + user auth + scenario persistence + MCP HTTP transport (S1+S2+S3).",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(ai_router)
    app.include_router(auth_router)
    app.include_router(scenarios_router)
    app.include_router(unit_assets_router)

    app.mount("/api/mcp", BearerAuthASGI(mcp.streamable_http_app()))

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/doc/download/{filename}")
    async def download_doc(filename: str, scenario_id: str = "", doc_folder: str = ""):
        from pathlib import Path
        from fastapi.responses import FileResponse, JSONResponse
        folder = doc_folder or scenario_id
        doc_root = Path("/doc_output")
        filepath = doc_root / folder / filename if folder else doc_root / filename
        if not filepath.exists():
            return JSONResponse({"error": "File not found"}, status_code=404)
        return FileResponse(str(filepath), filename=filename)

    @app.get("/api/doc/list")
    async def list_docs(scenario_id: str = "", doc_folder: str = ""):
        from pathlib import Path
        from datetime import datetime
        folder = doc_folder or scenario_id
        doc_root = Path("/doc_output")
        target_dir = doc_root / folder if folder else doc_root
        if not target_dir.exists():
            return {"files": []}
        files = []
        for f in sorted(target_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if f.is_file():
                stat = f.stat()
                files.append({
                    "name": f.name,
                    "size_bytes": stat.st_size,
                    "size_kb": round(stat.st_size / 1024, 1),
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
        return {"files": files}

    @app.get("/api/doc/preview/{filename}")
    async def preview_doc(filename: str, scenario_id: str = ""):
        from pathlib import Path
        from fastapi.responses import JSONResponse
        from html import escape
        from docx import Document as DocxDocument
        doc_root = Path("/doc_output")
        filepath = doc_root / scenario_id / filename if scenario_id else doc_root / filename
        if not filepath.exists():
            return JSONResponse({"error": "File not found"}, status_code=404)
        try:
            doc = DocxDocument(str(filepath))
            html_parts = []
            for para in doc.paragraphs:
                text = escape(para.text)
                style = para.style.name if para.style else ""
                if style.startswith("Heading"):
                    level = style.replace("Heading ", "")
                    try:
                        hl = min(int(level), 6)
                    except ValueError:
                        hl = 1
                    html_parts.append(f"<h{hl}>{text}</h{hl}>")
                elif not text.strip():
                    html_parts.append("<p><br/></p>")
                else:
                    html_parts.append(f"<p>{text}</p>")
            for table in doc.tables:
                html_parts.append('<table class="doc-table">')
                for row in table.rows:
                    html_parts.append("<tr>")
                    for cell in row.cells:
                        html_parts.append(f"<td>{escape(cell.text)}</td>")
                    html_parts.append("</tr>")
                html_parts.append("</table>")
            return {"html": "\n".join(html_parts), "filename": filename, "pages": 1}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    return app


app = create_app()
