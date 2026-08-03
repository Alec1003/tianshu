from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterable, AsyncGenerator

from app.agent_runtime.events import AgentEvent
from app.agent_runtime.runtime.envelope import EnvelopeEvent


AI_SDK_STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "x-vercel-ai-ui-message-stream": "v1",
}


async def to_ai_sdk_stream(
    events: AsyncIterable[AgentEvent | EnvelopeEvent],
) -> AsyncGenerator[str, None]:
    """Convert internal events to AI SDK v5 UI message SSE text parts."""
    message_id = f"msg_{uuid.uuid4().hex}"
    text_id = f"text_{uuid.uuid4().hex}"
    text_started = False

    async for event in events:
        if event.type == "start":
            yield _sse({"type": "start", "messageId": message_id})
            yield _sse({"type": "text-start", "id": text_id})
            text_started = True
        elif event.type in {"text_delta", "text"}:
            if not text_started:
                yield _sse({"type": "start", "messageId": message_id})
                yield _sse({"type": "text-start", "id": text_id})
                text_started = True
            yield _sse({"type": "text-delta", "id": text_id, "delta": event.content})
        elif event.type in {"complete", "finish"}:
            if text_started:
                yield _sse({"type": "text-end", "id": text_id})
            yield _sse({"type": "finish"})
        elif event.type == "error":
            yield _sse(
                {
                    "type": "error",
                    "errorText": event.content,
                    "metadata": event.metadata,
                }
            )


def _sse(payload: dict) -> str:
    return "data: " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n\n"
