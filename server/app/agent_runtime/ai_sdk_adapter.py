from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator, AsyncIterable
from typing import Any

from app.agent_runtime.events import AgentEvent
from app.agent_runtime.runtime.envelope import EnvelopeEvent
from app.agent_runtime.runtime.runtime_event import RuntimeEvent

logger = logging.getLogger(__name__)

AI_SDK_STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "x-vercel-ai-ui-message-stream": "v1",
}

# Emit an SSE comment (":" prefix) every N seconds so the browser doesn't
# time out the stream while a long tool loop is running in the backend.
HEARTBEAT_INTERVAL = 15.0


async def to_ai_sdk_stream(
    events: AsyncIterable[AgentEvent | EnvelopeEvent | RuntimeEvent],
) -> AsyncGenerator[str, None]:
    """Stream events progressively as AI SDK v5 SSE.

    Tool events are *surfaced as visible text* — the LLM drives the tool loop
    on the backend, and each tool call + its result is rendered inline in the
    chat so the user can see what the assistant did and the tool's output.

    The output shape is:
        start
        [heartbeat comments while waiting for first text]
        text-start (on first text chunk)
        text-delta * (streamed as they come)
        text-end + finish (when the runtime reports completion)

    If an error event arrives, its message is appended to the text stream.

    The upstream event stream is consumed *directly* (no intermediate queue /
    pump task) to avoid a race where a queued text event could be dropped
    before the consumer reads it under certain scheduling timings.

    IMPORTANT: the event-dispatch block below MUST stay *outside* the
    `try/finally` that wraps the `wait_for(__anext__())` call. It must only
    run when `item` was successfully fetched — never when `wait_for` raised
    (TimeoutError / StopAsyncIteration), because in that case `item` would
    still hold the previous event and re-dispatching it would loop forever.
    """
    message_id = f"msg_{uuid.uuid4().hex}"
    text_id = f"text_{uuid.uuid4().hex}"

    # 1) Emit start immediately so the SSE response body starts streaming.
    yield _sse({"type": "start", "messageId": message_id})

    text_open = False
    finished = False
    finished_reason = "stop"

    ait = events.__aiter__()
    pending: asyncio.Future | None = None
    while True:
        # Wait for the next upstream event WITHOUT cancelling the generator.
        # Cancelling `ait.__anext__()` mid-flight (e.g. via wait_for timeout)
        # can corrupt the async generator and truncate long tool loops, so we
        # keep the pending task alive across heartbeat ticks until it resolves.
        if pending is None:
            pending = asyncio.ensure_future(ait.__anext__())
        done, _ = await asyncio.wait({pending}, timeout=HEARTBEAT_INTERVAL)
        if not done:
            # No event for HEARTBEAT_INTERVAL — keep the SSE connection alive.
            yield _sse_comment("heartbeat")
            continue
        try:
            item = pending.result()
        except StopAsyncIteration:
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning("ai_sdk_stream: upstream stream ended (%s)", exc)
            if not text_open:
                yield _sse({"type": "text-start", "id": text_id})
                text_open = True
            yield _sse({
                "type": "text-delta",
                "id": text_id,
                "delta": f"\n[错误] {_friendly_error(exc)}",
            })
            finished_reason = "error"
            break
        pending = None

        # ---- event dispatch: runs ONLY when `item` was fetched cleanly ----
        etype = _normalize_type(_event_type(item))

        # ---- error tuple from a broken upstream (defensive) ----
        if isinstance(item, tuple) and item and item[0] == "__error__":
            err = item[1]
            if not text_open:
                yield _sse({"type": "text-start", "id": text_id})
                text_open = True
            yield _sse(
                {"type": "text-delta", "id": text_id, "delta": f"\n[异常] {err}"}
            )
            break

        # ---- text: stream as a single text block ----
        if etype == "text":
            content = _extract_text(item) or ""
            if content:
                if not text_open:
                    yield _sse({"type": "text-start", "id": text_id})
                    text_open = True
                yield _sse(
                    {"type": "text-delta", "id": text_id, "delta": content}
                )
            continue

        # ---- tool events: expose as structured AI SDK tool parts ----
        if etype in {"tool_call", "tool_result"}:
            if etype == "tool_call":
                name, arguments, call_id = _extract_tool_call_info(item)
                yield _sse({
                    "type": "tool-input-start",
                    "toolCallId": call_id,
                    "toolName": name,
                })
                yield _sse({
                    "type": "tool-input-available",
                    "toolCallId": call_id,
                    "toolName": name,
                    "input": arguments,
                })
            else:
                name, output, call_id = _extract_tool_result_info(item)
                yield _sse({
                    "type": "tool-output-available",
                    "toolCallId": call_id,
                    "output": output,
                })
            continue

        # ---- error: surface to the user as text ----
        if etype == "error":
            err = _extract_error(item) or "Unknown error"
            if not text_open:
                yield _sse({"type": "text-start", "id": text_id})
                text_open = True
            yield _sse(
                {"type": "text-delta", "id": text_id, "delta": f"\n[错误] {err}"}
            )
            continue

        # ---- finish: close the text block, emit finish ----
        if etype == "finish":
            finished = True
            finished_reason = _extract_finish_reason(item) or "stop"
            break

    # 2) Close text block + emit finish
    if not text_open:
        # The LLM produced no text (e.g. hit MAX_TOOL_ITERATIONS without
        # summarising). Emit an empty text block so AI SDK closes cleanly.
        yield _sse({"type": "text-start", "id": text_id})
        text_open = True
    yield _sse({"type": "text-end", "id": text_id})
    yield _sse(
        {"type": "finish", "finishReason": finished_reason}
        if finished
        else {"type": "finish"}
    )


