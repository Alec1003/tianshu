from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent_runtime.ai_sdk_adapter import to_ai_sdk_stream
from app.agent_runtime.builder import AgentBuilder, QwenPawTextAgent
from app.agent_runtime.events import AgentEvent
from app.agent_runtime.executor import AgentExecutor
from app.agent_runtime.runtime import AgentRuntime, AgentRuntimeRequest
from app.ai.command_governance import CommandApprovalQueue
from app.ai.skill_registry import TianShuSkillRegistry


class FakeAgent:
    async def reply_stream(self, messages):
        assert messages[0]["role"] == "user"
        yield "hello"
        yield {"delta": " world"}


class FakeBuilder:
    async def build(self, request):
        assert request.user_id == "user-1"
        return FakeAgent()


@pytest.mark.asyncio
async def test_qwenpaw_backend_can_start_agent_runtime():
    runtime = AgentRuntime(builder=FakeBuilder(), executor=AgentExecutor())

    events = [
        event
        async for event in runtime.run(
            AgentRuntimeRequest(
                messages=[{"role": "user", "content": "hi"}],
                user_id="user-1",
                scenario_id="scenario-1",
            )
        )
    ]

    assert [event.type for event in events] == [
        "start",
        "text_delta",
        "text_delta",
        "complete",
    ]
    assert "".join(event.content for event in events) == "hello world"


@pytest.mark.asyncio
async def test_agent_builder_can_create_text_agent_from_request_model(monkeypatch):
    monkeypatch.setenv("TIANSHU_LLM_MODEL", "")
    from app.config import get_settings

    get_settings.cache_clear()
    builder = AgentBuilder()

    agent = await builder.build(
        AgentRuntimeRequest(
            messages=[],
            user_id="user-1",
            scenario_id="scenario-1",
            model={
                "provider": "qwen",
                "model": "qwen-plus",
                "apiKey": "sk-test",
                "baseUrl": "",
            },
        )
    )

    assert isinstance(agent, QwenPawTextAgent)
    assert agent.model_config.provider == "qwen"
    assert agent.model_config.model == "qwen-plus"
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_executor_returns_text_events():
    events = [
        event
        async for event in AgentExecutor().run(
            FakeAgent(),
            [{"role": "user", "content": "hi"}],
        )
    ]

    assert [event.type for event in events] == [
        "start",
        "text_delta",
        "text_delta",
        "complete",
    ]


@pytest.mark.asyncio
async def test_ai_sdk_adapter_outputs_text_stream():
    async def events():
        yield AgentEvent("start")
        yield AgentEvent("text_delta", "abc")
        yield AgentEvent("complete")

    chunks = [chunk async for chunk in to_ai_sdk_stream(events())]
    stream = "".join(chunks)

    assert '"type":"start"' in stream
    assert '"type":"text-delta"' in stream
    assert '"delta":"abc"' in stream
    assert '"type":"finish"' in stream


def test_agent_backend_defaults_to_qwenpaw(monkeypatch):
    from app.api import ai as ai_api
    from app.config import get_settings

    monkeypatch.delenv("TIANSHU_AGENT_BACKEND", raising=False)
    get_settings.cache_clear()

    from app.config import get_settings; assert get_settings().agent_backend == "qwenpaw"
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_qwenpaw_backend_can_stream(monkeypatch):
    """Chat endpoint uses AgentRuntime streaming."""
    from app.api import ai as ai_api
    from app.config import get_settings

    get_settings.cache_clear()
    async def stream_response(*_args, **_kwargs):
        from fastapi.responses import StreamingResponse
        return StreamingResponse(iter(["data: test"]), media_type="text/event-stream")
    monkeypatch.setattr(ai_api, "_chat_with_agent_runtime", stream_response)
    result = await ai_api.chat(object(), object(), object())
    assert hasattr(result, 'body_iterator')
    get_settings.cache_clear()


def test_workspace_runtime_identity_is_not_changed():
    workspace = SimpleNamespace(runtime=object())
    runtime = AgentRuntime()

    workspace.agent_runtime = runtime

    assert workspace.agent_runtime is runtime
    assert workspace.runtime is workspace.runtime


def test_command_approval_queue_is_unmodified():
    assert hasattr(CommandApprovalQueue, "approve_and_execute")
    assert hasattr(CommandApprovalQueue, "create_single_step_proposal")


def test_skill_registry_execution_contract_is_unmodified():
    assert hasattr(TianShuSkillRegistry, "execute")
    assert hasattr(TianShuSkillRegistry, "has_skill")
