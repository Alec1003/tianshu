from __future__ import annotations

import json

import pytest

from app.ai.mcp_client import MCPClientSkeleton, MCPServerConfig


def test_external_mcp_servers_parse_from_json_config():
    raw = json.dumps(
        [
            {
                "name": "planner",
                "transport": "stdio",
                "command": "python",
                "args": ["-m", "external_planner"],
                "env": {"PLANNER_TOKEN": "secret"},
                "allowedTools": ["plan_route"],
            },
            {
                "name": "remote",
                "transport": "streamable-http",
                "url": "http://127.0.0.1:9000/mcp",
                "headers": {"Authorization": "Bearer secret"},
                "enabled": False,
            },
        ]
    )

    client = MCPClientSkeleton.from_env(raw)
    servers = client.list_servers()

    assert client.configuration_errors() == []
    assert [server.name for server in servers] == ["planner", "remote"]
    assert servers[0].transport == "stdio"
    assert servers[0].allowed_tools == ["plan_route"]
    assert servers[1].transport == "streamable_http"
    assert servers[1].url == "http://127.0.0.1:9000/mcp"
    assert servers[1].enabled is False


def test_server_summaries_do_not_expose_secrets():
    raw = json.dumps(
        [
            {
                "name": "remote",
                "transport": "http",
                "url": "http://127.0.0.1:9000/mcp",
                "headers": {"Authorization": "Bearer secret"},
            },
        ]
    )

    client = MCPClientSkeleton.from_env(raw)

    assert client.list_server_summaries() == [
        {
            "name": "remote",
            "transport": "streamable_http",
            "enabled": True,
            "url": "http://127.0.0.1:9000/mcp",
            "command": "",
            "allowedTools": [],
        }
    ]


def test_invalid_external_mcp_config_is_reported_not_raised():
    client = MCPClientSkeleton.from_env("{bad json")

    assert client.list_servers() == []
    assert "not valid JSON" in client.configuration_errors()[0]


@pytest.mark.asyncio
async def test_disabled_server_does_not_open_transport():
    client = MCPClientSkeleton()
    client.register_server(
        MCPServerConfig(
            name="planner",
            transport="stdio",
            command="python",
            enabled=False,
        )
    )

    traces, tools = await client.list_tools("planner")
    call_trace, result = await client.call_tool("planner", "plan_route", {})

    assert tools == []
    assert traces[0].status == "pending"
    assert call_trace.status == "pending"
    assert result == {}


@pytest.mark.asyncio
async def test_allowed_tools_gate_external_calls_before_transport():
    client = MCPClientSkeleton()
    client.register_server(
        MCPServerConfig(
            name="planner",
            transport="stdio",
            command="python",
            allowed_tools=["plan_route"],
        )
    )

    trace, result = await client.call_tool("planner", "allocate_weapon", {})

    assert trace.status == "error"
    assert "not allowed" in trace.message
    assert result == {}
