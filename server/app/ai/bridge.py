from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from app.ai.agent import PanopticonCommanderAgent
from app.ai.mcp_client import MCPClientSkeleton, MCPServerConfig
from app.ai.models import AgentExecutionSummary
from app.ai.openclaw_sdk_adapter import OpenClawSDKAdapter
from app.ai.pydantic_agent import AgentDeps, build_agent
from app.ai.skill_registry import PanopticonSkillRegistry
from app.panopticon.runtime import ROOT_DIR, PanopticonRuntime

logger = logging.getLogger(__name__)

DEFAULT_SCENARIO_PATH = ROOT_DIR / "client" / "src" / "scenarios" / "SCS.json"


class PanopticonOpenClawBridge:
    """Unified bridge for OpenClaw agent, skill registry, and MCP skeleton."""

    def __init__(
        self,
        scenario_path: Path = DEFAULT_SCENARIO_PATH,
        llm_model: str = "",
        llm_api_key: str = "",
        llm_base_url: str = "",
    ) -> None:
        self.runtime = PanopticonRuntime(scenario_path=scenario_path)
        self.skill_registry = PanopticonSkillRegistry(runtime=self.runtime)
        self.mcp_client = MCPClientSkeleton()
        self.sdk_adapter = OpenClawSDKAdapter()
        self.agent = PanopticonCommanderAgent(
            skill_registry=self.skill_registry,
            mcp_client=self.mcp_client,
            sdk_adapter=self.sdk_adapter,
        )
        self._register_default_mcp_skeleton()

        # ── S4: Pydantic AI agent ─────────────────────────────────────────────
        # Built only when a model is configured; otherwise None and the regex
        # planner in self.agent is used as the fallback.
        self.pydantic_agent = None
        if llm_model:
            self.pydantic_agent = build_agent(
                model_id=llm_model,
                api_key=llm_api_key,
                base_url=llm_base_url,
            )
            logger.info("pydantic-ai agent built: model=%s", llm_model)

    @classmethod
    def from_env(cls) -> "PanopticonOpenClawBridge":
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

    async def process_command_async(
        self, command: str, context: dict[str, Any] | None = None
    ) -> AgentExecutionSummary:
        """Async path — uses pydantic-ai agent when configured, regex planner otherwise."""
        if self.pydantic_agent is not None:
            from app.ai.pydantic_agent import run_agent  # noqa: PLC0415

            return await run_agent(self.pydantic_agent, command, self.skill_registry)
        return self.agent.process_command(command=command, context=context)

    def exported_scenario(self) -> dict[str, Any]:
        return self.runtime.get_exported_scenario()
