from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, AsyncIterator

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client

from app.ai.models import MCPCallTrace
from app.security.url_guard import normalize_and_validate_base_url

ENV_EXTERNAL_MCP_SERVERS = "AICC_EXTERNAL_MCP_SERVERS"
SUPPORTED_TRANSPORTS = {"stdio", "streamable_http"}


@dataclass
class MCPServerConfig:
    """Operator-managed external MCP server config.

    天枢平台 intentionally does not define weapon-allocation, path-planning, or
    other domain tools here. Those tools live in external MCP servers; this
    client only connects, lists, and calls them for the LLM agent.
    """

    name: str
    transport: str = "stdio"
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    allowed_tools: list[str] = field(default_factory=list)
    enabled: bool = True
    timeout_seconds: float = 30.0

    def normalized_transport(self) -> str:
        transport = self.transport.strip().lower().replace("-", "_")
        if transport in {"http", "streamablehttp"}:
            return "streamable_http"
        return transport


class MCPClientSkeleton:
    """Backwards-compatible external MCP client used by 天枢平台's LLM agent."""

    def __init__(self) -> None:
        self._servers: dict[str, MCPServerConfig] = {}
        self._config_errors: list[str] = []

    @classmethod
    def from_env(cls, raw: str | None = None) -> "MCPClientSkeleton":
        client = cls()
        raw_config = raw if raw is not None else os.environ.get(ENV_EXTERNAL_MCP_SERVERS, "")
        raw_config = raw_config.strip()
        if not raw_config:
            return client

        try:
            decoded = json.loads(raw_config)
        except json.JSONDecodeError as exc:
            client._config_errors.append(f"{ENV_EXTERNAL_MCP_SERVERS} is not valid JSON: {exc}")
            return client

        if not isinstance(decoded, list):
            client._config_errors.append(f"{ENV_EXTERNAL_MCP_SERVERS} must be a JSON array")
            return client

        for index, item in enumerate(decoded):
            if not isinstance(item, dict):
                client._config_errors.append(f"server[{index}] must be an object")
                continue
            try:
                client.register_server(_config_from_mapping(item))
            except ValueError as exc:
                client._config_errors.append(f"server[{index}]: {exc}")
        return client

    def register_server(self, config: MCPServerConfig) -> None:
        name = config.name.strip()
        if not name:
            raise ValueError("name is required")
        transport = config.normalized_transport()
        if transport not in SUPPORTED_TRANSPORTS:
            raise ValueError(f"unsupported transport: {config.transport}")
        if transport == "stdio" and not config.command.strip():
            raise ValueError("stdio transport requires command")
        if transport == "streamable_http":
            if not config.url.strip():
                raise ValueError("streamable_http transport requires url")
            raw_url = config.url.strip()
            config.url = normalize_and_validate_base_url(
                config.url,
                allow_private_network=True,
            )
            if raw_url.endswith("/") and not config.url.endswith("/"):
                config.url += "/"
        config.name = name
        config.transport = transport
        config.allowed_tools = [tool.strip() for tool in config.allowed_tools if tool.strip()]
        self._servers[name] = config

    def list_servers(self) -> list[MCPServerConfig]:
        return list(self._servers.values())

    def list_server_summaries(self) -> list[dict[str, Any]]:
        return [
            {
                "name": server.name,
                "transport": server.normalized_transport(),
                "enabled": server.enabled,
                "url": server.url if server.normalized_transport() == "streamable_http" else "",
                "command": server.command if server.normalized_transport() == "stdio" else "",
                "allowedTools": list(server.allowed_tools),
            }
            for server in self.list_servers()
        ]

    def configuration_errors(self) -> list[str]:
        return list(self._config_errors)

    async def list_tools(
        self, server_name: str | None = None
    ) -> tuple[list[MCPCallTrace], list[dict[str, Any]]]:
        targets = self._resolve_targets(server_name)
        traces: list[MCPCallTrace] = []
        tools: list[dict[str, Any]] = []
        for target_name, server in targets:
            if server is None:
                traces.append(
                    MCPCallTrace(
                        action="list_tools",
                        target=target_name,
                        status="error",
                        message="MCP server not registered",
                    )
                )
                continue
            if not server.enabled:
                traces.append(
                    MCPCallTrace(
                        action="list_tools",
                        target=server.name,
                        status="pending",
                        message="MCP server disabled",
                    )
                )
                continue
            try:
                async with asyncio.timeout(server.timeout_seconds):
                    async with self._session(server) as session:
                        result = await session.list_tools()
                server_tools = []
                allowed = set(server.allowed_tools)
                for tool in getattr(result, "tools", []):
                    dumped = _dump_model(tool)
                    name = str(dumped.get("name") or "")
                    if allowed and name not in allowed:
                        continue
                    server_tools.append(
                        {
                            "server": server.name,
                            "name": name,
                            "description": dumped.get("description") or "",
                            "inputSchema": dumped.get("inputSchema") or {},
                        }
                    )
                tools.extend(server_tools)
                traces.append(
                    MCPCallTrace(
                        action="list_tools",
                        target=server.name,
                        status="ok",
                        message=f"{len(server_tools)} tools available",
                    )
                )
            except Exception as exc:
                traces.append(
                    MCPCallTrace(
                        action="list_tools",
                        target=server.name,
                        status="error",
                        message=str(exc),
                    )
                )
        return traces, tools

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        payload: dict[str, Any] | None = None,
    ) -> tuple[MCPCallTrace, dict[str, Any]]:
        server = self._servers.get(server_name.strip())
        action = f"call:{tool_name}"
        if server is None:
            return (
                MCPCallTrace(
                    action=action,
                    target=server_name,
                    status="error",
                    message="MCP server not registered",
                ),
                {},
            )
        if not server.enabled:
            return (
                MCPCallTrace(
                    action=action,
                    target=server.name,
                    status="pending",
                    message="MCP server disabled",
                ),
                {},
            )
        if server.allowed_tools and tool_name not in set(server.allowed_tools):
            return (
                MCPCallTrace(
                    action=action,
                    target=server.name,
                    status="error",
                    message="MCP tool is not allowed for this server",
                ),
                {},
            )

        try:
            async with asyncio.timeout(server.timeout_seconds):
                async with self._session(server) as session:
                    result = await session.call_tool(
                        tool_name,
                        payload or {},
                        read_timeout_seconds=timedelta(seconds=server.timeout_seconds),
                    )
            dumped = _dump_model(result)
            is_error = bool(dumped.get("isError"))
            return (
                MCPCallTrace(
                    action=action,
                    target=server.name,
                    status="error" if is_error else "ok",
                    message="MCP tool returned error" if is_error else "MCP tool call succeeded",
                ),
                dumped,
            )
        except Exception as exc:
            return (
                MCPCallTrace(
                    action=action,
                    target=server.name,
                    status="error",
                    message=str(exc),
                ),
                {},
            )

    def _resolve_targets(
        self, server_name: str | None
    ) -> list[tuple[str, MCPServerConfig | None]]:
        if server_name and server_name.strip():
            key = server_name.strip()
            return [(key, self._servers.get(key))]
        return [(server.name, server) for server in self.list_servers()]

    @asynccontextmanager
    async def _session(self, server: MCPServerConfig) -> AsyncIterator[ClientSession]:
        if server.normalized_transport() == "stdio":
            params = StdioServerParameters(
                command=server.command,
                args=server.args,
                env=server.env or None,
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session
            return

        async with streamablehttp_client(
            server.url,
            headers=server.headers or None,
            timeout=server.timeout_seconds,
            sse_read_timeout=max(server.timeout_seconds, 300),
        ) as (read, write, _get_session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


def _config_from_mapping(raw: dict[str, Any]) -> MCPServerConfig:
    name = str(raw.get("name") or "").strip()
    transport = str(raw.get("transport") or "stdio")
    command = str(raw.get("command") or "")
    url = str(raw.get("url") or raw.get("baseUrl") or "")
    args = _string_list(raw.get("args"))
    env = _string_dict(raw.get("env"))
    headers = _string_dict(raw.get("headers"))
    allowed_tools = _string_list(raw.get("allowedTools") or raw.get("allowed_tools"))
    enabled = _bool_value(raw.get("enabled"), default=True)
    timeout_seconds = _float_value(raw.get("timeoutSeconds") or raw.get("timeout_seconds"), default=30.0)
    return MCPServerConfig(
        name=name,
        transport=transport,
        command=command,
        args=args,
        env=env,
        url=url,
        headers=headers,
        allowed_tools=allowed_tools,
        enabled=enabled,
        timeout_seconds=max(1.0, timeout_seconds),
    )


def _dump_model(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if isinstance(value, dict):
        return value
    return {"value": repr(value)}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    raise ValueError("expected a list of strings")


def _string_dict(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("expected an object")
    return {str(key): str(val) for key, val in value.items() if str(key).strip()}


def _bool_value(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _float_value(value: Any, *, default: float) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("timeoutSeconds must be a number") from exc
