from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent_runtime.agents import AgentBuilder
from app.agent_runtime.capabilities import Capability, CapabilityRegistry
from app.agent_runtime.context.manager import ContextManager
from app.agent_runtime.memory.manager import MemoryManager
from app.agent_runtime.runtime import AgentRuntimeRequest
from app.agent_runtime.tools.base import ToolContext


class InMemoryStorage:
    def __init__(self) -> None:
        self.items = []

    def list_items(self):
        return list(self.items)

    def save_items(self, items):
        self.items = list(items)


class FakeCapabilityAdapter:
    async def discover(self):
        return [
            Capability(
                name="inspect_current_scenario",
                description="Inspect scenario",
                source="skill",
                provider="tianshu",
                permission="read",
                input_schema={"type": "object", "properties": {}},
            )
        ]

    async def execute(self, capability, arguments, context: ToolContext):
        return {"ok": True, "capability": capability.name}


class FakeToolRegistry:
    async def load_driver_tools(self, _workspace):
        return None

    def schemas(self):
        return []


@pytest.mark.asyncio
async def test_context_contains_memory_runtime_and_capabilities():
    memory = MemoryManager(storage=InMemoryStorage())
    memory.store(
        content="remember the northern route",
        workspace_id="workspace-a",
        scenario_id="scenario-a",
        memory_type="scenario",
        confirmed=True,
        importance=0.9,
    )
    capabilities = CapabilityRegistry()
    capabilities.register(
        Capability(name="inspect_current_scenario", description="Inspect"),
        FakeCapabilityAdapter(),
    )
    workspace = SimpleNamespace(
        id="workspace-a",
        workspace_id="workspace-a",
        capability_registry=capabilities,
        tool_registry=FakeToolRegistry(),
        exported_scenario=lambda: {
            "currentScenario": {"name": "Alpha", "aircraft": [1], "ships": []}
        },
    )
    request = AgentRuntimeRequest(
        messages=[{"role": "user", "content": "route"}],
        user_id="user-a",
        workspace=workspace,
        scenario_id="scenario-a",
        capability_registry=capabilities,
    )

    context = await ContextManager(memory_manager=memory).build(request)

    assert context.runtime_state["scenarioName"] == "Alpha"
    assert "northern route" in context.memory_summary
    assert context.available_capabilities[0]["name"] == "inspect_current_scenario"
    assert "Available Capabilities" in context.to_prompt_context()


@pytest.mark.asyncio
async def test_agent_builder_injects_context_and_capabilities():
    capabilities = CapabilityRegistry()
    capabilities.register(
        Capability(name="inspect_current_scenario", description="Inspect"),
        FakeCapabilityAdapter(),
    )
    tools = FakeToolRegistry()
    workspace = SimpleNamespace(
        capability_registry=capabilities,
        tool_registry=tools,
        skill_registry=SimpleNamespace(capabilities=lambda: []),
    )
    request = AgentRuntimeRequest(
        messages=[],
        user_id="user-a",
        workspace=workspace,
        tool_registry=tools,
        capability_registry=capabilities,
        model={"provider": "qwen", "model": "qwen-plus", "apiKey": "sk-test"},
    )

    agent = await AgentBuilder().build(request)

    assert agent.capability_registry is capabilities
    assert "inspect_current_scenario" in agent.workspace_context["capability_names"]
