from __future__ import annotations

import inspect
from collections.abc import AsyncGenerator
from typing import Any

from app.agent_runtime.events import AgentEvent


class AgentExecutor:
    """Run an agent and convert its native output into internal events."""

    async def run(
        self,
        agent: Any,
        messages: list[dict[str, Any]],
    ) -> AsyncGenerator[AgentEvent, None]:
        yield AgentEvent("start")
        try:
            async for event in self._stream_agent(agent, messages):
                yield event
            yield AgentEvent("complete")
        except Exception as exc:
            yield AgentEvent(
                "error",
                content=str(exc) or exc.__class__.__name__,
                metadata={"error_type": exc.__class__.__name__},
            )

    async def _stream_agent(
        self,
        agent: Any,
        messages: list[dict[str, Any]],
    ) -> AsyncGenerator[AgentEvent, None]:
        if hasattr(agent, "reply_stream"):
            stream = agent.reply_stream(messages)
            async for event in stream:
                normalized = self._event(event)
                if normalized is not None:
                    yield normalized
            return

        if hasattr(agent, "run"):
            result = agent.run(messages)
            if inspect.isawaitable(result):
                result = await result
            normalized = self._event(result)
            if normalized is not None:
                yield normalized
            return

        raise TypeError("Agent must expose reply_stream(messages) or run(messages).")

    @staticmethod
    def _event(event: Any) -> AgentEvent | None:
        if isinstance(event, AgentEvent):
            return event
        if isinstance(event, str):
            return AgentEvent("text_delta", content=event)
        if isinstance(event, dict):
            event_type = event.get("type")
            if event_type in {"tool_call_start", "tool_call_end", "tool_error"}:
                return AgentEvent(
                    event_type,
                    content=str(event.get("content") or ""),
                    metadata=dict(event.get("metadata") or {}),
                )
            value = (
                event.get("delta")
                or event.get("content")
                or event.get("text")
                or event.get("output")
                or ""
            )
            return AgentEvent("text_delta", content=value) if isinstance(value, str) else None
        for attr in ("delta", "content", "text", "output"):
            value = getattr(event, attr, None)
            if isinstance(value, str):
                return AgentEvent("text_delta", content=value)
        return None
