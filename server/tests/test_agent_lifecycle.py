from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent_runtime.agents import (
    AgentLifecycle,
    AgentLifecycleStatus,
    AgentProfile,
)
from app.agent_runtime.events import AgentEvent
from app.agent_runtime.executor import AgentExecutor
from app.agent_runtime.runtime import AgentRuntimeRequest, TianShuRuntimeOrchestrator


def test_agent_lifecycle_status_transitions():
    lifecycle = AgentLifecycle()

    assert lifecycle.status == AgentLifecycleStatus.CREATED
    lifecycle.initialize()
    assert lifecycle.status == AgentLifecycleStatus.INITIALIZED
    lifecycle.start()
    assert lifecycle.status == AgentLifecycleStatus.RUNNING
    lifecycle.finish()
    assert lifecycle.status == AgentLifecycleStatus.FINISHED
    lifecycle.close()
    assert lifecycle.status == AgentLifecycleStatus.CLOSED


def test_agent_lifecycle_error_transition():
    lifecycle = AgentLifecycle()

    lifecycle.fail(RuntimeError("boom"))

    assert lifecycle.status == AgentLifecycleStatus.ERROR
    assert lifecycle.error == "boom"


class FakeRegistry:
    def __init__(self, agent):
        self.agent = agent
        self.created_name = ""

    async def create_agent(self, *, request, builder, name="default"):
        self.created_name = name
        return self.agent


class LifecycleAgent:
    def __init__(self) -> None:
        self.profile = AgentProfile(name="default")
        self.lifecycle = AgentLifecycle()
        self.lifecycle.initialize()

    async def reply_stream(self, _messages):
        yield "ok"

    async def close(self):
        self.lifecycle.close()


@pytest.mark.asyncio
async def test_runtime_gets_agent_from_workspace_registry_and_closes_it():
    agent = LifecycleAgent()
    workspace = SimpleNamespace(agent_registry=FakeRegistry(agent))
    runtime = TianShuRuntimeOrchestrator(executor=AgentExecutor())

    events = [
        event
        async for event in runtime.run(
            AgentRuntimeRequest(
                messages=[{"role": "user", "content": "hi"}],
                user_id="user-a",
                workspace=workspace,
                metadata={"agent_name": "default"},
            )
        )
    ]

    assert [event.type for event in events] == ["start", "text", "finish"]
    assert workspace.agent_registry.created_name == "default"
    assert agent.lifecycle.status == AgentLifecycleStatus.CLOSED


class ErrorAgent(LifecycleAgent):
    async def reply_stream(self, _messages):
        raise RuntimeError("agent failed")


@pytest.mark.asyncio
async def test_runtime_marks_agent_error_before_close_on_executor_error():
    agent = ErrorAgent()
    observed_statuses: list[AgentLifecycleStatus] = []

    class RecordingExecutor(AgentExecutor):
        async def run(self, agent, messages):
            async for event in super().run(agent, messages):
                if event.type == "error":
                    observed_statuses.append(agent.lifecycle.status)
                yield event

    workspace = SimpleNamespace(agent_registry=FakeRegistry(agent))
    runtime = TianShuRuntimeOrchestrator(executor=RecordingExecutor())

    events = [
        event
        async for event in runtime.run(
            AgentRuntimeRequest(messages=[], user_id="user-a", workspace=workspace)
        )
    ]

    assert [event.type for event in events] == ["start", "error"]
    assert observed_statuses == [AgentLifecycleStatus.RUNNING]
    assert agent.lifecycle.status == AgentLifecycleStatus.CLOSED
