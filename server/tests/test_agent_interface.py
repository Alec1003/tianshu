from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent_runtime.agents import (
    AgentBuilder,
    AgentCapability,
    AgentLifecycleStatus,
    AgentModelConfig,
    AgentProfile,
    AgentRegistry,
    BaseAgent,
    QwenPawTextAgent,
)
from app.agent_runtime.executor import AgentExecutor
from app.agent_runtime.runtime import AgentRuntimeRequest, TianShuRuntimeOrchestrator


class FakeToolRegistry:
    async def load_driver_tools(self, _workspace):
        return None

    def schemas(self):
        return []


class RecordingBuilder:
    def __init__(self, agent):
        self.agent = agent
        self.calls = 0

    async def build_with_profile(self, _request, _profile):
        self.calls += 1
        return self.agent


class TextOnlyAgent(BaseAgent):
    def __init__(self) -> None:
        self.initialized = False
        self.closed = False

    async def initialize(self) -> None:
        self.initialized = True

    async def run(self, _messages):
        yield "ok"

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_base_agent_lifecycle_contract():
    agent = TextOnlyAgent()

    await agent.initialize()
    output = [event async for event in agent.run([{"role": "user", "content": "hi"}])]
    await agent.close()

    assert agent.initialized is True
    assert output == ["ok"]
    assert agent.closed is True


def test_agent_profile_loads_role_capabilities_and_metadata():
    profile = AgentProfile(
        name="default",
        role="default_assistant",
        capabilities=[AgentCapability(name="text_chat")],
        metadata={"multi_agent_enabled": False},
    )

    assert profile.role == "default_assistant"
    assert profile.capabilities[0].name == "text_chat"
    assert profile.metadata["multi_agent_enabled"] is False


@pytest.mark.asyncio
async def test_agent_registry_register_profile_and_create_default_agent():
    registry = AgentRegistry()
    profile = AgentProfile(name="default", system_prompt="Prompt")
    agent = TextOnlyAgent()
    builder = RecordingBuilder(agent)

    registry.register_profile(profile)
    created = await registry.create_default_agent(
        request=SimpleNamespace(),
        builder=builder,
    )

    assert registry.get_profile("default") is profile
    assert created is agent
    assert builder.calls == 1


@pytest.mark.asyncio
async def test_default_qwenpaw_text_agent_matches_base_agent_interface():
    tools = FakeToolRegistry()
    workspace = SimpleNamespace(tool_registry=tools, skill_registry=object())
    request = AgentRuntimeRequest(
        messages=[],
        user_id="user-a",
        workspace=workspace,
        tool_registry=tools,
        model={"provider": "qwen", "model": "qwen-plus", "apiKey": "sk-test"},
    )

    agent = await AgentBuilder().build(request)

    assert isinstance(agent, BaseAgent)
    assert isinstance(agent, QwenPawTextAgent)
    assert agent.lifecycle.status == AgentLifecycleStatus.INITIALIZED
    assert agent.model_config == AgentModelConfig("qwen", "qwen-plus", "sk-test", "")


class SingleAgent:
    async def reply_stream(self, _messages):
        yield "single"


class SingleAgentRegistry:
    def __init__(self) -> None:
        self.calls = 0

    async def create_agent(self, *, request, builder, name="default"):
        self.calls += 1
        return SingleAgent()


@pytest.mark.asyncio
async def test_workflow_interface_does_not_affect_single_agent_mode():
    registry = SingleAgentRegistry()
    workflow = SimpleNamespace(calls=0)

    async def workflow_run(**_kwargs):
        workflow.calls += 1
        yield "unexpected"

    workflow.run = workflow_run
    workspace = SimpleNamespace(
        agent_registry=registry,
        workflow_orchestrator=workflow,
    )
    runtime = TianShuRuntimeOrchestrator(executor=AgentExecutor())

    events = [
        event
        async for event in runtime.run(
            AgentRuntimeRequest(
                messages=[{"role": "user", "content": "hi"}],
                user_id="user-a",
                workspace=workspace,
                metadata={
                    "workflow_enabled": False,
                    "workflow_tasks": [{"agent_name": "default", "input": "ignored"}],
                },
            )
        )
    ]

    assert [event.type for event in events] == ["start", "text", "finish"]
    assert events[1].content == "single"
    assert registry.calls == 1
    assert workflow.calls == 0
