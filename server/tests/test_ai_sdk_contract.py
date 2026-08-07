from __future__ import annotations
import json, pytest
from unittest.mock import AsyncMock, MagicMock
from app.agent_runtime.runtime.runtime_event import RuntimeEvent
from app.agent_runtime.agents.tool_loop import ToolLoop
from app.agent_runtime.agents.llm_adapter import LLMResponse
from app.agent_runtime.ai_sdk_adapter import to_ai_sdk_stream

async def _a(*items):
    for item in items:
        yield item

def _events(lines):
    return [json.loads(l[6:]) for l in lines if l.startswith("data: ")]

def _types(events):
    return [e["type"] for e in events]

class TestToolEventsAreHidden:
    """Tool events must NEVER be forwarded to the AI SDK. The user sees
    only the final LLM text, never the raw tool JSON or call ids."""

    @pytest.mark.asyncio
    async def test_tool_call_not_emitted(self):
        llm = AsyncMock()
        llm.call = AsyncMock(side_effect=[
            LLMResponse(text="", tool_calls=[{"id":"c1","type":"function","function":{"name":"inspect","arguments":"{}"}}]),
            LLMResponse(text="done", tool_calls=[]),
        ])
        reg = MagicMock()
        reg.execute = AsyncMock(return_value={"ok":True})
        loop = ToolLoop(llm_adapter=llm, tool_registry=reg)
        actions = [a async for a in loop.run([{"role":"user","content":"check"}], tools=[{"type":"function","function":{"name":"inspect","description":"","parameters":{"type":"object","properties":{}}}}])]
        lines = [l async for l in to_ai_sdk_stream(_a(*actions))]
        et = _types(_events(lines))
        for banned in (
            "tool-input-start",
            "tool-input-available",
            "tool-output-available",
            "tool-call-start",
            "tool-call-end",
        ):
            assert banned not in et, f"Tool event {banned!r} must not be emitted, but found in {et}"

    @pytest.mark.asyncio
    async def test_tool_result_not_emitted(self):
        llm = AsyncMock()
        llm.call = AsyncMock(side_effect=[
            LLMResponse(text="", tool_calls=[{"id":"c1","type":"function","function":{"name":"inspect","arguments":"{}"}}]),
            LLMResponse(text="done", tool_calls=[]),
        ])
        reg = MagicMock()
        reg.execute = AsyncMock(return_value={"ok":True})
        loop = ToolLoop(llm_adapter=llm, tool_registry=reg)
        actions = [a async for a in loop.run([{"role":"user","content":"check"}], tools=[{"type":"function","function":{"name":"inspect","description":"","parameters":{"type":"object","properties":{}}}}])]
        lines = [l async for l in to_ai_sdk_stream(_a(*actions))]
        events = _events(lines)
        # No tool output JSON should leak to the user
        for e in events:
            assert "toolCallId" not in e
            assert "toolName" not in e
            assert "output" not in e or e.get("type") != "tool-output-available"

    @pytest.mark.asyncio
    async def test_text_appears_after_tool_loop(self):
        llm = AsyncMock()
        llm.call = AsyncMock(side_effect=[
            LLMResponse(text="", tool_calls=[{"id":"c1","type":"function","function":{"name":"inspect","arguments":"{}"}}]),
            LLMResponse(text="final answer", tool_calls=[]),
        ])
        reg = MagicMock()
        reg.execute = AsyncMock(return_value={"ok":True})
        loop = ToolLoop(llm_adapter=llm, tool_registry=reg)
        actions = [a async for a in loop.run([{"role":"user","content":"check"}], tools=[{"type":"function","function":{"name":"inspect","description":"","parameters":{"type":"object","properties":{}}}}])]
        lines = [l async for l in to_ai_sdk_stream(_a(*actions))]
        events = _events(lines)
        deltas = [e["delta"] for e in events if e["type"] == "text-delta"]
        assert "final answer" in "".join(deltas)


class TestNormalChat:
    @pytest.mark.asyncio
    async def test_simple(self):
        llm = AsyncMock()
        llm.call = AsyncMock(return_value=LLMResponse(text="Hello!", tool_calls=[]))
        loop = ToolLoop(llm_adapter=llm)
        actions = [a async for a in loop.run([{"role":"user","content":"hi"}])]
        lines = [l async for l in to_ai_sdk_stream(_a(*actions))]
        events = _events(lines)
        et = _types(events)
        assert "text-start" in et
        assert "text-delta" in et
        assert events[-1]["type"] == "finish"

    @pytest.mark.asyncio
    async def test_starts_immediately(self):
        """The first emitted event MUST be 'start' so the SSE connection
        is established without buffering."""
        async def slow_events():
            import asyncio
            await asyncio.sleep(0.05)
            yield RuntimeEvent.text("hello")

        lines = [l async for l in to_ai_sdk_stream(slow_events())]
        events = _events(lines)
        assert events[0]["type"] == "start"
        assert events[0].get("messageId")


class TestToolError:
    @pytest.mark.asyncio
    async def test_error_finish(self):
        llm = AsyncMock()
        llm.call = AsyncMock(side_effect=[
            LLMResponse(text="", tool_calls=[{"id":"c1","type":"function","function":{"name":"bad","arguments":"{}"}}]),
            LLMResponse(text="recovered", tool_calls=[]),
        ])
        reg = MagicMock()
        reg.execute = AsyncMock(side_effect=RuntimeError("crash"))
        loop = ToolLoop(llm_adapter=llm, tool_registry=reg)
        actions = [a async for a in loop.run([{"role":"user","content":"call"}], tools=[{"type":"function","function":{"name":"bad","description":"","parameters":{"type":"object","properties":{}}}}])]
        lines = [l async for l in to_ai_sdk_stream(_a(*actions))]
        events = _events(lines)
        et = _types(events)
        assert "finish" in et
        assert et[-1] == "finish"
