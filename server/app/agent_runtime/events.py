from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


AgentEventType = Literal[
    "start",
    "text_delta",
    "tool_call_start",
    "tool_call_end",
    "tool_error",
    "complete",
    "error",
]


@dataclass(frozen=True)
class AgentEvent:
    """Internal, transport-neutral agent event."""

    type: AgentEventType
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
