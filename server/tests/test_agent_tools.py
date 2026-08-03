from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent_runtime.builder import AgentBuilder
from app.agent_runtime.executor import AgentExecutor
from app.agent_runtime.runtime import AgentRuntimeRequest
from app.agent_runtime.tools.base import ToolContext
from app.agent_runtime.tools.registry import ToolRegistry
from app.agent_runtime.tools.runtime_tools import RuntimeSkillTool


class FakeRegistry:
    def capabilities(self):
        return []


@pytest.mark.asyncio
async def test_agent_builder_loads_tools(monkeypatch):
    monkeypatch.setenv("TIANSHU_LLM_MODEL", "")
    from app.config import get_settings

    get_settings.cache_clear()
    workspace = SimpleNamespace(
        skill_registry=FakeRegistry(),
        exported_scenario=lambda: {"name": "Demo"},
    )

    agent = await AgentBuilder().build(
        AgentRuntimeRequest(
            messages=[],
            user_id="user-1",
            workspace=workspace,
            model={"provider": "ollama", "model": "llama3"},
        )
    )

    assert agent.tool_registry.has_tool("inspect_current_scenario")
    assert "inspect_current_scenario" in agent._workspace_hint()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_qwenpaw_agent_supports_tool_call():
    """JSON tool-call fallback path: no model configured, agent parses JSON from message."""
    from app.agent_runtime.agents.base import QwenPawTextAgent
    from app.agent_runtime.agents.model_factory import AgentModelConfig
    from app.agent_runtime.tools.base import ToolContext

    workspace = SimpleNamespace(
        exported_scenario=lambda: {"name": "Demo", "aircraft": [1, 2]},
    )
    registry = ToolRegistry()
    registry.register(
        RuntimeSkillTool(
            name="inspect_current_scenario",
            description="Inspect",
            input_schema={"type": "object", "properties": {}},
            readonly=True,
        )
    )
    agent = QwenPawTextAgent(
        model_config=AgentModelConfig(provider="", model="", api_key="", base_url=""),
        system_prompt="test",
        workspace_context={},
        tool_registry=registry,
        capability_registry=None,
        tool_context=ToolContext(
            workspace=workspace,
            skill_registry=None,
            user_id="user-1",
            scenario_id="scenario-1",
        ),
    )
    messages = [{"role": "user", "content": '{"tool":"inspect_current_scenario","arguments":{}}'}]
    events = [event async for event in AgentExecutor().run(agent, messages)]

    assert [event.type for event in events] == [
        "start",
        "tool_call_start",
        "tool_call_end",
        "text_delta",
        "complete",
    ]
    assert '"aircraft": 2' in events[3].content


@pytest.mark.asyncio
async def test_tool_error_is_reported_as_event():
    """JSON tool-call fallback: error when tool is not found."""
    from app.agent_runtime.agents.base import QwenPawTextAgent
    from app.agent_runtime.agents.model_factory import AgentModelConfig
    from app.agent_runtime.tools.base import ToolContext

    agent = QwenPawTextAgent(
        model_config=AgentModelConfig(provider="", model="", api_key="", base_url=""),
        system_prompt="test",
        workspace_context={},
        tool_registry=ToolRegistry(),
        capability_registry=None,
        tool_context=ToolContext(
            workspace=SimpleNamespace(),
            skill_registry=None,
            user_id="user-1",
            scenario_id="scenario-1",
        ),
    )
    messages = [{"role": "user", "content": '{"tool":"missing","arguments":{}}'}]
    events = [event async for event in AgentExecutor().run(agent, messages)]

    assert any(event.type == "tool_error" for event in events)


def test_backend_selector_default_is_qwenpaw(monkeypatch):
    from app.api import ai as ai_api
    from app.config import get_settings

    monkeypatch.delenv("TIANSHU_AGENT_BACKEND", raising=False)
    get_settings.cache_clear()

    assert get_settings().agent_backend == "qwenpaw"
    get_settings.cache_clear()


def test_skill_registry_still_uses_runtime_harness():
    from app.ai.skill_registry import TianShuSkillRegistry

    names = set(TianShuSkillRegistry.execute.__code__.co_names)
    assert {"harness", "execute"} <= names
