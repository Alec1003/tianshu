from __future__ import annotations
import json
import pytest
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

@pytest.mark.asyncio
async def test_tool_error_does_not_emit_tool_events():
    """Even when a tool errors, no tool events are forwarded to the AI SDK.
    The user just sees the final text response."""
    llm = AsyncMock()
    llm.call = AsyncMock(side_effect=[
        LLMResponse(text="", tool_calls=[{"id":"c1","type":"function","function":{"name":"bad","arguments":"{}"}}]),
        LLMResponse(text="recovered", tool_calls=[]),
    ])
    reg = MagicMock()
    reg.execute = AsyncMock(side_effect=RuntimeError("crash"))
    loop = ToolLoop(llm_adapter=llm, tool_registry=reg)
    msgs = [{"role":"user","content":"call"}]
    tools = [{"type":"function","function":{"name":"bad","description":"","parameters":{"type":"object","properties":{}}}}]
    actions = [a async for a in loop.run(msgs, tools=tools)]
    lines = [l async for l in to_ai_sdk_stream(_a(*actions))]
    events = _events(lines)
    et = _types(events)
    for banned in ("tool-input-start", "tool-output-available", "tool-call-start", "tool-call-end"):
        assert banned not in et
    assert "text-delta" in et
    assert "finish" in et

@pytest.mark.asyncio
async def test_error_then_finish():
    err = RuntimeEvent.error("bad")
    fin = RuntimeEvent.finish("error")
    lines = [l async for l in to_ai_sdk_stream(_a(err, fin))]
    events = _events(lines)
    et = _types(events)
    assert "text-delta" in et  # error surfaced as text
    assert "finish" in et
