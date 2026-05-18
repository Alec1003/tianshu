from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.ai.models import MCPCallTrace


@dataclass
class MCPServerConfig:
    """MCP server config placeholder.

    NOTE: This is intentionally a skeleton. Business logic should be implemented
    when external solver/services are integrated.
    """

    name: str
    transport: str = "stdio"
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = False


class MCPClientSkeleton:
    """OpenClaw MCP client integration skeleton.

    Keeps framework-level methods only. No domain-specific logic implemented.
    """

    def __init__(self) -> None:
        self._servers: dict[str, MCPServerConfig] = {}

    # ----------------------------- MCP extension area -----------------------------
    # Add server connection implementation in this section when integrating
    # external solver MCP endpoints.
    # -----------------------------------------------------------------------------
    def register_server(self, config: MCPServerConfig) -> None:
        self._servers[config.name] = config

    def list_servers(self) -> list[MCPServerConfig]:
        return list(self._servers.values())

    def call_tool(
        self, server_name: str, tool_name: str, payload: dict[str, Any] | None = None
    ) -> MCPCallTrace:
        if server_name not in self._servers:
            return MCPCallTrace(
                action=f"call:{tool_name}",
                target=server_name,
                status="error",
                message="MCP server not registered",
            )
        if not self._servers[server_name].enabled:
            return MCPCallTrace(
                action=f"call:{tool_name}",
                target=server_name,
                status="pending",
                message="MCP skeleton registered. Server runtime not enabled.",
            )
        return MCPCallTrace(
            action=f"call:{tool_name}",
            target=server_name,
            status="pending",
            message="MCP skeleton connected. Tool execution logic reserved.",
        )