# ------------------------------------------------------------------
# Event extraction helpers
# ------------------------------------------------------------------


def _event_type(event: Any) -> str:
    if isinstance(event, RuntimeEvent):
        return event.type
    return getattr(event, "type", "") or ""


# AgentEvent uses "text_delta" / "complete" / "start" types;
# RuntimeEvent uses "text" / "finish" / "error" types.
# Normalize them to a single canonical set so the main loop is uniform.
_TYPE_ALIASES = {
    "text_delta": "text",
    "complete": "finish",
}


def _normalize_type(etype: str) -> str:
    return _TYPE_ALIASES.get(etype, etype)


def _extract_text(event: Any) -> str:
    if isinstance(event, RuntimeEvent):
        if event.type == "text":
            return (event.payload or {}).get("text", "") or ""
        return ""
    etype = getattr(event, "type", "")
    if etype in {"text_delta", "text"}:
        return getattr(event, "content", "") or ""
    return ""


def _friendly_error(error: BaseException) -> str:
    """Never expose a blank/raw asyncio TimeoutError to the chat UI."""
    if isinstance(error, asyncio.TimeoutError):
        return "AI response timed out. Please retry; the server kept the connection alive while waiting."
    return str(error) or error.__class__.__name__


def _extract_error(event: Any) -> str | None:
    if isinstance(event, RuntimeEvent):
        if event.type == "error":
            return (event.payload or {}).get("errorText", "Unknown error")
        return None
    if getattr(event, "type", "") == "error":
        return getattr(event, "content", "") or str(event)
    return None


def _extract_finish_reason(event: Any) -> str:
    if isinstance(event, RuntimeEvent):
        return (event.payload or {}).get("finishReason", "stop")
    return getattr(event, "content", "") or "stop"


def _extract_tool_call_info(event: Any) -> tuple[str, Any, str]:
    if isinstance(event, RuntimeEvent):
        payload = event.payload or {}
        return payload.get("name", ""), payload.get("arguments", {}), payload.get("call_id", "")
    if isinstance(event, EnvelopeEvent):
        return event.content or "", (event.metadata or {}).get("arguments", {}), (event.metadata or {}).get("call_id", "")
    return "", {}, ""


def _extract_tool_result_info(event: Any) -> tuple[str, Any, str]:
    if isinstance(event, RuntimeEvent):
        payload = event.payload or {}
        return payload.get("name", ""), payload.get("output", {}), payload.get("call_id", "")
    if isinstance(event, EnvelopeEvent):
        return event.content or "", (event.metadata or {}).get("result", {}), (event.metadata or {}).get("call_id", "")
    return "", {}, ""


