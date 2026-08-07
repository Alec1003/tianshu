from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

RuntimeEventType = Literal["text", "tool_call", "tool_result", "error", "finish", "heartbeat"]


@dataclass(frozen=True)
class RuntimeEvent:
    """Unified runtime event - mirrors QwenPaw FunctionCall/FunctionCallOutput.

    Internal fields follow QwenPaw convention:
      - call_id     -> unique tool call identifier
      - name        -> tool name
      - arguments   -> tool arguments
      - output      -> tool execution result

    ai_sdk_adapter normalizes these to AI SDK v5:
      - call_id     -> toolCallId
      - arguments   -> input
      - output      -> output
    """

    type: RuntimeEventType
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def text(cls, content: str, **_kw: Any) -> "RuntimeEvent":
        return cls("text", payload={"text": content})

    @classmethod
    def tool_call(cls, name: str, arguments: dict[str, Any] | None = None, *, call_id: str = "", **_kw: Any) -> "RuntimeEvent":
        return cls("tool_call", payload={"name": name, "arguments": arguments or {}, "call_id": call_id})

    @classmethod
    def tool_result(cls, name: str, output: Any, *, call_id: str = "", **_kw: Any) -> "RuntimeEvent":
        return cls("tool_result", payload={"name": name, "output": output, "call_id": call_id})

    @classmethod
    def error(cls, error_text: str, error_code: str = "error", *, call_id: str = "", tool_name: str = "", **_kw: Any) -> "RuntimeEvent":
        payload: dict[str, Any] = {"errorText": error_text, "errorCode": error_code}
        if call_id:
            payload["call_id"] = call_id
        if tool_name:
            payload["toolName"] = tool_name
        return cls("error", payload=payload)

    @classmethod
    def finish(cls, reason: str = "stop", **_kw: Any) -> "RuntimeEvent":
        return cls("finish", payload={"finishReason": reason})

    @classmethod
    def heartbeat(cls) -> "RuntimeEvent":
        return cls("heartbeat")


__all__ = ["RuntimeEvent", "RuntimeEventType"]
