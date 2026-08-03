from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.agent_runtime.events import AgentEvent


EnvelopeEventType = Literal[
    "start",
    "text",
    "tool_call",
    "tool_result",
    "error",
    "finish",
]


@dataclass(frozen=True)
class EnvelopeEvent:
    """Transport-neutral runtime event emitted by the lifecycle orchestrator."""

    type: EnvelopeEventType
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_agent_event(self) -> AgentEvent:
        if self.type == "text":
            return AgentEvent("text_delta", self.content, self.metadata)
        if self.type == "tool_call":
            return AgentEvent("tool_call_start", self.content, self.metadata)
        if self.type == "tool_result":
            return AgentEvent("tool_call_end", self.content, self.metadata)
        if self.type == "finish":
            return AgentEvent("complete", self.content, self.metadata)
        return AgentEvent(self.type, self.content, self.metadata)  # type: ignore[arg-type]


class Envelope:
    """Normalize legacy executor events into runtime lifecycle events."""

    @staticmethod
    def from_agent_event(event: AgentEvent) -> EnvelopeEvent | None:
        if event.type == "start":
            return EnvelopeEvent("start", event.content, event.metadata)
        if event.type == "text_delta":
            return EnvelopeEvent("text", event.content, event.metadata)
        if event.type == "tool_call_start":
            return EnvelopeEvent("tool_call", event.content, event.metadata)
        if event.type == "tool_call_end":
            return EnvelopeEvent("tool_result", event.content, event.metadata)
        if event.type == "tool_error":
            return EnvelopeEvent("error", event.content, event.metadata)
        if event.type == "complete":
            return EnvelopeEvent("finish", event.content, event.metadata)
        if event.type == "error":
            return EnvelopeEvent("error", event.content, event.metadata)
        return None

    @staticmethod
    def error(error: BaseException) -> EnvelopeEvent:
        return EnvelopeEvent(
            "error",
            str(error) or error.__class__.__name__,
            {"error_type": error.__class__.__name__},
        )


__all__ = ["Envelope", "EnvelopeEvent", "EnvelopeEventType"]
