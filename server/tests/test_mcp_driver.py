from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent_runtime.drivers.mcp_driver import MCPDriver
from app.agent_runtime.tools.base import ToolContext
from app.agent_runtime.tools.registry import ToolRegistry
from app.ai.models import CommandAdjudicationResult, MCPCallTrace


class FakeMCPClient:
    def __init__(self) -> None:
        self.calls = []

    async def list_tools(self, server_name=None):
        return (
            [
                MCPCallTrace(
                    action="list_tools",
                    target=server_name or "planner",
                    status="ok",
                    message="2 tools available",
                )
            ],
            [
                {
                    "server": "planner",
                    "name": "query_weather",
                    "description": "Query weather",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"area": {"type": "string"}},
                    },
                    "annotations": {"readOnlyHint": True},
                },
                {
                    "server": "planner",
                    "name": "save_plan",
                    "description": "Save plan",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                    },
                },
            ],
        )

    async def call_tool(self, server, tool_name, payload):
        self.calls.append((server, tool_name, payload))
        return (
            MCPCallTrace(
                action=f"call:{tool_name}",
                target=server,
                status="ok",
                message="ok",
            ),
            {"content": [{"type": "text", "text": "done"}]},
        )


class FakeApprovalQueue:
    def __init__(self) -> None:
        self.created = []

    def create_single_step_proposal(self, **kwargs):
        self.created.append(kwargs)
        return SimpleNamespace(
            id="proposal-1",
            status="pending",
            adjudication=CommandAdjudicationResult(summary="review"),
        )


class FakeDriverRegistry:
    def __init__(self, driver: MCPDriver) -> None:
        self.driver = driver

    async def capabilities(self):
        return await self.driver.capabilities()

    async def execute(self, _driver_name: str, capability: str, arguments: dict):
        return await self.driver.execute(capability, arguments)


@pytest.mark.asyncio
async def test_mcp_driver_can_initialize_and_discover_capabilities():
    driver = MCPDriver(client=FakeMCPClient())

    await driver.initialize()
    capabilities = await driver.capabilities()

    assert [cap.name for cap in capabilities] == [
        "mcp__planner__query_weather",
        "mcp__planner__save_plan",
    ]
    assert capabilities[0].readonly is True
    assert capabilities[1].permission == "write"


@pytest.mark.asyncio
async def test_mcp_driver_schema_conversion_and_execution():
    client = FakeMCPClient()
    driver = MCPDriver(client=client)

    capabilities = await driver.capabilities()
    result = await driver.execute(
        capabilities[0].name,
        {"area": "north"},
    )

    assert capabilities[0].input_schema["type"] == "object"
    assert result["ok"] is True
    assert client.calls == [("planner", "query_weather", {"area": "north"})]


@pytest.mark.asyncio
async def test_mcp_tool_readonly_executes_directly():
    client = FakeMCPClient()
    driver = MCPDriver(client=client)
    workspace = SimpleNamespace(driver_registry=FakeDriverRegistry(driver))
    registry = ToolRegistry()
    for capability in await driver.capabilities():
        if capability.readonly:
            from app.agent_runtime.tools.mcp_tools import MCPTool

            registry.register(MCPTool(capability))

    result = await registry.execute(
        "mcp__planner__query_weather",
        {"area": "north"},
        ToolContext(workspace=workspace, skill_registry=None),
    )

    assert result["ok"] is True
    assert client.calls == [("planner", "query_weather", {"area": "north"})]


@pytest.mark.asyncio
async def test_mcp_tool_write_enters_approval_queue():
    driver = MCPDriver(client=FakeMCPClient())
    capabilities = await driver.capabilities()
    write_capability = next(cap for cap in capabilities if not cap.readonly)
    from app.agent_runtime.tools.mcp_tools import MCPTool

    tool = MCPTool(write_capability)
    queue = FakeApprovalQueue()
    result = await tool.execute(
        {"name": "plan"},
        ToolContext(
            workspace=SimpleNamespace(driver_registry=SimpleNamespace()),
            skill_registry=None,
            approval_queue=queue,
            source_command="save plan",
        ),
    )

    assert result["proposalId"] == "proposal-1"
    assert result["requiresApproval"] is True
    assert queue.created[0]["skill"] == "mcp__planner__save_plan"


@pytest.mark.asyncio
async def test_tool_registry_loads_mcp_tools_from_workspace_driver():
    driver = MCPDriver(client=FakeMCPClient())
    workspace = SimpleNamespace(driver_registry=FakeDriverRegistry(driver), skill_registry=None)
    registry = ToolRegistry.from_workspace(workspace)

    await registry.load_driver_tools(workspace)

    assert registry.has_tool("mcp__planner__query_weather")
    assert registry.has_tool("mcp__planner__save_plan")
