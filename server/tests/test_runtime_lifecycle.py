from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent_runtime.ai_sdk_adapter import to_ai_sdk_stream
from app.agent_runtime.events import AgentEvent
from app.agent_runtime.executor import AgentExecutor
from app.agent_runtime.runtime import (
    AgentRuntime,
    AgentRuntimeRequest,
    HookContext,
    HookRegistry,
    Phase,
    TianShuRuntimeOrchestrator,
)
from app.agent_runtime.runtime.envelope import Envelope, EnvelopeEvent


class FakeAgent:
    async def reply_stream(self, _messages):
        yield "hello"


class FakeBuilder:
    async def build(self, _request):
        return FakeAgent()


class RecordingHook:
    def __init__(self, calls: list[str], label: str) -> None:
        self.calls = calls
        self.label = label

    async def before(self, context: HookContext) -> None:
        self.calls.append(f"{self.label}:{context.phase.value}:before")

    async def after(self, context: HookContext) -> None:
        self.calls.append(f"{self.label}:{context.phase.value}:after")

    async def on_error(self, context: HookContext) -> None:
        self.calls.append(f"{self.label}:{context.phase.value}:error")


@pytest.mark.asyncio
async def test_runtime_lifecycle_phase_order():
    calls: list[str] = []
    hooks = HookRegistry()
    for phase in (
        Phase.PRE_DISPATCH,
        Phase.PRE_AGENT_BUILD,
        Phase.PRE_EXECUTE,
        Phase.POST_RESPONSE,
        Phase.FINALLY,
    ):
        hooks.register(phase, RecordingHook(calls, "hook"))
    runtime = TianShuRuntimeOrchestrator(
        builder=FakeBuilder(),
        executor=AgentExecutor(),
        hook_registry=hooks,
    )

    events = [
        event
        async for event in runtime.run(
            AgentRuntimeRequest(
                messages=[{"role": "user", "content": "hi"}],
                user_id="user-a",
            )
        )
    ]

    assert [event.type for event in events] == ["start", "text", "finish"]
    assert calls == [
        "hook:pre_dispatch:before",
        "hook:pre_agent_build:before",
        "hook:pre_execute:before",
        "hook:post_response:after",
        "hook:finally:after",
    ]


@pytest.mark.asyncio
async def test_hook_registry_register_unregister():
    calls: list[str] = []
    hook = RecordingHook(calls, "one")
    registry = HookRegistry()
    context = HookContext(
        request=AgentRuntimeRequest(messages=[], user_id="user-a")
    )

    registry.register(Phase.PRE_DISPATCH, hook)
    await registry.execute(Phase.PRE_DISPATCH, context)
    registry.unregister(Phase.PRE_DISPATCH, hook)
    await registry.execute(Phase.PRE_DISPATCH, context)

    assert calls == ["one:pre_dispatch:before"]


@pytest.mark.asyncio
async def test_hook_exception_triggers_on_error_and_finally():
    calls: list[str] = []

    class FailingHook:
        async def before(self, _context):
            raise RuntimeError("boom")

    hooks = HookRegistry()
    hooks.register(Phase.PRE_DISPATCH, FailingHook())
    hooks.register(Phase.ON_ERROR, RecordingHook(calls, "error-hook"))
    hooks.register(Phase.FINALLY, RecordingHook(calls, "finally-hook"))
    runtime = TianShuRuntimeOrchestrator(
        builder=FakeBuilder(),
        hook_registry=hooks,
    )

    events = [
        event
        async for event in runtime.run(
            AgentRuntimeRequest(messages=[], user_id="user-a")
        )
    ]

    assert events == [
        EnvelopeEvent(
            "error",
            "boom",
            {"error_type": "RuntimeError"},
        )
    ]
    assert calls == [
        "error-hook:on_error:error",
        "finally-hook:finally:after",
    ]


def test_envelope_converts_legacy_agent_events():
    envelope = Envelope()

    assert envelope.from_agent_event(AgentEvent("start")).type == "start"
    assert (
        envelope.from_agent_event(AgentEvent("text_delta", "abc")).type
        == "text"
    )
    assert (
        envelope.from_agent_event(
            AgentEvent("tool_call_start", metadata={"tool": "x"})
        ).type
        == "tool_call"
    )
    assert envelope.from_agent_event(AgentEvent("complete")).type == "finish"


@pytest.mark.asyncio
async def test_legacy_agent_runtime_facade_keeps_agent_event_contract():
    runtime = AgentRuntime(builder=FakeBuilder(), executor=AgentExecutor())

    events = [
        event
        async for event in runtime.run(
            AgentRuntimeRequest(
                messages=[{"role": "user", "content": "hi"}],
                user_id="user-a",
            )
        )
    ]

    assert [event.type for event in events] == [
        "start",
        "text_delta",
        "complete",
    ]


@pytest.mark.asyncio
async def test_ai_sdk_adapter_accepts_envelope_events():
    async def events():
        yield EnvelopeEvent("start")
        yield EnvelopeEvent("text", "abc")
        yield EnvelopeEvent("finish")

    stream = "".join([chunk async for chunk in to_ai_sdk_stream(events())])

    assert '"type":"start"' in stream
    assert '"type":"text-delta"' in stream
    assert '"delta":"abc"' in stream
    assert '"type":"finish"' in stream


def test_pydantic_backend_default_is_unchanged(monkeypatch):
    from app.api import ai as ai_api
    from app.config import get_settings

    monkeypatch.delenv("TIANSHU_AGENT_BACKEND", raising=False)
    get_settings.cache_clear()

    assert get_settings().agent_backend == "qwenpaw"
    get_settings.cache_clear()


def test_orchestrator_can_be_stored_on_workspace_facade():
    workspace = SimpleNamespace()
    runtime = TianShuRuntimeOrchestrator()

    workspace.agent_runtime = runtime

    assert workspace.agent_runtime is runtime
