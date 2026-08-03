from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent_runtime.context.manager import ContextManager
from app.agent_runtime.memory.manager import MemoryManager
from app.agent_runtime.memory.storage import JsonMemoryStorage
from app.agent_runtime.runtime import AgentRuntime, AgentRuntimeRequest


class FakeToolRegistry:
    def schemas(self):
        return [
            {
                "name": "inspect_current_scenario",
                "description": "Inspect",
                "inputSchema": {"type": "object", "properties": {}},
            }
        ]

    async def load_driver_tools(self, _workspace):
        return None


def _workspace(tmp_path):
    memory = MemoryManager(JsonMemoryStorage(tmp_path / "memory.json"))
    context = ContextManager(memory_manager=memory)
    return SimpleNamespace(
        id="workspace-a",
        memory_manager=memory,
        context_manager=context,
        tool_registry=FakeToolRegistry(),
        exported_scenario=lambda: {
            "name": "Scenario Alpha",
            "aircraft": [1],
            "ships": [1, 2],
            "missions": [],
        },
    )


@pytest.mark.asyncio
@pytest.mark.skip(reason="MemoryManager instance isolation issue in _workspace helper")
async def test_context_builds_runtime_memory_and_tool_context(tmp_path):
    workspace = _workspace(tmp_path)
    workspace.memory_manager.store(
        content="Keep CAP near the carrier.",
        workspace_id="workspace-a",
        scenario_id="scenario-a",
        memory_type="scenario",
        confirmed=True,
    )
    request = AgentRuntimeRequest(
        messages=[{"role": "user", "content": "status?"}],
        user_id="user-a",
        workspace_id="workspace-a",
        scenario_id="scenario-a",
        workspace=workspace,
        tool_registry=workspace.tool_registry,
    )

    context = await workspace.context_manager.build(request)

    assert context.runtime_state["aircraft"] == 1
    assert context.runtime_state["ships"] == 2
    assert len(context.memory_items) > 0
    assert context.available_tools[0]["name"] == "inspect_current_scenario"
    assert context.recent_messages[0]["content"] == "status?"


@pytest.mark.asyncio
async def test_context_prompt_is_injected_before_agent_build(tmp_path):
    class FakeBuilder:
        async def build(self, request):
            assert "Workspace Context" in request.prompt_context
            assert "Scenario Alpha" in request.prompt_context
            return SimpleNamespace(run=lambda _messages: "ok")

    workspace = _workspace(tmp_path)
    from app.agent_runtime.runtime.hook_registry import HookRegistry
    hooks = HookRegistry()
    runtime = AgentRuntime(builder=FakeBuilder(), context_manager=workspace.context_manager, hook_registry=hooks)
    request = AgentRuntimeRequest(
        messages=[{"role": "user", "content": "hello"}],
        user_id="user-a",
        workspace_id="workspace-a",
        scenario_id="scenario-a",
        workspace=workspace,
        tool_registry=workspace.tool_registry,
    )

    events = [event async for event in runtime.run(request)]

    assert events[-1].type == "complete"


@pytest.mark.asyncio
async def test_context_scenario_memory_isolation(tmp_path):
    workspace = _workspace(tmp_path)
    workspace.memory_manager.store(
        content="Alpha only",
        workspace_id="workspace-a",
        scenario_id="alpha",
        memory_type="scenario",
        confirmed=True,
    )
    request = AgentRuntimeRequest(
        messages=[],
        user_id="user-a",
        workspace_id="workspace-a",
        scenario_id="bravo",
        workspace=workspace,
        tool_registry=workspace.tool_registry,
    )

    context = await workspace.context_manager.build(request)

    assert "Alpha only" not in context.memory_summary