def _summarize_tool_call(name: str, arguments: Any) -> str:
    """Build a one-line human-readable tool-call summary (no raw JSON)."""
    args = arguments if isinstance(arguments, dict) else {}

    # --- doc-tools ---
    if name == "doc-tools":
        rt = args.get("report_type", "situation")
        label = {"situation": "态势报告", "summary": "战况摘要", "brief": "战术简报"}.get(rt, rt)
        title = args.get("title", "")
        fmt = args.get("format", "docx")
        parts = [f"📄 正在生成{label}"]
        if title:
            parts.append(f"「{title}」")
        parts.append(f"（格式：{fmt}）")
        return "".join(parts)

    # --- inspection tools ---
    if name == "inspect_current_scenario":
        return "🔍 正在查看当前场景…"
    if name == "list_runtime_tools":
        return "🔧 正在获取可用工具列表…"

    # --- scenario loaders ---
    if name in ("load_scenario_snapshot", "load_scenario_file", "load_scenario_json"):
        return f"📂 正在加载场景…"

    # --- tactical plans ---
    if name == "propose_tactical_plan_options":
        return "🎯 正在生成战术方案…"

    # --- generic write action ---
    safe_args = {k: v for k, v in args.items() if k != "project_id"}
    if safe_args:
        brief = ", ".join(f"{k}={str(v)[:40]}" for k, v in list(safe_args.items())[:3])
        return f"🔧 正在调用 `{name}`（{brief}）"
    return f"🔧 正在调用 `{name}`"


def _summarize_tool_result(name: str, output: Any) -> str:
    """Build a one-line human-readable result summary (no raw JSON)."""
    out = output if isinstance(output, dict) else {}

    # --- doc-tools ---
    if name == "doc-tools":
        pid = out.get("proposalId") or out.get("proposal_id", "")
        status = out.get("proposalStatus") or out.get("proposal_status", "")
        adj = out.get("adjudication") or {}
        if adj.get("status") == "needs_review":
            return f"✅ 已提交审批提案 `{pid[:8]}…`，请批准后生成文件"
        if status == "executed":
            return "✅ 文档已生成并保存到当前项目的 AI_Output 文档中心"
        return f"✅ 提案 `{pid[:8]}…` 状态：{status}"

    # --- inspection ---
    if name == "inspect_current_scenario":
        ok = out.get("ok", out)
        counts = out.get("counts", {})
        if isinstance(counts, dict) and counts:
            brief = f"场景「{out.get('scenarioName', out.get('scenarioId', '?'))}」：实体 {sum(counts.values())} 个"
            return f"✅ {brief}"
        return "✅ 已获取当前场景"

    # --- proposals (generic write tools) ---
    pid = out.get("proposalId") or out.get("proposal_id", "")
    if pid:
        status = out.get("proposalStatus") or out.get("proposal_status", "")
        adj = out.get("adjudication") or {}
        if not adj or adj.get("status") != "blocked":
            return f"✅ 已提交提案 `{pid[:8]}…`，等待审批"
        issues = adj.get("issues", [])
        first_msg = (issues[0].get("message", "") if issues else str(adj))[:80]
        return f"⚠️ 提案被拒绝：{first_msg}"

    # --- fallback: very short summary ---
    if isinstance(out, dict):
        keys = [k for k in out if k not in ("scenario", "rawScenario", "scenarioJson", "trace", "result")]
        if keys:
            brief_k = keys[0]
            brief_v = str(out.get(brief_k))[:60]
            return f"✅ {brief_k}={brief_v}"
    if isinstance(out, (list,)):
        return f"✅ 返回 {len(out)} 项"
    if isinstance(out, str):
        return f"✅ {out[:100]}"
    return "✅ 完成"


def _format_tool_event(event: Any) -> str:
    """Render a tool_call / tool_result event as a concise one-liner."""
    etype = _event_type(event)
    if etype == "tool_call":
        name, arguments, _ = _extract_tool_call_info(event)
        return _summarize_tool_call(name, arguments)
    if etype == "tool_result":
        name, output, _ = _extract_tool_result_info(event)
        return _summarize_tool_result(name, output)
    return ""


def _sse(payload: dict) -> str:
    return "data: " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n\n"


def _sse_comment(text: str) -> str:
    # SSE comment lines start with ":" and are ignored by the AI SDK parser.
    return f": {text}\n\n"


__all__ = [
    "AI_SDK_STREAM_HEADERS",
    "to_ai_sdk_stream",
    "HEARTBEAT_INTERVAL",
]
