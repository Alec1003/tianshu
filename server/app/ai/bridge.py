from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.agent_runtime.runtime import AgentRuntimeRequest
from app.agent_runtime.runtime.envelope import EnvelopeEvent
from app.ai.models import (
    AgentExecutionSummary,
    CommandProposal,
    SkillExecutionResult,
    StructuredCommandStep,
)
from app.agent_runtime.workspace.workspace import TianShuWorkspace
from app.platform.paths import default_scenario_path

logger = logging.getLogger(__name__)

DEFAULT_SCENARIO_PATH = default_scenario_path()


class TianShuOpenClawBridge:
    """Unified bridge for 天枢平台 agent, skill registry, and external MCP client."""

    def __init__(
        self,
        scenario_path: Path = DEFAULT_SCENARIO_PATH,
        llm_model: str = "",
        llm_api_key: str = "",
        llm_base_url: str = "",
        external_mcp_servers: str | None = None,
        workspace: TianShuWorkspace | None = None,
    ) -> None:
        self.scenario_path = scenario_path
        self.llm_model = llm_model
        self.llm_api_key = llm_api_key
        self.llm_base_url = llm_base_url
        self.workspace = workspace or TianShuWorkspace.create(
            user_id="default",
            scenario_id="default",
            scenario_path=scenario_path,
            external_mcp_servers=external_mcp_servers,
        )
        self._bind_workspace_facade()
        # ── S4: Pydantic AI agent ─────────────────────────────────────────────
        # Built only when a model is configured; otherwise None and the regex


    def _bind_workspace_facade(self) -> None:
        self.runtime = self.workspace.runtime
        self.skill_registry = self.workspace.skill_registry
        self.command_approvals = self.workspace.command_approvals
        self.mcp_client = self.workspace.mcp_client
        self.sdk_adapter = self.workspace.sdk_adapter
        self.memory_manager = self.workspace.memory_manager
        self.context_manager = self.workspace.context_manager
        self.agent_runtime = self.workspace.agent_runtime
        self.agent_registry = self.workspace.agent_registry
        self.capability_registry = self.workspace.capability_registry
        self.workflow_orchestrator = self.workspace.workflow_orchestrator
        self.driver_registry = self.workspace.driver_registry
        self.tool_registry = self.workspace.tool_registry
        self.agent = self.workspace.agent

    @classmethod
    def from_env(cls) -> "TianShuOpenClawBridge":
        from app.config import get_settings  # noqa: PLC0415

        settings = get_settings()
        return cls(
            scenario_path=default_scenario_path(),
            llm_model=settings.llm_model,
            llm_api_key=settings.llm_api_key,
            llm_base_url=settings.llm_base_url,
            external_mcp_servers=settings.external_mcp_servers,
        )

    def process_command(
        self, command: str, context: dict[str, Any] | None = None
    ) -> AgentExecutionSummary:
        """Synchronous path — regex planner only (no LLM)."""
        return self.agent.process_command(command=command, context=context)

    async def _process_with_agent_runtime(
        self, command: str, context: dict[str, Any] | None = None
    ) -> AgentExecutionSummary:
        ctx = context or {}
        model_cfg = ctx.get("model") if isinstance(ctx, dict) else None
        model: dict[str, Any] = {}
        if isinstance(model_cfg, dict):
            model = {
                "provider": str(model_cfg.get("provider") or "").strip(),
                "model": str(model_cfg.get("model") or "").strip(),
                "apiKey": str(model_cfg.get("apiKey") or "").strip(),
                "baseUrl": str(model_cfg.get("baseUrl") or "").strip(),
            }
        runtime_request = AgentRuntimeRequest(
            messages=[{"role": "user", "content": command}],
            user_id="default",
            model=model,
            workspace=self.workspace,
            tool_registry=self.tool_registry,
            approval_queue=self.command_approvals,
            chat_mode="command",
        )
        summary = AgentExecutionSummary(command=command, decomposition=[command])
        has_error = False
        has_results = False
        async for event in self.workspace.stream_query(runtime_request):
            if not isinstance(event, EnvelopeEvent):
                continue
            if event.type in {"start", "finish", "text"}:
                continue
            if event.type == "error":
                has_error = True
                summary.error = summary.error or event.content
                continue
            if event.type == "tool_call":
                # A tool invocation started; the result arrives as a
                # separate "tool_result" event which carries the output.
                continue
            if event.type == "tool_result":
                md = event.metadata or {}
                skill_name = str(
                    event.content
                    or md.get("tool")
                    or md.get("capability")
                    or "unknown"
                )
                has_results = True
                output_val = md.get("result")
                summary.skill_calls.append(SkillExecutionResult(
                    skill=skill_name, status="ok",
                    parameters=md.get("arguments", {}),
                    output=output_val if isinstance(output_val, dict) else {},
                ))
        if not has_results:
            # No tool results (no model, or text-only). Fall back to regex planner.
            return self.agent.process_command(command=command, context=context)
        if has_error:
            summary.status = "partial"
        else:
            summary.status = "ok"
        return summary



    async def process_command_async(
        self, command: str, context: dict[str, Any] | None = None
    ) -> AgentExecutionSummary:
        """Async path — uses AgentRuntime pipeline with regex fallback."""
        return await self._process_with_agent_runtime(command, context)

    async def propose_command_async(
        self, command: str, context: dict[str, Any] | None = None
    ) -> tuple[AgentExecutionSummary, list[CommandProposal]]:
        """Create structured command proposals via AgentRuntime pipeline."""
        summary = await self._process_with_agent_runtime(command, context)
        proposals: list[CommandProposal] = []
        for result in summary.skill_calls:
            pid = result.output.get("proposalId") if isinstance(result.output, dict) else None
            if pid:
                proposal = self.command_approvals.get(pid)
                if proposal is not None and proposal not in proposals:
                    proposals.append(proposal)
        return summary, proposals

    def exported_scenario(self) -> dict[str, Any]:
        return self.runtime.get_exported_scenario()
