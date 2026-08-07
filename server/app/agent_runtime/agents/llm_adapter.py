from __future__ import annotations

import json
import logging
import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)
# Plan generation can involve a long streamed tool-selection response.
LLM_CALL_TIMEOUT_SECONDS = 240.0


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = "stop"
    streamed: bool = False


class LLMAdapter:
    """Unified LLM caller with stream-first then non-stream fallback for tools."""

    def __init__(
        self,
        model_config: Any,
    ) -> None:
        self.model_config = model_config
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from openai import AsyncOpenAI  # noqa: PLC0415
        except Exception as exc:
            raise RuntimeError("OpenAI-compatible SDK is not installed.") from exc
        kwargs: dict[str, Any] = {}
        if self.model_config.api_key:
            kwargs["api_key"] = self.model_config.api_key
        if self.model_config.effective_base_url:
            kwargs["base_url"] = self.model_config.effective_base_url
        self._client = AsyncOpenAI(**kwargs)
        return self._client

    async def call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        if tools:
            return await self._call_with_tools(messages, tools)
        return await self._call_stream(messages)

    async def _call_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        # Phase 1: streaming attempt
        stream_resp = await self._call_stream(
            messages, tools=tools, tool_choice="auto"
        )
        if stream_resp.tool_calls:
            logger.debug(
                "LLMAdapter: streaming returned %d tool_calls",
                len(stream_resp.tool_calls),
            )
            return stream_resp

        if stream_resp.text.strip():
            # A streamed text response is already a complete assistant turn.
            # Calling the provider a second time creates duplicate answers and
            # makes long tool turns look interrupted in the UI.
            return stream_resp

        # Phase 2: non-streaming fallback
        try:
            nonstream_resp = await self._call_nonstream(
                messages, tools=tools, tool_choice="auto"
            )
            if nonstream_resp.tool_calls:
                logger.info(
                    "LLMAdapter: non-stream fallback returned %d tool_calls",
                    len(nonstream_resp.tool_calls),
                )
                return nonstream_resp
            logger.debug("LLMAdapter: non-stream fallback returned text only")
            return nonstream_resp
        except Exception as exc:
            logger.warning(
                "LLMAdapter: non-stream fallback failed (%s), using stream text",
                exc,
            )
            return stream_resp

    async def _call_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
    ) -> LLMResponse:
        client = self._ensure_client()
        kwargs: dict[str, Any] = {
            "model": self.model_config.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        async with asyncio.timeout(LLM_CALL_TIMEOUT_SECONDS):
            stream = await client.chat.completions.create(**kwargs)
            return await self._consume_stream(stream, tools=tools)

    async def _consume_stream(self, stream: Any, *, tools: list[dict[str, Any]] | None) -> LLMResponse:
        text_parts: list[str] = []
        tool_calls_by_index: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None

        async for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            choice = choices[0]
            finish_reason = getattr(choice, "finish_reason", None) or finish_reason
            delta = getattr(choice, "delta", None) or {}

            for td in getattr(delta, "tool_calls", None) or []:
                index = getattr(td, "index", 0)
                if index not in tool_calls_by_index:
                    tool_calls_by_index[index] = {
                        "id": getattr(td, "id", "") or "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    }
                tc = tool_calls_by_index[index]
                if getattr(td, "id", None):
                    tc["id"] = td.id
                fn = getattr(td, "function", None)
                if fn is not None:
                    if getattr(fn, "name", None):
                        tc["function"]["name"] += fn.name
                    if getattr(fn, "arguments", None):
                        tc["function"]["arguments"] += fn.arguments

            content = getattr(delta, "content", None)
            if content:
                text_parts.append(str(content))

        tool_calls = _normalize_tool_calls(tool_calls_by_index)
        return LLMResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            finish_reason=finish_reason or "stop",
            streamed=True,
        )

    async def _call_nonstream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
    ) -> LLMResponse:
        client = self._ensure_client()
        kwargs: dict[str, Any] = {
            "model": self.model_config.model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        async with asyncio.timeout(LLM_CALL_TIMEOUT_SECONDS):
            response = await client.chat.completions.create(**kwargs)
        choice = (getattr(response, "choices", None) or [None])[0]
        if choice is None:
            return LLMResponse(text="", finish_reason="stop")

        message = getattr(choice, "message", None) or {}
        text = getattr(message, "content", "") or ""
        finish_reason = getattr(choice, "finish_reason", None) or "stop"

        raw_tool_calls = getattr(message, "tool_calls", None) or []
        tool_calls: list[dict[str, Any]] = []
        for tc in raw_tool_calls:
            fn = getattr(tc, "function", None)
            tool_calls.append({
                "id": getattr(tc, "id", "") or "",
                "type": "function",
                "function": {
                    "name": getattr(fn, "name", "") if fn else "",
                    "arguments": getattr(fn, "arguments", "{}") if fn else "{}",
                },
            })

        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            streamed=False,
        )


def _normalize_tool_calls(
    by_index: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        by_index[i]
        for i in sorted(by_index)
        if by_index[i]["function"]["name"].strip()
    ]


__all__ = ["LLMAdapter", "LLMResponse", "LLM_CALL_TIMEOUT_SECONDS"]
