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

class TestToolLifecycle:
    @pytest.mark.asyncio
    async def test_success_flow(self):
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
        events = [json.loads(l[6:]) for l in lines if l.startswith("data: ")]
        et = [e["type"] for e in events]
        assert 'tool-input-start' in et and 'tool-output-available' in et and 'text-delta' in et
        assert "tool-input-start" in et
        assert "tool-input-available" in et
        assert "tool-output-available" in et
        assert "text-delta" in et
        assert et[-1] == "finish"

    @pytest.mark.asyncio
    async def test_error_flow_no_generic_error_event(self):
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
        events = [json.loads(l[6:]) for l in lines if l.startswith("data: ")]
        et = [e["type"] for e in events]
        ti_idx = et.index("tool-input-available")
        to_idx = et.index("tool-output-available")
        assert ti_idx < to_idx, "tool-input-available must precede tool-output-available"
        generic_errors = [e for e in events if e["type"] == "error"]
        assert len(generic_errors) == 0, f"No generic error events, got {generic_errors}"
        assert et[-1] == "finish"

    @pytest.mark.asyncio
    async def test_same_call_id_through_error(self):
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
        events = [json.loads(l[6:]) for l in lines if l.startswith("data: ")]
        tool_events = [e for e in events if e["type"] in ("tool-input-start","tool-input-available","tool-output-available")]
        cids = set(e["toolCallId"] for e in tool_events)
        assert len(cids) == 1, f"All tool events must share one call_id, got {cids}"
        assert "" not in cids

