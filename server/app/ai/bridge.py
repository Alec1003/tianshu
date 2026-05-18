from __future__ import annotations

from pathlib import Path
from typing import Any

from app.ai.agent import PanopticonCommanderAgent
from app.ai.mcp_client import MCPClientSkeleton, MCPServerConfig
from app.ai.models import AgentExecutionSummary
from app.ai.openclaw_sdk_adapter import OpenClawSDKAdapter
from app.ai.skill_registry import PanopticonSkillRegistry
from app.panopticon.runtime import ROOT_DIR, PanopticonRuntime


DEFAULT_SCENARIO_PATH = ROOT_DIR / "client" / "src" / "scenarios" / "SCS.json"


class PanopticonOpenClawBridge:
    """Unified bridge for OpenClaw agent, skill registry, and MCP skeleton."""

    def __init__(self, scenario_path: Path = DEFAULT_SCENARIO_PATH) -> None:
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

    @classmethod
    def from_env(cls) -> "PanopticonOpenClawBridge":
        return cls()

    def _register_default_mcp_skeleton(self) -> None:
        # ------------------------------- MCP extension -------------------------------
        # Keep only connection skeleton here. Add concrete external MCP servers
        # (e.g., solver service) when available.
        # ---------------------------------------------------------------------------
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
        return self.agent.process_command(command=command, context=context)

    def exported_scenario(self) -> dict[str, Any]:
        return self.runtime.get_exported_scenario()
