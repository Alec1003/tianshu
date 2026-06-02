from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.ai.agent import AICCCommanderAgent
from app.ai.command_governance import CommandApprovalQueue
from app.ai.mcp_client import MCPClientSkeleton
from app.ai.models import (
    AgentExecutionSummary,
    CommandProposal,
    SkillExecutionResult,
    StructuredCommandStep,
)
from app.ai.openclaw_sdk_adapter import OpenClawSDKAdapter
from app.ai.pydantic_agent import build_agent
from app.ai.skill_registry import AICCSkillRegistry
from app.aicc_runtime.runtime import AICCRuntime
from app.platform.paths import default_scenario_path

logger = logging.getLogger(__name__)

DEFAULT_SCENARIO_PATH = default_scenario_path()


class AICCOpenClawBridge:
    """Unified bridge for 天枢平台 agent, skill registry, and external MCP client."""

    def __init__(
        self,
        scenario_path: Path = DEFAULT_SCENARIO_PATH,
        llm_model: str = "",
        llm_api_key: str = "",
        llm_base_url: str = "",
        external_mcp_servers: str | None = None,
    ) -> None:
        self.runtime = AICCRuntime(scenario_path=scenario_path)
        self.skill_registry = AICCSkillRegistry(runtime=self.runtime)
        self.command_approvals = CommandApprovalQueue(
            runtime=self.runtime,
            registry=self.skill_registry,
        )
        self.mcp_client = MCPClientSkeleton.from_env(external_mcp_servers)
        self.sdk_adapter = OpenClawSDKAdapter()
        self.agent = AICCCommanderAgent(
            skill_registry=self.skill_registry,
            mcp_client=self.mcp_client,
            sdk_adapter=self.sdk_adapter,
        )
        # ── S4: Pydantic AI agent ─────────────────────────────────────────────
        # Built only when a model is configured; otherwise None and the regex
        # planner in self.agent is used as the fallback.
        self.pydantic_agent = None
        self.pydantic_ask_agent = None
        if llm_model:
            self.pydantic_agent = build_agent(
                model_id=llm_model,
                api_key=llm_api_key,
                base_url=llm_base_url,
            )
            self.pydantic_ask_agent = build_agent(
                model_id=llm_model,
                api_key=llm_api_key,
                base_url=llm_base_url,
                enable_tools=False,
            )
            logger.info("pydantic-ai agent built: model=%s", llm_model)

    @classmethod
    def from_env(cls) -> "AICCOpenClawBridge":
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

    def _resolve_agent_for_request(self, context: dict[str, Any] | None):
        """Pick the pydantic-ai agent to use for a single request.

        Priority:
          1. ``context["model"]`` – user-supplied model config from the AI
             sidebar. When the provider/model pair is complete and either an
             API key is present or the provider supports keyless local access,
             we build a one-off agent so the user's editor truly takes effect.
          2. ``self.pydantic_agent`` – the env-var–configured global agent
             from ``from_env``.
          3. ``None`` – caller falls back to the regex planner.

        Errors during per-request build are swallowed and logged; we then
        fall back to the global agent rather than failing the user's
        command outright.
        """
        ctx = context or {}
        model_cfg = ctx.get("model") if isinstance(ctx, dict) else None
        if isinstance(model_cfg, dict):
            provider = str(model_cfg.get("provider") or "").strip()
            model_name = str(model_cfg.get("model") or "").strip()
            api_key = str(model_cfg.get("apiKey") or "").strip()
            base_url = str(model_cfg.get("baseUrl") or "").strip()
            from app.ai.pydantic_agent import can_build_model_override  # noqa: PLC0415

            if can_build_model_override(provider, model_name, api_key, base_url):
                model_id = f"{provider}:{model_name}"
                try:
                    from app.ai.pydantic_agent import build_agent  # noqa: PLC0415

                    return build_agent(
                        model_id=model_id,
                        api_key=api_key,
                        base_url=base_url,
                    )
                except Exception as exc:  # pragma: no cover - depends on SDK
                    logger.warning(
                        "per-request pydantic-ai agent build failed (%s): %s",
                        model_id,
                        exc,
                    )
        return self.pydantic_agent

    async def process_command_async(
        self, command: str, context: dict[str, Any] | None = None
    ) -> AgentExecutionSummary:
        """Async path — uses pydantic-ai agent when configured, regex planner otherwise.

        ``context["model"]`` (when supplied) overrides the global env-var
        agent for this single request — see ``_resolve_agent_for_request``.
        """
        agent = self._resolve_agent_for_request(context)
        if agent is not None:
            from app.ai.pydantic_agent import run_agent  # noqa: PLC0415

            return await run_agent(
                agent,
                command,
                self.skill_registry,
                mcp_client=self.mcp_client,
            )
        return self.agent.process_command(command=command, context=context)

    async def propose_command_async(
        self, command: str, context: dict[str, Any] | None = None
    ) -> tuple[AgentExecutionSummary, list[CommandProposal]]:
        """Create structured command proposals without mutating runtime state."""
        agent = self._resolve_agent_for_request(context)
        if agent is not None:
            from app.ai.pydantic_agent import run_agent  # noqa: PLC0415

            summary = await run_agent(
                agent,
                command,
                self.skill_registry,
                approval_queue=self.command_approvals,
                mcp_client=self.mcp_client,
            )
            proposals = [
                proposal
                for result in summary.skill_calls
                if (proposal_id := result.output.get("proposalId"))
                for proposal in [self.command_approvals.get(str(proposal_id))]
                if proposal is not None
            ]
            return summary, proposals

        return self._propose_with_regex(command)

    def _propose_with_regex(
        self, command: str
    ) -> tuple[AgentExecutionSummary, list[CommandProposal]]:
        """Fallback planner used only when no LLM agent is configured."""
        planned_calls = self.agent.plan_command(command)
        summary = AgentExecutionSummary(
            command=command,
            decomposition=self.agent._decompose(command),
        )
        if not planned_calls:
            summary.status = "error"
            summary.error = self.agent._build_no_skill_message(command)
            return summary, []

        steps = [
            StructuredCommandStep(
                id=f"step-{index + 1}",
                skill=call.name,
                parameters=call.parameters,
                source_text=call.source_text,
                summary=call.name.replace("_", " "),
                risk="medium",
            )
            for index, call in enumerate(planned_calls)
        ]
        proposal = self.command_approvals.create_proposal(
            command=command,
            steps=steps,
            source="regex",
        )
        summary.skill_calls = [
            SkillExecutionResult(
                skill=step.skill,
                status="ok",
                parameters=step.parameters,
                output={
                    "proposalId": proposal.id,
                    "proposalStatus": proposal.status,
                    "requiresApproval": True,
                },
            )
            for step in steps
        ]
        summary.status = "partial" if proposal.status == "blocked" else "ok"
        if proposal.status == "blocked":
            summary.error = proposal.adjudication.summary
        return summary, [proposal]

    def exported_scenario(self) -> dict[str, Any]:
        return self.runtime.get_exported_scenario()
