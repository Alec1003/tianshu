from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from app.agent_runtime.agents.llm_adapter import LLMAdapter, LLMResponse
from app.agent_runtime.agents.tool_schema import ToolCallNormalizer
from app.agent_runtime.runtime.runtime_event import RuntimeEvent

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 12
MAX_TOTAL_SECONDS = 480.0
SUMMARY_TIMEOUT_SECONDS = 45.0

# When the LLM keeps calling tools without ever producing a natural-language
# summary (a common failure mode for some models), we synthesize a final
# user-facing answer from the tool results instead of leaving the user with an
# empty message. We first ask the LLM to summarise, and fall back to a compact
# extraction if that also fails.
SUMMARY_SYSTEM_PROMPT = (
    "你是一名战术推演助手。下面的工具已经执行完毕并产出了结果。"
    "请仅基于这些结果，用简体中文直接为用户生成最终答复。"
    "要求：\n"
    "1. 不要输出任何工具调用 JSON，也不要提及“工具调用”“以上结果”之类的元描述；\n"
    "2. 用清晰的条目或表格呈现关键结论（兵力、目标、方案对比、审批状态等）；\n"
    "3. 如果结果中包含待审批的提案，明确告知用户需要人工审批后才会生效；\n"
    "4. 语气专业、简洁。"
)

# Fields we try to pull readable content from when synthesising a fallback.
_READABLE_FIELDS = (
    "summary", "text", "message", "description", "content", "report",
    "brief", "result", "answer", "markdown",
)


