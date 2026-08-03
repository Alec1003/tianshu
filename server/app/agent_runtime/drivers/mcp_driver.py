from __future__ import annotations

from typing import Any

from app.agent_runtime.drivers.models import Capability
from app.ai.mcp_client import MCPClientSkeleton


class MCPDriver:
    """Driver wrapper around the legacy MCP client.

    Connection protocol support remains in ``MCPClientSkeleton``; this layer
    adds QwenPaw-style lifecycle and capability semantics for AgentRuntime.
    """

    name = "mcp"

    def __init__(self, *, client: MCPClientSkeleton) -> None:
        self.client = client
        self._capabilities: list[Capability] | None = None

    async def initialize(self) -> None:
        if self._capabilities is None:
            self._capabilities = await self._discover()

    async def capabilities(self) -> list[Capability]:
        await self.initialize()
        return list(self._capabilities or [])

    async def execute(
        self,
        capability: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        server, tool_name = _split_capability_name(capability)
        trace, result = await self.client.call_tool(server, tool_name, arguments or {})
        return {
            "ok": trace.status == "ok",
            "trace": trace.model_dump(mode="json"),
            "result": result,
        }

    async def close(self) -> None:
        self._capabilities = None

    async def _discover(self) -> list[Capability]:
        _traces, tools = await self.client.list_tools()
        return [
            Capability(
                name=_capability_name(str(tool.get("server") or ""), str(tool.get("name") or "")),
                description=str(tool.get("description") or ""),
                input_schema=_normalize_schema(tool.get("inputSchema") or {}),
                output_schema=tool.get("outputSchema") or {},
                source="driver",
                provider=self.name,
                permission=_permission_for_tool(tool),
                metadata={
                    "server": str(tool.get("server") or ""),
                    "tool_name": str(tool.get("name") or ""),
                },
            )
            for tool in tools
            if tool.get("server") and tool.get("name")
        ]


def _capability_name(server: str, tool_name: str) -> str:
    return f"mcp__{server.strip()}__{tool_name.strip()}"


def _split_capability_name(capability: str) -> tuple[str, str]:
    parts = capability.split("__", 2)
    if len(parts) == 3 and parts[0] == "mcp":
        return parts[1], parts[2]
    raise ValueError(f"Invalid MCP capability name: {capability}")


def _normalize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    if schema.get("type") == "object":
        return schema
    return {"type": "object", "properties": dict(schema)}


def _permission_for_tool(tool: dict[str, Any]) -> str:
    schema = tool.get("inputSchema") or {}
    annotations = tool.get("annotations") or {}
    if annotations.get("readOnlyHint") is True:
        return "read"
    name = str(tool.get("name") or "").lower()
    mutating_prefixes = ("create", "update", "delete", "save", "write", "set", "patch")
    if name.startswith(mutating_prefixes):
        return "write"
    if schema.get("x-tianshu-permission") in {"read", "write", "control"}:
        return schema["x-tianshu-permission"]
    return "read"
