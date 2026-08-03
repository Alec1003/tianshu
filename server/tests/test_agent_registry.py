from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent_runtime.agents import (
    AgentBuilder,
    AgentLifecycleStatus,
    AgentModelConfig,
    AgentProfile,
    AgentRegistry,
    ModelFactory,
    PromptBuilder,
    QwenPawTextAgent,
)
from app.agent_runtime.runtime import AgentRuntimeRequest


class FakeToolRegistry:
    async def load_driver_tools(self, _workspace):
        return None

    def schemas(self):
        return [
            {
                "name": "inspect_current_scenario",
                "description": "Inspect scenario",
                "inputSchema": {"type": "object", "properties": {}},
            }
        ]


def test_agent_registry_register_get_and_list_agents():
    registry = AgentRegistry()
    profile = AgentProfile(
        name="commander",
        description="Tactical commander",
        system_prompt="Command prompt",
        tool_permissions={"inspect_current_scenario": "read"},
        memory_scope="scenario",
    )

    registry.register(profile)

    assert registry.get("commander") is profile
    assert registry.list_agents() == [profile]


@pytest.mark.asyncio
async def test_agent_registry_creates_agent_from_profile():
    registry = AgentRegistry()
    registry.register(
        AgentProfile(
            name="default",
            system_prompt="Registry prompt",
            model_config={
                "provider": "qwen",
                "model": "qwen-plus",
                "apiKey": "sk-test",
            },
        )
    )
    tools = FakeToolRegistry()
    workspace = SimpleNamespace(tool_registry=tools, skill_registry=object())
    request = AgentRuntimeRequest(
        messages=[{"role": "user", "content": "hello"}],
        user_id="user-a",
        scenario_id="scenario-a",
        workspace=workspace,
        tool_registry=tools,
    )

    agent = await registry.create_agent(
        request=request,
        builder=AgentBuilder(),
        name="default",
    )

    assert isinstance(agent, QwenPawTextAgent)
    assert agent.profile is registry.get("default")
    assert agent.system_prompt.startswith("Registry prompt")
    assert agent.lifecycle.status == AgentLifecycleStatus.INITIALIZED


def test_model_factory_uses_profile_model_when_request_has_no_override():
    profile = AgentProfile(
        name="default",
        model_config={
            "provider": "deepseek",
            "model": "deepseek-chat",
            "apiKey": "sk-profile",
        },
    )

    config = ModelFactory().resolve(SimpleNamespace(model={}), profile)

    assert config == AgentModelConfig(
        provider="deepseek",
        model="deepseek-chat",
        api_key="sk-profile",
        base_url="",
    )


def test_prompt_builder_uses_profile_prompt_before_workspace_prompt():
    request = SimpleNamespace(
        workspace=SimpleNamespace(agent_prompt="Workspace prompt"),
        prompt_context="Context block",
    )
    profile = AgentProfile(name="default", system_prompt="Profile prompt")

    prompt = PromptBuilder().build(request, profile)

    assert prompt.startswith("Profile prompt")
    assert "Context block" in prompt
