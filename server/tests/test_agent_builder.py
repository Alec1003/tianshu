from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent_runtime.agents import (
    AgentBuilder,
    AgentCreateSpec,
    AgentFactory,
    AgentModelConfig,
    ModelFactory,
    PromptBuilder,
    QWENPAW_TEXT_PROMPT,
    QwenPawTextAgent,
)
from app.agent_runtime.runtime import AgentRuntimeRequest


class FakeToolRegistry:
    def __init__(self) -> None:
        self.loaded_workspace = None

    async def load_driver_tools(self, workspace):
        self.loaded_workspace = workspace

    def schemas(self):
        return [
            {
                "name": "inspect_current_scenario",
                "description": "Inspect scenario",
                "inputSchema": {"type": "object", "properties": {}},
            }
        ]

    async def execute(self, *_args, **_kwargs):
        return {"ok": True}


@pytest.mark.asyncio
async def test_agent_builder_creates_agent_from_workspace_request():
    tools = FakeToolRegistry()
    workspace = SimpleNamespace(
        tool_registry=tools,
        skill_registry=object(),
        agent_prompt="",
    )
    request = AgentRuntimeRequest(
        messages=[{"role": "user", "content": "hello"}],
        user_id="user-a",
        scenario_id="scenario-a",
        workspace=workspace,
        tool_registry=tools,
        model={
            "provider": "qwen",
            "model": "qwen-plus",
            "apiKey": "sk-test",
        },
    )

    agent = await AgentBuilder().build(request)

    assert isinstance(agent, QwenPawTextAgent)
    assert agent.tool_registry is tools
    assert agent.tool_context.workspace is workspace
    assert tools.loaded_workspace is workspace


def test_prompt_builder_uses_workspace_prompt_and_context():
    request = SimpleNamespace(
        workspace=SimpleNamespace(agent_prompt="Base prompt"),
        prompt_context="Workspace Context\n- scenario: Alpha",
    )

    prompt = PromptBuilder().build(request)

    assert prompt.startswith("Base prompt")
    assert "Workspace Context" in prompt
    assert "scenario: Alpha" in prompt


def test_prompt_builder_falls_back_to_default_prompt():
    request = SimpleNamespace(workspace=SimpleNamespace(agent_prompt=""), prompt_context="")

    assert PromptBuilder().build(request) == QWENPAW_TEXT_PROMPT


def test_model_factory_prefers_request_override(monkeypatch):
    monkeypatch.setenv("TIANSHU_LLM_MODEL", "")
    from app.config import get_settings

    get_settings.cache_clear()
    config = ModelFactory().resolve(
        SimpleNamespace(
            model={
                "provider": "deepseek",
                "model": "deepseek-chat",
                "apiKey": "sk-test",
                "baseUrl": "",
            }
        )
    )

    assert config == AgentModelConfig(
        provider="deepseek",
        model="deepseek-chat",
        api_key="sk-test",
        base_url="",
    )
    get_settings.cache_clear()


def test_agent_factory_keeps_text_agent_compatibility():
    tools = FakeToolRegistry()
    builder = AgentBuilder()
    request = AgentRuntimeRequest(
        messages=[],
        user_id="user-a",
        workspace=SimpleNamespace(skill_registry=object()),
        tool_registry=tools,
        model={"provider": "qwen", "model": "qwen-plus", "apiKey": "sk-test"},
    )
    tool_context = builder.resolve_tool_context(request)
    agent = AgentFactory().create(
        AgentCreateSpec(
            model_config=AgentModelConfig("qwen", "qwen-plus", "sk-test", ""),
            system_prompt="prompt",
            workspace_context={"tool_names": ["inspect_current_scenario"]},
            tool_registry=tools,
            tool_context=tool_context,
        )
    )

    assert isinstance(agent, QwenPawTextAgent)
    assert agent.system_prompt == "prompt"
    assert agent.tool_registry is tools


def test_pydantic_backend_default_is_unchanged(monkeypatch):
    from app.api import ai as ai_api
    from app.config import get_settings

    monkeypatch.delenv("TIANSHU_AGENT_BACKEND", raising=False)
    get_settings.cache_clear()

    assert get_settings().agent_backend == "qwenpaw"
    get_settings.cache_clear()
