from __future__ import annotations

import json
import logging
from typing import Any

from app.agent_runtime.agents.interface import BaseAgent
from app.agent_runtime.agents.model_factory import AgentModelConfig
from app.agent_runtime.agents.lifecycle import AgentLifecycle
from app.agent_runtime.events import AgentEvent
from app.agent_runtime.tools.base import ToolContext

logger = logging.getLogger(__name__)


class QwenPawTextAgent(BaseAgent):
    """QwenPaw-style agent with native LLM tool-calling via OpenAI-compatible API.

    When a model is configured, native function calling is used: tool schemas
    are converted to the OpenAI tools format, the LLM decides which tool(s) to
    call, we execute them through the tool/capability registry, feed the
    results back, and stream the final text response.

    When no model is configured (AgentModelConfig.is_configured is False), the
    agent falls back to JSON tool-call parsing from the last message.
    """

    def __init__(
        self,
        *,
        model_config: AgentModelConfig,
        system_prompt: str,
        workspace_context: dict[str, Any],
        tool_registry: Any,
        tool_context: ToolContext,
        capability_registry: Any | None = None,
        lifecycle: AgentLifecycle | None = None,
    ) -> None:
        self.model_config = model_config
        self.system_prompt = system_prompt
        self.workspace_context = workspace_context
        self.tool_registry = tool_registry
        self.capability_registry = capability_registry
        self.tool_context = tool_context
        self.lifecycle = lifecycle or AgentLifecycle()
        self._openai_tools_cache: list[dict[str, Any]] | None = None

    async def initialize(self) -> None:
        self.lifecycle.initialize()

    async def run(self, messages: list[dict[str, Any]]):
        async for event in self.reply_stream(messages):
            yield event

    async def close(self) -> None:
        self.lifecycle.close()

    async def reply_stream(self, messages: list[dict[str, Any]]):
        # --- JSON tool-call fallback (no model configured) ---
        if not self.model_config.is_configured:
            tool_call = self._parse_tool_call(messages)
            if tool_call is not None:
                async for event in self._execute_tool_json(tool_call[0], tool_call[1]):
                    yield event
                return
            yield AgentEvent("error", "No LLM configured and no JSON tool call found.")
            return

        # --- Native tool-calling path ---
        async for event in self._stream_with_native_tools(messages):
            yield event

    # ------------------------------------------------------------------
    # JSON tool-call fallback (kept for backward compatibility)
    # ------------------------------------------------------------------

    async def _execute_tool_json(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ):
        yield AgentEvent(
            "tool_call_start",
            metadata={"tool": tool_name, "arguments": arguments},
        )
        try:
            result = await self._execute_capability(tool_name, arguments)
        except Exception as exc:
            yield AgentEvent(
                "tool_error",
                content=str(exc) or exc.__class__.__name__,
                metadata={"tool": tool_name, "error_type": exc.__class__.__name__},
            )
            return
        yield AgentEvent(
            "tool_call_end",
            metadata={"tool": tool_name, "result": result},
        )
        yield json.dumps(result, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Native tool-calling via OpenAI-compatible API
    # ------------------------------------------------------------------

    async def _stream_with_native_tools(self, messages: list[dict[str, Any]]):
        client = self._build_client()
        provider_messages = self._provider_messages(messages)
        tools = self._get_openai_tools()

        kwargs: dict[str, Any] = {
            "model": self.model_config.model,
            "messages": provider_messages,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        stream = await client.chat.completions.create(**kwargs)

        tool_calls_by_index: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None
        text_parts: list[str] = []

        async for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            choice = choices[0]
            finish_reason = getattr(choice, "finish_reason", None) or finish_reason
            delta = getattr(choice, "delta", None) or {}

            # Collect tool calls from deltas
            tool_deltas = getattr(delta, "tool_calls", None) or []
            for td in tool_deltas:
                index = getattr(td, "index", 0)
                if index not in tool_calls_by_index:
                    tool_calls_by_index[index] = {
                        "id": getattr(td, "id", "") or "",
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

            # Collect text deltas
            content = getattr(delta, "content", None)
            if content:
                text_parts.append(str(content))
                yield AgentEvent("text_delta", str(content))

        # --- Execute tool calls if the model requested them ---
        if finish_reason == "tool_calls" and tool_calls_by_index:
            tool_call_items = sorted(tool_calls_by_index.items(), key=lambda x: x[0])
            tool_messages: list[dict[str, Any]] = []
            for _index, tc in tool_call_items:
                fn_name = tc["function"]["name"]
                try:
                    fn_args = json.loads(tc["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    fn_args = {}
                yield AgentEvent(
                    "tool_call_start",
                    metadata={"tool": fn_name, "arguments": fn_args},
                )
                try:
                    result = await self._execute_capability(fn_name, fn_args)
                except Exception as exc:
                    yield AgentEvent(
                        "tool_error",
                        content=str(exc) or exc.__class__.__name__,
                        metadata={"tool": fn_name, "error_type": exc.__class__.__name__},
                    )
                    result = {"error": str(exc)}
                yield AgentEvent(
                    "tool_call_end",
                    metadata={"tool": fn_name, "result": result},
                )
                tool_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                })

            # Continue: feed tool results back, get final response
            provider_messages.extend(tool_messages)
            followup_stream = await client.chat.completions.create(
                model=self.model_config.model,
                messages=provider_messages,
                stream=True,
            )
            async for chunk in followup_stream:
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                content = getattr(getattr(choices[0], "delta", None) or {}, "content", None)
                if content:
                    yield AgentEvent("text_delta", str(content))

    def _build_client(self) -> Any:
        try:
            from openai import AsyncOpenAI  # noqa: PLC0415
        except Exception as exc:  # pragma: no cover - depends on optional SDK
            raise RuntimeError("OpenAI-compatible SDK is not installed.") from exc

        kwargs: dict[str, Any] = {}
        if self.model_config.api_key:
            kwargs["api_key"] = self.model_config.api_key
        if self.model_config.effective_base_url:
            kwargs["base_url"] = self.model_config.effective_base_url
        return AsyncOpenAI(**kwargs)

    def _get_openai_tools(self) -> list[dict[str, Any]]:
        """Convert ToolRegistry schemas to OpenAI tools format, cached."""
        if self._openai_tools_cache is not None:
            return self._openai_tools_cache
        schemas: list[dict[str, Any]] = []
        if self.tool_registry is not None:
            schemas = self.tool_registry.schemas()
        tools: list[dict[str, Any]] = []
        for s in schemas:
            params = s.get("inputSchema", s.get("input_schema", {}))
            if not isinstance(params, dict):
                params = {"type": "object", "properties": {}}
            tools.append({
                "type": "function",
                "function": {
                    "name": s["name"],
                    "description": s.get("description", ""),
                    "parameters": params,
                },
            })
        self._openai_tools_cache = tools
        return tools

    def _provider_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        provider_messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt}
        ]
        workspace_hint = self._workspace_hint()
        if workspace_hint:
            provider_messages.append({"role": "system", "content": workspace_hint})
        for message in messages:
            role = str(message.get("role") or "user")
            if role not in {"system", "user", "assistant", "tool"}:
                role = "user"
            content = message_text(message)
            if content:
                provider_messages.append({"role": role, "content": content})
        return provider_messages

    def _workspace_hint(self) -> str:
        scenario_id = self.workspace_context.get("scenario_id") or ""
        user_id = self.workspace_context.get("user_id") or ""
        tool_names = self.workspace_context.get("tool_names") or []
        memory_summary = self.workspace_context.get("memory_summary") or ""
        if not scenario_id and not user_id and not tool_names and not memory_summary:
            return ""
        hint = (
            f"Workspace context: user_id={user_id}; scenario_id={scenario_id}; "
            f"tools={', '.join(tool_names)}."
        )
        if memory_summary:
            hint += f"\nMemory summary:\n{memory_summary}"
        return hint

    async def _execute_capability(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if self.capability_registry is not None:
            return await self.capability_registry.execute(name, arguments, self.tool_context)
        return await self.tool_registry.execute(name, arguments, self.tool_context)

    @staticmethod
    def _parse_tool_call(
        messages: list[dict[str, Any]],
    ) -> tuple[str, dict[str, Any]] | None:
        if not messages:
            return None
        text = message_text(messages[-1]).strip()
        if not text:
            return None
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        tool_name = payload.get("tool") or payload.get("tool_name")
        arguments = payload.get("arguments") or payload.get("args") or {}
        if not isinstance(tool_name, str) or not tool_name:
            return None
        arguments = arguments if isinstance(arguments, dict) else {}
        return tool_name, arguments


def message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text") or part.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    parts = message.get("parts")
    if isinstance(parts, list):
        text_parts: list[str] = []
        for part in parts:
            if isinstance(part, dict) and part.get("type") == "text":
                text = part.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
        return "\n".join(text_parts)
    return ""


def last_user_text(messages: list[dict[str, Any]]) -> str:
    if not messages:
        return ""
    return message_text(messages[-1])


__all__ = ["QwenPawTextAgent", "last_user_text", "message_text"]
