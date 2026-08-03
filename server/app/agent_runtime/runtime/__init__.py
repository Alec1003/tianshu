from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from app.agent_runtime.agents.builder import AgentBuilder
from app.agent_runtime.context.manager import ContextManager
from app.agent_runtime.events import AgentEvent
from app.agent_runtime.executor import AgentExecutor
from app.agent_runtime.runtime.envelope import Envelope, EnvelopeEvent
from app.agent_runtime.runtime.hook_registry import HookRegistry
from app.agent_runtime.runtime.hooks import HookContext
from app.agent_runtime.runtime.phases import Phase


@dataclass
class AgentRuntimeRequest:
    messages: list[dict[str, Any]]
    user_id: str
    workspace_id: str | None = None
    scenario_id: str | None = None
    model: dict[str, Any] = field(default_factory=dict)
    workspace: Any | None = None
    tool_registry: Any | None = None
    approval_queue: Any | None = None
    capability_registry: Any | None = None
    agent_context: Any | None = None
    prompt_context: str = ""
    chat_mode: str = "command"
    metadata: dict[str, Any] = field(default_factory=dict)


class TianShuRuntimeOrchestrator:
    """QwenPaw-inspired lifecycle orchestrator for one TianShu agent turn."""

    def __init__(
        self,
        *,
        builder: AgentBuilder | None = None,
        executor: AgentExecutor | None = None,
        context_manager: ContextManager | None = None,
        hook_registry: HookRegistry | None = None,
        envelope: Envelope | None = None,
    ) -> None:
        self.builder = builder or AgentBuilder()
        self.executor = executor or AgentExecutor()
        self.context_manager = context_manager
        self.hooks = hook_registry or HookRegistry()
        self.envelope = envelope or Envelope()

    async def run(
        self,
        request: AgentRuntimeRequest,
    ) -> AsyncGenerator[EnvelopeEvent, None]:
        context = HookContext(request=request)
        try:
            await self.hooks.execute(Phase.PRE_DISPATCH, context)
            request = self._normalize_request(request)
            context.request = request
            await self.hooks.execute(Phase.POST_DISPATCH, context)

            await self.hooks.execute(Phase.PRE_AGENT_BUILD, context)
            await self._prepare_request_context(request)
            if self._workflow_enabled(request):
                async for event in self._run_workflow(request):
                    yield event
                await self.hooks.execute(Phase.POST_RESPONSE, context)
                return
            agent = await self._build_agent(request)
            context.agent = agent
            await self.hooks.execute(Phase.POST_AGENT_BUILD, context)

            await self.hooks.execute(Phase.PRE_EXECUTE, context)
            self._mark_agent_running(agent)
            saw_error = False
            async for event in self.executor.run(agent, request.messages):
                envelope_event = self.envelope.from_agent_event(event)
                if envelope_event is not None:
                    if envelope_event.type == "error":
                        saw_error = True
                        self._mark_agent_error(agent, RuntimeError(envelope_event.content))
                    yield envelope_event
            if not saw_error:
                self._mark_agent_finished(agent)
            await self.hooks.execute(Phase.POST_RESPONSE, context)
        except BaseException as exc:
            context.error = exc
            self._mark_agent_error(getattr(context, "agent", None), exc)
            try:
                await self.hooks.execute(Phase.ON_ERROR, context)
            finally:
                yield self.envelope.error(exc)
        finally:
            await self._close_agent(getattr(context, "agent", None))
            await self.hooks.execute(Phase.FINALLY, context)

    async def _prepare_request_context(self, request: AgentRuntimeRequest) -> None:
        capability_registry = request.capability_registry or getattr(
            request.workspace,
            "capability_registry",
            None,
        )
        if capability_registry is not None and request.workspace is not None:
            await capability_registry.load_from_workspace(request.workspace)
            request.capability_registry = capability_registry
        tool_registry = request.tool_registry or getattr(request.workspace, "tool_registry", None)
        if tool_registry is not None and request.workspace is not None:
            await tool_registry.load_driver_tools(request.workspace)
        context_manager = self._context_manager(request)
        if context_manager is not None:
            request.agent_context = await context_manager.build(request)
            request.prompt_context = context_manager.prompt_context(request.agent_context)

    def _context_manager(self, request: AgentRuntimeRequest) -> ContextManager | None:
        if self.context_manager is not None:
            return self.context_manager
        workspace = request.workspace
        manager = getattr(workspace, "context_manager", None)
        return manager if isinstance(manager, ContextManager) else None

    async def _build_agent(self, request: AgentRuntimeRequest):
        workspace = getattr(request, "workspace", None)
        registry = getattr(workspace, "agent_registry", None)
        if registry is not None:
            agent_name = (getattr(request, "metadata", {}) or {}).get("agent_name") or "default"
            return await registry.create_agent(
                request=request,
                builder=self.builder,
                name=str(agent_name),
            )
        return await self.builder.build(request)

    @staticmethod
    def _workflow_enabled(request: AgentRuntimeRequest) -> bool:
        metadata = getattr(request, "metadata", {}) or {}
        return metadata.get("workflow_enabled") is True

    async def _run_workflow(
        self,
        request: AgentRuntimeRequest,
    ) -> AsyncGenerator[EnvelopeEvent, None]:
        workspace = getattr(request, "workspace", None)
        orchestrator = getattr(workspace, "workflow_orchestrator", None)
        if orchestrator is None:
            raise RuntimeError("Workflow execution requires workspace.workflow_orchestrator.")
        async for event in orchestrator.run(
            request=request,
            builder=self.builder,
            executor=self.executor,
            envelope=self.envelope,
        ):
            yield event

    @staticmethod
    def _mark_agent_running(agent) -> None:
        lifecycle = getattr(agent, "lifecycle", None)
        start = getattr(lifecycle, "start", None)
        if callable(start):
            start()

    @staticmethod
    def _mark_agent_finished(agent) -> None:
        lifecycle = getattr(agent, "lifecycle", None)
        finish = getattr(lifecycle, "finish", None)
        if callable(finish):
            finish()

    @staticmethod
    def _mark_agent_error(agent, error: BaseException) -> None:
        lifecycle = getattr(agent, "lifecycle", None)
        fail = getattr(lifecycle, "fail", None)
        if callable(fail):
            fail(error)

    @staticmethod
    async def _close_agent(agent) -> None:
        close = getattr(agent, "close", None)
        if close is None:
            return
        result = close()
        if hasattr(result, "__await__"):
            await result

    @staticmethod
    def _normalize_request(request: AgentRuntimeRequest) -> AgentRuntimeRequest:
        if request.messages is None:
            request.messages = []
        if request.metadata is None:
            request.metadata = {}
        return request


class AgentRuntime(TianShuRuntimeOrchestrator):
    """Backward-compatible facade that emits legacy AgentEvent objects."""

    async def run(
        self,
        request: AgentRuntimeRequest,
    ) -> AsyncGenerator[AgentEvent, None]:
        async for event in super().run(request):
            yield event.to_agent_event()


__all__ = [
    "AgentRuntime",
    "AgentRuntimeRequest",
    "Envelope",
    "EnvelopeEvent",
    "HookContext",
    "HookRegistry",
    "Phase",
    "TianShuRuntimeOrchestrator",
]
