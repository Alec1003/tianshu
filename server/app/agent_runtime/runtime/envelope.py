from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from app.agent_runtime.events import AgentEvent
from app.agent_runtime.runtime.runtime_event import RuntimeEvent

EnvelopeEventType = Literal["start", "text", "tool_call", "tool_result", "error", "finish"]

@dataclass(frozen=True)
class EnvelopeEvent:
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
        return AgentEvent(self.type, self.content, self.metadata)


class Envelope:
    def __init__(self) -> None:
        self._state: str = "IDLE"

    @property
    def state(self) -> str:
        return self._state

    def from_runtime_event(self, event: RuntimeEvent) -> Optional[EnvelopeEvent]:
        if event.type == "text":
            self._state = "TEXT_STREAMING"
            return EnvelopeEvent("text", (event.payload or {}).get("text", ""), event.metadata)
        if event.type == "tool_call":
            self._state = "TOOL_RUNNING"
            return EnvelopeEvent("tool_call", (event.payload or {}).get("name", ""), {"arguments": (event.payload or {}).get("arguments", {}), "call_id": (event.payload or {}).get("call_id", "")})
        if event.type == "tool_result":
            self._state = "TEXT_STREAMING"
            return EnvelopeEvent("tool_result", (event.payload or {}).get("name", ""), {"result": (event.payload or {}).get("output", {}), "call_id": (event.payload or {}).get("call_id", "")})
        if event.type == "finish":
            self._state = "FINISHED"
            return EnvelopeEvent("finish", event.payload.get("finishReason", ""), event.metadata)
        if event.type == "error":
            self._state = "ERROR"
            return EnvelopeEvent("error", event.payload.get("errorText", ""), event.metadata)
        if event.type == "heartbeat":
            return None
        return None

    @staticmethod
    def from_agent_event(event: AgentEvent) -> EnvelopeEvent | None:
        if isinstance(event, RuntimeEvent):
            return Envelope().from_runtime_event(event)
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
        return EnvelopeEvent("error", str(error) or error.__class__.__name__, {"error_type": error.__class__.__name__})

__all__ = ["Envelope", "EnvelopeEvent", "EnvelopeEventType"]


