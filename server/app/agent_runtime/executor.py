from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from app.agent_runtime.events import AgentEvent
from app.agent_runtime.runtime.runtime_event import RuntimeEvent

_HEARTBEAT_TICK = object()
HEARTBEAT_INTERVAL_SECONDS = 15.0


class AgentExecutor:
    """QwenPaw-style: drives agent.reply_stream() with heartbeat,
    translates all events to RuntimeEvent."""

    async def run(
        self,
        agent: Any,
        messages: list[dict[str, Any]],
    ) -> AsyncGenerator[RuntimeEvent, None]:
        try:
            async for event in self._stream_agent(agent, messages):
                if event is not None:
                    yield event
            yield RuntimeEvent.finish("stop")
        except asyncio.TimeoutError:
            yield RuntimeEvent.error(
                "AI response timed out. Please retry.",
                error_code="TimeoutError",
            )
            yield RuntimeEvent.finish("error")
        except Exception as exc:
            yield RuntimeEvent.error(
                str(exc) or exc.__class__.__name__,
                error_code=exc.__class__.__name__,
            )
            yield RuntimeEvent.finish("error")

    async def _stream_agent(
        self,
        agent: Any,
        messages: list[dict[str, Any]],
    ) -> AsyncGenerator[RuntimeEvent, None]:
        if not hasattr(agent, "reply_stream"):
            raise TypeError("Agent must expose reply_stream(messages).")
        stream = agent.reply_stream(messages)
        async for event in _iter_with_heartbeat(
            stream.__aiter__(),
            HEARTBEAT_INTERVAL_SECONDS,
        ):
            if event is _HEARTBEAT_TICK:
                yield RuntimeEvent.heartbeat()
                continue
            yield _to_runtime(event)


async def _iter_with_heartbeat(
    agent_iter: Any,
    heartbeat_interval: float,
) -> AsyncGenerator[Any, None]:
    pending: asyncio.Task | None = None
    while True:
        if pending is None:
            pending = asyncio.ensure_future(agent_iter.__anext__())
        done, _ = await asyncio.wait({pending}, timeout=heartbeat_interval)
        if not done:
            yield _HEARTBEAT_TICK
            continue
        try:
            event = pending.result()
        except StopAsyncIteration:
            return
        finally:
            pending = None
        yield event


def _to_runtime(event: Any) -> RuntimeEvent:
    if isinstance(event, RuntimeEvent):
        return event
    if isinstance(event, AgentEvent):
        return _from_agent_event(event)
    if isinstance(event, str):
        return RuntimeEvent.text(event)
    if isinstance(event, dict):
        et = event.get("type", "")
        if et in ("text_delta", "text"):
            return RuntimeEvent.text(event.get("content", "") or event.get("delta", ""))
        if et == "tool_call_start":
            meta = event.get("metadata", {}) or {}
            return RuntimeEvent.tool_call(meta.get("tool", ""), meta.get("arguments", {}))
        if et == "tool_call_end":
            meta = event.get("metadata", {}) or {}
            return RuntimeEvent.tool_result(meta.get("tool", ""), meta.get("result", {}))
        if et in ("complete", "finish"):
            return RuntimeEvent.finish()
        if et == "error":
            return RuntimeEvent.error(event.get("content", "unknown"))
    return RuntimeEvent.text(str(event))


def _from_agent_event(event: AgentEvent) -> RuntimeEvent:
    if event.type == "text_delta":
        return RuntimeEvent.text(event.content)
    if event.type == "tool_call_start":
        return RuntimeEvent.tool_call(
            event.metadata.get("tool", ""),
            event.metadata.get("arguments", {}),
        )
    if event.type == "tool_call_end":
        return RuntimeEvent.tool_result(
            event.metadata.get("tool", ""),
            event.metadata.get("result", {}),
        )
    if event.type == "complete":
        return RuntimeEvent.finish()
    if event.type == "error":
        return RuntimeEvent.error(event.content)
    if event.type == "start":
        return RuntimeEvent("text", payload={"text": ""})
    return RuntimeEvent.text(event.content)


__all__ = ["AgentExecutor", "_HEARTBEAT_TICK", "HEARTBEAT_INTERVAL_SECONDS"]
