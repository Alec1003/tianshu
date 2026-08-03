from __future__ import annotations

from enum import Enum


class WorkflowState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"


__all__ = ["WorkflowState"]
