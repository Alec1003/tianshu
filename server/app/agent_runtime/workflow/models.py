from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from app.agent_runtime.workflow.messages import AgentMessage
from app.agent_runtime.workflow.state import WorkflowState


@dataclass
class AgentTask:
    task_id: str
    agent_name: str
    input: Any
    output: Any = None
    status: WorkflowState = WorkflowState.CREATED


@dataclass
class Workflow:
    workflow_id: str = field(default_factory=lambda: str(uuid4()))
    state: WorkflowState = WorkflowState.CREATED
    tasks: list[AgentTask] = field(default_factory=list)
    messages: list[AgentMessage] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_task(self, task: AgentTask) -> AgentTask:
        self.tasks.append(task)
        return task

    def add_message(self, message: AgentMessage) -> AgentMessage:
        self.messages.append(message)
        return message


__all__ = ["AgentTask", "Workflow"]
