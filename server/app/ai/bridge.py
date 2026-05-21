from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from app.ai.agent import AICCCommanderAgent
from app.ai.mcp_client import MCPClientSkeleton, MCPServerConfig
from app.ai.models import AgentExecutionSummary
from app.ai.openclaw_sdk_adapter import OpenClawSDKAdapter
from app.ai.pydantic_agent import AgentDeps, build_agent
from app.ai.skill_registry import AICCSkillRegistry
from app.aicc_runtime.runtime import ROOT_DIR, AICCRuntime

logger = logging.getLogger(__name__)

DEFAULT_SCENARIO_PATH = ROOT_DIR / "client" / "src" / "scenarios" / "SCS.json"


class AICCOpenClawBridge:
    """Unified bridge for AICC agent, skill registry, and MCP skeleton."""

    def __init__(
        self,
        scenario_path: Path = DEFAULT_SCENARIO_PATH,
        llm_model: str = "",
        llm_api_key: str = "",
        llm_base_url: str = "",
    ) -> None:
        self.runtime = AICCRuntime(scenario_path=scenario_path)
        self.skill_registry = AICCSkillRegistry(runtime=self.runtime)
        self.mcp_client = MCPClientSkeleton()
        self.sdk_adapter = OpenClawSDKAdapter()
        self.agent = AICCCommanderAgent(
            skill_registry=self.skill_registry,
            mcp_client=self.mcp_client,
            sdk_adapter=self.sdk_adapter,
        )
        self._register_default_mcp_skeleton()

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
        scenario_env = os.environ.get("AICC_MCP_RUNTIME_SCENARIO")
        scenario_path = Path(scenario_env) if scenario_env else DEFAULT_SCENARIO_PATH
        return cls(
            scenario_path=scenario_path,
            llm_model=settings.llm_model,
            llm_api_key=settings.llm_api_key,
            llm_base_url=settings.llm_base_url,
        )

    def _register_default_mcp_skeleton(self) -> None:
        self.mcp_client.register_server(
            MCPServerConfig(
                name="solver-reserved",
                transport="stdio",
                command="",
                args=[],
                enabled=False,
            )
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
             sidebar. When ``provider`` + ``model`` + ``apiKey`` are all
             present we build a one-off agent so the user's editor truly
             takes effect.
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
            if provider and model_name and api_key:
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

            return await run_agent(agent, command, self.skill_registry)
        return self.agent.process_command(command=command, context=context)

    def exported_scenario(self) -> dict[str, Any]:
        return self.runtime.get_exported_scenario()
