from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent_runtime.agents import AgentLifecycle, AgentLifecycleStatus
from app.agent_runtime.events import AgentEvent
from app.agent_runtime.executor import AgentExecutor
from app.agent_runtime.runtime import AgentRuntimeRequest, TianShuRuntimeOrchestrator
from app.agent_runtime.workflow import (
    AgentMessage,
    AgentTask,
    WorkflowOrchestrator,
    WorkflowState,
)


class FakeAgent:
    def __init__(self, text: str = "done") -> None:
        self.lifecycle = AgentLifecycle()
        self.lifecycle.initialize()
        self.text = text
        self.received_messages = []

    async def reply_stream(self, messages):
        self.received_messages = messages
        yield self.text

    async def close(self):
        self.lifecycle.close()


class FakeAgentRegistry:
    def __init__(self, agent: FakeAgent) -> None:
        self.agent = agent
        self.created_agents: list[str] = []

    async def create_agent(self, *, request, builder, name="default"):
        self.created_agents.append(name)
        return self.agent


def test_workflow_create_and_message_transfer():
    orchestrator = WorkflowOrchestrator()
    task = AgentTask(task_id="task-1", agent_name="default", input="inspect")

    workflow = orchestrator.create_workflow(tasks=[task], metadata={"source": "test"})
    workflow.add_message(
        AgentMessage(sender="operator", receiver="default", content="inspect")
    )

    assert workflow.state == WorkflowState.CREATED
    assert workflow.tasks == [task]
    assert workflow.messages[0].receiver == "default"
    assert orchestrator.get(workflow.workflow_id) is workflow


@pytest.mark.asyncio
async def test_workflow_dispatches_task_and_updates_state():
    agent = FakeAgent("task result")
    registry = FakeAgentRegistry(agent)
    workspace = SimpleNamespace(agent_registry=registry)
    request = AgentRuntimeRequest(
        messages=[{"role": "user", "content": "original"}],
        user_id="user-a",
        workspace=workspace,
    )
    orchestrator = WorkflowOrchestrator()
    workflow = orchestrator.create_workflow(
        tasks=[AgentTask(task_id="task-1", agent_name="default", input="task input")]
    )

    events = [
        event
        async for event in orchestrator.run(
            request=SimpleNamespace(**{**request.__dict__, "metadata": {"workflow": workflow}}),
            builder=object(),
            executor=AgentExecutor(),
        )
    ]

    assert [event.type for event in events] == ["start", "text", "finish"]
    assert events[1].content == "task result"
    assert workflow.state == WorkflowState.COMPLETED
    assert workflow.tasks[0].status == WorkflowState.COMPLETED
    assert workflow.tasks[0].output == "task result"
    assert registry.created_agents == ["default"]
    assert agent.received_messages == [{"role": "user", "content": "task input", "metadata": {"task_id": "task-1", "workflow_id": workflow.workflow_id}}]
    assert agent.lifecycle.status == AgentLifecycleStatus.CLOSED
    assert workflow.messages[-1].sender == "default"
    assert workflow.messages[-1].receiver == "workflow"


class ErrorExecutor:
    async def run(self, _agent, _messages):
        yield AgentEvent("start")
        yield AgentEvent("error", "failed")


@pytest.mark.asyncio
async def test_workflow_failed_task_sets_failed_state():
    agent = FakeAgent()
    registry = FakeAgentRegistry(agent)
    workflow = WorkflowOrchestrator().create_workflow(
        tasks=[AgentTask(task_id="task-err", agent_name="default", input="fail")]
    )
    request = SimpleNamespace(
        workspace=SimpleNamespace(agent_registry=registry),
        metadata={"workflow": workflow},
        messages=[],
    )
    orchestrator = WorkflowOrchestrator()

    events = [
        event
        async for event in orchestrator.run(
            request=request,
            builder=object(),
            executor=ErrorExecutor(),
        )
    ]

    assert [event.type for event in events] == ["start", "error"]
    assert workflow.state == WorkflowState.FAILED
    assert workflow.tasks[0].status == WorkflowState.FAILED


@pytest.mark.asyncio
async def test_runtime_orchestrator_uses_workflow_only_when_enabled():
    agent = FakeAgent("workflow response")
    registry = FakeAgentRegistry(agent)
    workspace = SimpleNamespace(
        agent_registry=registry,
        workflow_orchestrator=WorkflowOrchestrator(),
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
                    "workflow_enabled": True,
                    "workflow_tasks": [
                        {
                            "task_id": "task-1",
                            "agent_name": "default",
                            "input": "workflow input",
                        }
                    ],
                },
            )
        )
    ]

    assert [event.type for event in events] == ["start", "text", "finish"]
    assert events[1].content == "workflow response"
    assert registry.created_agents == ["default"]
