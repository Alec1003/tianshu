from __future__ import annotations
import asyncio
import json
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from app.agent_runtime.runtime.runtime_event import RuntimeEvent
from app.agent_runtime.agents.tool_loop import ToolLoop
from app.agent_runtime.agents.llm_adapter import LLMResponse
from app.agent_runtime.ai_sdk_adapter import to_ai_sdk_stream

async def _a(*items):
    for item in items:
        yield item

@pytest.mark.asyncio
async def test_tool_call_event_order():
    llm = AsyncMock()
    llm.call = AsyncMock(side_effect=[
        LLMResponse(text="", tool_calls=[{"id":"c1","type":"function","function":{"name":"inspect","arguments":"{}"}}]),
        LLMResponse(text="Found 11 aircraft", tool_calls=[]),
    ])
    reg = MagicMock()
    reg.execute = AsyncMock(return_value={"ok":True,"kind":"scene"})
    loop = ToolLoop(llm_adapter=llm, tool_registry=reg)
    msgs = [{"role":"user","content":"check"}]
    tools = [{"type":"function","function":{"name":"inspect","description":"","parameters":{"type":"object","properties":{}}}}]
    actions = [a async for a in loop.run(msgs, tools=tools)]
    lines = [l async for l in to_ai_sdk_stream(_a(*actions))]
    events = [json.loads(l[6:]) for l in lines if l.startswith("data: ")]
    et = [e["type"] for e in events]
    assert "tool-input-start" in et
    assert "tool-input-available" in et
    assert "tool-output-available" in et
    assert "text-start" in et
    assert "text-delta" in et
    for e in events:
        if e["type"] == "text-delta":
            assert "ok" not in e.get("delta","")
    assert "tool-call-start" not in et
    assert "tool-result" not in et

@pytest.mark.asyncio
async def test_normal_chat_no_tool():
    llm = AsyncMock()
    llm.call = AsyncMock(return_value=LLMResponse(text="Hello!", tool_calls=[]))
    loop = ToolLoop(llm_adapter=llm)
    actions = [a async for a in loop.run([{"role":"user","content":"hi"}])]
    lines = [l async for l in to_ai_sdk_stream(_a(*actions))]
    joined = "".join(lines)
    assert "text-start" in joined
    assert "text-delta" in joined


@pytest.mark.asyncio
async def test_approval_gate_resumes_same_tool_loop():
    class ApprovalGate:
        def __init__(self):
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def wait_for_resolution(self, proposal_id):
            assert proposal_id == "proposal-1"
            self.started.set()
            await self.release.wait()
            return SimpleNamespace(
                status="executed",
                execution=[{"skill": "deploy_aircraft", "status": "ok"}],
                error=None,
            )

    llm = AsyncMock()
    llm.call = AsyncMock(side_effect=[
        LLMResponse(
            text="",
            tool_calls=[
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "deploy_aircraft", "arguments": "{}"},
                }
            ],
        ),
        LLMResponse(text="部署已完成", tool_calls=[]),
    ])
    registry = MagicMock()
    registry.execute = AsyncMock(
        return_value={
            "proposalId": "proposal-1",
            "proposalStatus": "pending",
            "requiresApproval": True,
        }
    )
    gate = ApprovalGate()
    loop = ToolLoop(
        llm_adapter=llm,
        tool_registry=registry,
        tool_context=SimpleNamespace(approval_queue=gate),
    )

    async def collect():
        return [
            action
            async for action in loop.run(
                [{"role": "user", "content": "部署一架飞机"}],
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "deploy_aircraft",
                            "description": "",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
            )
        ]

    task = asyncio.create_task(collect())
    await gate.started.wait()
    assert not task.done(), "the agent turn must pause at the approval gate"
    gate.release.set()
    actions = await task

    assert llm.call.await_count == 2
    assert any(action.payload.get("text") == "部署已完成" for action in actions)
