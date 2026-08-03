from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentLifecycleStatus(str, Enum):
    CREATED = "created"
    INITIALIZED = "initialized"
    RUNNING = "running"
    FINISHED = "finished"
    ERROR = "error"
    CLOSED = "closed"


@dataclass
class AgentLifecycle:
    """Track a single agent instance lifecycle."""

    status: AgentLifecycleStatus = AgentLifecycleStatus.CREATED
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def initialize(self) -> None:
        self.status = AgentLifecycleStatus.INITIALIZED
        self.error = ""

    def start(self) -> None:
        self.status = AgentLifecycleStatus.RUNNING
        self.error = ""

    def finish(self) -> None:
        self.status = AgentLifecycleStatus.FINISHED

    def fail(self, error: BaseException | str) -> None:
        self.status = AgentLifecycleStatus.ERROR
        self.error = str(error)

    def close(self) -> None:
        self.status = AgentLifecycleStatus.CLOSED


__all__ = ["AgentLifecycle", "AgentLifecycleStatus"]
