from __future__ import annotations
import json, pytest
from app.agent_runtime.runtime.runtime_event import RuntimeEvent
from app.agent_runtime.runtime.envelope import Envelope
from app.agent_runtime.ai_sdk_adapter import to_ai_sdk_stream

async def _a(*items):
    for item in items:
        yield item

def _events(lines):
    return [json.loads(l[6:]) for l in lines if l.startswith("data: ")]

def _types(events):
    return [e["type"] for e in events]

class TestRuntimeCreation:
    def test_text(self):
        e = RuntimeEvent.text("hello")
        assert e.type == "text"
    def test_tool_call(self):
        e = RuntimeEvent.tool_call("inspect", {"a":1})
        assert e.type == "tool_call"
    def test_tool_result(self):
        e = RuntimeEvent.tool_result("inspect", {"ok":True})
        assert e.type == "tool_result"
    def test_error(self):
        e = RuntimeEvent.error("bad","ERR")
        assert e.type == "error"
    def test_finish(self):
        e = RuntimeEvent.finish("stop")
        assert e.type == "finish"
    def test_heartbeat(self):
        e = RuntimeEvent.heartbeat()
        assert e.type == "heartbeat"

class TestEnvelope:
    def test_text(self):
        env = Envelope().from_runtime_event(RuntimeEvent.text("hi"))
        assert env.type == "text"
    def test_tool_call(self):
        env = Envelope().from_runtime_event(RuntimeEvent.tool_call("x",{"a":1}))
        assert env.type == "tool_call"
    def test_tool_result(self):
        env = Envelope().from_runtime_event(RuntimeEvent.tool_result("x",{"r":1}))
        assert env.type == "tool_result"
    def test_error(self):
        env = Envelope().from_runtime_event(RuntimeEvent.error("bad"))
        assert env.type == "error"
    def test_finish(self):
        env = Envelope().from_runtime_event(RuntimeEvent.finish())
        assert env.type == "finish"
    def test_heartbeat_skip(self):
        env = Envelope().from_runtime_event(RuntimeEvent.heartbeat())
        assert env is None

class TestAISDKv5:
    @pytest.mark.asyncio
    async def test_text(self):
        lines = [l async for l in to_ai_sdk_stream(_a(RuntimeEvent.text("hi")))]
        events = _events(lines)
        et = _types(events)
        assert "text-start" in et
        assert "text-end" in et
        assert "finish" in et

    @pytest.mark.asyncio
    async def test_tool_call_is_hidden(self):
        """Tool events must not surface to the AI SDK."""
        lines = [l async for l in to_ai_sdk_stream(_a(
            RuntimeEvent.tool_call("inspect", {}, call_id="test-c1"),
            RuntimeEvent.finish(),
        ))]
        events = _events(lines)
        et = _types(events)
        for banned in ("tool-input-start", "tool-input-available", "tool-call-start"):
            assert banned not in et

    @pytest.mark.asyncio
    async def test_tool_result_is_hidden(self):
        lines = [l async for l in to_ai_sdk_stream(_a(
            RuntimeEvent.tool_result("x", {"ok":1}, call_id="test-c1"),
            RuntimeEvent.finish(),
        ))]
        events = _events(lines)
        et = _types(events)
        assert "tool-output-available" not in et

    @pytest.mark.asyncio
    async def test_error_finish(self):
        lines = [l async for l in to_ai_sdk_stream(_a(RuntimeEvent.error("bad"), RuntimeEvent.finish("error")))]
        events = _events(lines)
        et = _types(events)
        assert "text-delta" in et  # error surfaced as text
        assert "finish" in et

    @pytest.mark.asyncio
    async def test_finish(self):
        lines = [l async for l in to_ai_sdk_stream(_a(RuntimeEvent.finish()))]
        events = _events(lines)
        et = _types(events)
        assert "finish" in et
        # No text-start needed if no events came before
        assert "text-start" in et  # adapter always opens a text block before closing

    @pytest.mark.asyncio
    async def test_no_tool_events_leak(self):
        lines = [l async for l in to_ai_sdk_stream(_a(
            RuntimeEvent.tool_call("x", {}, call_id="test-c2"),
            RuntimeEvent.tool_result("x", {"r":1}, call_id="test-c2"),
            RuntimeEvent.finish(),
        ))]
        events = _events(lines)
        et = _types(events)
        for banned in (
            "tool-input-start", "tool-input-available", "tool-output-available",
            "tool-call-start", "tool-call-end", "tool-result",
        ):
            assert banned not in et, f"Tool event {banned!r} must not be in {et}"

    @pytest.mark.asyncio
    async def test_heartbeat_emits_comment(self):
        """If no event arrives within HEARTBEAT_INTERVAL, an SSE comment
        must be emitted so the browser keeps the connection open."""
        import asyncio
        from app.agent_runtime.ai_sdk_adapter import HEARTBEAT_INTERVAL

        async def slow():
            await asyncio.sleep(HEARTBEAT_INTERVAL + 0.5)
            yield RuntimeEvent.text("hi")

        lines = [l async for l in to_ai_sdk_stream(slow())]
        # At least one comment line should be present
        assert any(l.startswith(":") for l in lines), f"expected heartbeat comment, got {lines!r}"
