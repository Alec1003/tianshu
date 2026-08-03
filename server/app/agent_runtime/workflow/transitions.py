from __future__ import annotations

from app.agent_runtime.workflow.state import WorkflowState


class WorkflowTransitionError(RuntimeError):
    """Raised when a workflow state transition is invalid."""


_ALLOWED_TRANSITIONS: dict[WorkflowState, set[WorkflowState]] = {
    WorkflowState.CREATED: {WorkflowState.RUNNING, WorkflowState.FAILED},
    WorkflowState.RUNNING: {
        WorkflowState.WAITING,
        WorkflowState.COMPLETED,
        WorkflowState.FAILED,
    },
    WorkflowState.WAITING: {WorkflowState.RUNNING, WorkflowState.COMPLETED, WorkflowState.FAILED},
    WorkflowState.COMPLETED: set(),
    WorkflowState.FAILED: set(),
}


def transition(current: WorkflowState, target: WorkflowState) -> WorkflowState:
    if current == target:
        return current
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise WorkflowTransitionError(
            f"Invalid workflow transition: {current.value} -> {target.value}"
        )
    return target


__all__ = ["WorkflowTransitionError", "transition"]
