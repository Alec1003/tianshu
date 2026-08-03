from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

from app.agent_runtime.events import AgentEvent
from app.agent_runtime.runtime.envelope import Envelope, EnvelopeEvent
from app.agent_runtime.workflow.messages import AgentMessage
from app.agent_runtime.workflow.models import AgentTask, Workflow
from app.agent_runtime.workflow.state import WorkflowState
from app.agent_runtime.workflow.transitions import transition


class WorkflowOrchestrator:
    """QwenPaw-style foundation for dispatching tasks between registered agents."""

    def __init__(self) -> None:
        self._workflows: dict[str, Workflow] = {}

    def create_workflow(
        self,
        *,
        tasks: list[AgentTask] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Workflow:
        workflow = Workflow(
            tasks=list(tasks or []),
            metadata=dict(metadata or {}),
        )
        self._workflows[workflow.workflow_id] = workflow
        return workflow

    def get(self, workflow_id: str) -> Workflow:
        try:
            return self._workflows[workflow_id]
        except KeyError as exc:
            raise ValueError(f"Workflow not found: {workflow_id}") from exc

    def list_workflows(self) -> list[Workflow]:
        return list(self._workflows.values())

    async def run(
        self,
        *,
        request: Any,
        builder: Any,
        executor: Any,
        envelope: Envelope | None = None,
    ) -> AsyncGenerator[EnvelopeEvent, None]:
        workflow = self._workflow_from_request(request)
        workflow.state = transition(workflow.state, WorkflowState.RUNNING)
        normalizer = envelope or Envelope()
        yield EnvelopeEvent(
            "start",
            metadata={"workflow_id": workflow.workflow_id, "workflow_state": workflow.state.value},
        )
        try:
            for task in workflow.tasks:
                async for event in self.dispatch_task(
                    workflow=workflow,
                    task=task,
                    request=request,
                    builder=builder,
                    executor=executor,
                    envelope=normalizer,
                ):
                    yield event
                if task.status == WorkflowState.FAILED:
                    workflow.state = transition(workflow.state, WorkflowState.FAILED)
                    return
            workflow.state = transition(workflow.state, WorkflowState.COMPLETED)
            yield EnvelopeEvent(
                "finish",
                metadata={"workflow_id": workflow.workflow_id, "workflow_state": workflow.state.value},
            )
        except BaseException as exc:
            workflow.state = transition(workflow.state, WorkflowState.FAILED)
            yield EnvelopeEvent(
                "error",
                str(exc) or exc.__class__.__name__,
                {
                    "workflow_id": workflow.workflow_id,
                    "error_type": exc.__class__.__name__,
                },
            )

    async def dispatch_task(
        self,
        *,
        workflow: Workflow,
        task: AgentTask,
        request: Any,
        builder: Any,
        executor: Any,
        envelope: Envelope | None = None,
    ) -> AsyncGenerator[EnvelopeEvent, None]:
        registry = getattr(getattr(request, "workspace", None), "agent_registry", None)
        if registry is None:
            raise RuntimeError("Workflow execution requires workspace.agent_registry.")
        task.status = WorkflowState.RUNNING
        message = AgentMessage(
            sender="workflow",
            receiver=task.agent_name,
            content=self._task_content(task.input),
            metadata={"task_id": task.task_id, "workflow_id": workflow.workflow_id},
        )
        workflow.add_message(message)
        agent = await registry.create_agent(
            request=request,
            builder=builder,
            name=task.agent_name,
        )
        self._mark_agent_running(agent)
        normalizer = envelope or Envelope()
        output_parts: list[str] = []
        saw_error = False
        try:
            async for event in executor.run(agent, self._messages_for_task(request, task, message)):
                normalized = normalizer.from_agent_event(event)
                if normalized is None:
                    continue
                if normalized.type in {"start", "finish"}:
                    continue
                metadata = {
                    **normalized.metadata,
                    "workflow_id": workflow.workflow_id,
                    "task_id": task.task_id,
                    "agent_name": task.agent_name,
                }
                if normalized.type == "text":
                    output_parts.append(normalized.content)
                if normalized.type == "error":
                    saw_error = True
                    self._mark_agent_error(agent, RuntimeError(normalized.content))
                yield EnvelopeEvent(normalized.type, normalized.content, metadata)
            task.output = "".join(output_parts)
            task.status = WorkflowState.FAILED if saw_error else WorkflowState.COMPLETED
            if saw_error:
                return
            self._mark_agent_finished(agent)
            workflow.add_message(
                AgentMessage(
                    sender=task.agent_name,
                    receiver="workflow",
                    content=str(task.output or ""),
                    metadata={"task_id": task.task_id, "workflow_id": workflow.workflow_id},
                )
            )
        except BaseException as exc:
            task.output = str(exc) or exc.__class__.__name__
            task.status = WorkflowState.FAILED
            self._mark_agent_error(agent, exc)
            raise
        finally:
            await self._close_agent(agent)

    def _workflow_from_request(self, request: Any) -> Workflow:
        metadata = getattr(request, "metadata", {}) or {}
        workflow = metadata.get("workflow")
        if isinstance(workflow, Workflow):
            if workflow.workflow_id not in self._workflows:
                self._workflows[workflow.workflow_id] = workflow
            return workflow
        task_payloads = metadata.get("workflow_tasks")
        tasks = (
            [self._task_from_payload(payload) for payload in task_payloads]
            if isinstance(task_payloads, list)
            else [
                AgentTask(
                    task_id=str(uuid4()),
                    agent_name=str(metadata.get("agent_name") or "default"),
                    input=getattr(request, "messages", []) or [],
                )
            ]
        )
        return self.create_workflow(tasks=tasks, metadata={"request": metadata})

    @staticmethod
    def _task_from_payload(payload: Any) -> AgentTask:
        if isinstance(payload, AgentTask):
            return payload
        if not isinstance(payload, dict):
            raise TypeError("Workflow task payload must be an AgentTask or dict.")
        return AgentTask(
            task_id=str(payload.get("task_id") or uuid4()),
            agent_name=str(payload.get("agent_name") or "default"),
            input=payload.get("input"),
        )

    @staticmethod
    def _task_content(task_input: Any) -> str:
        if isinstance(task_input, str):
            return task_input
        return str(task_input)

    @staticmethod
    def _messages_for_task(
        request: Any,
        task: AgentTask,
        message: AgentMessage,
    ) -> list[dict[str, Any]]:
        if isinstance(task.input, list):
            return task.input
        if isinstance(task.input, dict):
            return [task.input]
        if task.input is None:
            return list(getattr(request, "messages", []) or [])
        return [
            {
                "role": "user",
                "content": message.content,
                "metadata": dict(message.metadata),
            }
        ]

    @staticmethod
    def _mark_agent_running(agent: Any) -> None:
        start = getattr(getattr(agent, "lifecycle", None), "start", None)
        if callable(start):
            start()

    @staticmethod
    def _mark_agent_finished(agent: Any) -> None:
        finish = getattr(getattr(agent, "lifecycle", None), "finish", None)
        if callable(finish):
            finish()

    @staticmethod
    def _mark_agent_error(agent: Any, error: BaseException) -> None:
        fail = getattr(getattr(agent, "lifecycle", None), "fail", None)
        if callable(fail):
            fail(error)

    @staticmethod
    async def _close_agent(agent: Any) -> None:
        close = getattr(agent, "close", None)
        if close is None:
            return
        result = close()
        if hasattr(result, "__await__"):
            await result


__all__ = ["WorkflowOrchestrator"]