class ToolLoop:

    def __init__(self, *, llm_adapter, capability_registry=None, tool_registry=None, tool_context=None):
        self.llm = llm_adapter
        self.capability_registry = capability_registry
        self.tool_registry = tool_registry
        self.tool_context = tool_context

    async def run(self, messages, tools=None):
        iteration = 0
        provider_messages = list(messages)
        start_ts = time.monotonic()
        executed: list[tuple[str, Any]] = []
        user_query = _last_user_text(messages)

        while iteration < MAX_TOOL_ITERATIONS:
            # Bail if we've spent too long overall — even a partial summary is
            # better than letting the user stare at "thinking" forever.
            if time.monotonic() - start_ts > MAX_TOTAL_SECONDS:
                logger.warning(
                    "ToolLoop hit MAX_TOTAL_SECONDS=%.1f after %d iterations",
                    MAX_TOTAL_SECONDS, iteration,
                )
                summary = await self._final_summary(executed, user_query, reason="timeout")
                yield RuntimeEvent.text(summary)
                yield RuntimeEvent.finish("timeout")
                return

            iteration += 1
            try:
                response = await self.llm.call(provider_messages, tools=tools)
            except asyncio.TimeoutError:
                logger.warning(
                    "ToolLoop LLM call timed out at iteration=%d; using fallback",
                    iteration,
                )
                summary = await self._final_summary(
                    executed, user_query, reason="llm_timeout"
                )
                yield RuntimeEvent.text(summary)
                yield RuntimeEvent.finish("timeout")
                return

            tool_calls = ToolCallNormalizer.from_response(response.tool_calls, response.text)
            if tool_calls and not response.tool_calls:
                logger.info("ToolLoop iteration=%d json_tools=%d", iteration, len(tool_calls))

            # Happy path: the model produced a final natural-language answer.
            if response.text and not tool_calls:
                yield RuntimeEvent.text(response.text)
                yield RuntimeEvent.finish()
                return

            # The model returned neither text nor tool calls — degenerate
            # response. Synthesise from whatever we already executed.
            if not tool_calls:
                logger.warning(
                    "ToolLoop iteration=%d: LLM returned empty (text=%r)",
                    iteration, (response.text or "")[:100],
                )
                summary = await self._final_summary(executed, user_query, reason="empty")
                yield RuntimeEvent.text(summary)
                yield RuntimeEvent.finish()
                return

            logger.info("ToolLoop iteration=%d tool_calls=%d", iteration, len(tool_calls))
            tool_messages = []

            for tc in tool_calls:
                call_id = tc.call_id or f"call_{uuid.uuid4().hex[:12]}"
                yield RuntimeEvent.tool_call(tc.name, tc.arguments, call_id=call_id)
                try:
                    result = await self._execute_tool(tc.name, tc.arguments)
                    result = await self._await_approval(result)
                except Exception as exc:  # noqa: BLE001
                    result = {"error": str(exc)}
                yield RuntimeEvent.tool_result(tc.name, result, call_id=call_id)
                executed.append((tc.name, result))
                tool_messages.append({
                    "role": "tool",
                    # Some OpenAI-compatible providers omit an id in a
                    # malformed/partial streamed tool call. Reuse the stable
                    # fallback id we exposed to the UI so the next model turn
                    # still has a valid tool-result correlation.
                    "tool_call_id": call_id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

            if response.tool_calls:
                provider_messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": response.tool_calls,
                })
            for tm in tool_messages:
                provider_messages.append(tm)
            continue

        logger.warning("ToolLoop hit MAX_TOOL_ITERATIONS=%d", MAX_TOOL_ITERATIONS)
        summary = await self._final_summary(executed, user_query, reason="max_iterations")
        yield RuntimeEvent.text(summary)
        yield RuntimeEvent.finish("max_iterations")

    # ------------------------------------------------------------------
    # Final-answer synthesis
    # ------------------------------------------------------------------

    async def _final_summary(
        self,
        executed: list[tuple[str, Any]],
        user_query: str,
        *,
        reason: str,
    ) -> str:
        """Produce a user-facing answer from executed tool results.

        Strategy: first ask the LLM to summarise (no tools), falling back to a
        compact extraction from the result payloads if that fails. Never returns
        an empty string.
        """
        if executed:
            prompt = self._build_summary_prompt(executed, user_query)
            try:
                summary_msgs = [
                    {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ]
                resp: LLMResponse = await asyncio.wait_for(
                    self.llm.call(summary_msgs, tools=None),
                    timeout=SUMMARY_TIMEOUT_SECONDS,
                )
                if resp.text and resp.text.strip():
                    return resp.text.strip()
                logger.warning("final summary LLM returned empty, using fallback")
            except BaseException as exc:  # noqa: BLE001
                logger.warning("final summary LLM failed (%s); using fallback", exc)

        return self._synthesize(executed, user_query, reason)

    def _build_summary_prompt(self, executed: list[tuple[str, Any]], user_query: str) -> str:
        parts: list[str] = []
        for idx, (name, result) in enumerate(executed, start=1):
            parts.append(f"{idx}. 工具 `{name}` 的结果：\n{_format_result(result)}")
        body = "\n\n".join(parts)
        header = f"用户原始问题：{user_query}\n\n" if user_query else ""
        return (
            f"{header}以下是已执行工具的结果：\n\n{body}\n\n"
            "请基于上述结果给出最终答复。"
        )

    def _synthesize(
        self,
        executed: list[tuple[str, Any]],
        user_query: str,
        reason: str,
    ) -> str:
        """Last-resort compact summary built directly from tool results."""
        if not executed:
            if reason in {"timeout", "llm_timeout"}:
                return "（操作耗时过长，已中止。请简化指令或稍后重试。）"
            if reason == "empty":
                return "（模型未返回有效内容，请重试或换一种表述。）"
            return "（未执行任何操作。）"

        lines = ["已完成以下操作，结果如下："]
        for idx, (name, result) in enumerate(executed, start=1):
            readable = _extract_readable(result)
            if readable:
                snippet = readable if len(readable) <= 600 else readable[:600] + "…"
                lines.append(f"{idx}. **{name}**：{snippet}")
            else:
                lines.append(f"{idx}. **{name}**：（结果无可读文本，详见工具返回数据）")
        lines.append("")
        lines.append("> 如需进一步推演或调整，请告诉我。")
        return "\n".join(lines)

    async def _execute_tool(self, name, arguments):
        if self.capability_registry is not None:
            try:
                return await self.capability_registry.execute(name, arguments, self.tool_context)
            except ValueError:
                logger.debug("CapabilityRegistry fallback to ToolRegistry for %s", name)
        if self.tool_registry is not None:
            return await self.tool_registry.execute(name, arguments, self.tool_context)
        raise ValueError(f"No registry for tool: {name}")

    async def _await_approval(self, result: Any) -> Any:
        """Suspend this turn at a human gate, then resume with execution data."""
        if not isinstance(result, dict) or not result.get("requiresApproval"):
            return result
        proposal_id = result.get("proposalId")
        queue = getattr(self.tool_context, "approval_queue", None)
        wait_for_resolution = getattr(queue, "wait_for_resolution", None)
        if not proposal_id or not callable(wait_for_resolution):
            return result

        # AgentExecutor emits heartbeat events while this await is pending, so
        # the SSE connection remains alive while the operator reviews the card.
        proposal = await wait_for_resolution(str(proposal_id))
        execution = [
            item.model_dump(mode="json") if hasattr(item, "model_dump") else item
            for item in (getattr(proposal, "execution", None) or [])
        ]
        return {
            "proposalId": str(proposal_id),
            "proposalStatus": getattr(proposal, "status", "unknown"),
            "requiresApproval": False,
            "approved": getattr(proposal, "status", "")
            in {"executed", "partial"},
            "execution": execution,
            "error": getattr(proposal, "error", None),
        }


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                texts = [
                    p.get("text") or p.get("content")
                    for p in content
                    if isinstance(p, dict)
                ]
                joined = "\n".join(t for t in texts if isinstance(t, str))
                if joined:
                    return joined
    return ""


def _format_result(result: Any, limit: int = 1200) -> str:
    if isinstance(result, dict):
        for field in _READABLE_FIELDS:
            val = result.get(field)
            if isinstance(val, str) and val.strip():
                return val if len(val) <= limit else val[:limit] + "…"
        if "error" in result:
            return f"（执行出错：{result['error']}）"
    if isinstance(result, str):
        return result if len(result) <= limit else result[:limit] + "…"
    text = json.dumps(result, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "…"


def _extract_readable(result: Any) -> str:
    if isinstance(result, dict):
        for field in _READABLE_FIELDS:
            val = result.get(field)
            if isinstance(val, str) and val.strip():
                return val.strip()
        if "error" in result:
            return f"（执行出错：{result['error']}）"
    if isinstance(result, str):
        return result.strip()
    return ""


__all__ = ["ToolLoop", "MAX_TOOL_ITERATIONS", "MAX_TOTAL_SECONDS"]
