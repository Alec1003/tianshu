from __future__ import annotations

from typing import Any

from app.agent_runtime.tools.registry import ToolRegistry

# Ask-mode default read-only tool name prefixes that are always retained.
ASK_DEFAULT_READONLY_CATEGORIES = {
    "scenario.query": {"get_scenario", "get_scenario_statistics", "list_scenarios", "inspect_current_scenario"},
    "runtime.status": {"runtime_status", "runtime_get_outcome", "runtime_export_scenario"},
    "unit.list": {"list_units", "get_unit_detail"},
    "threat.query": {"query_threats"},
}


class CapabilityResolver:
    """Resolve and filter tool registries based on agent execution mode."""

    @staticmethod
    def resolve_tools(
        tool_registry: ToolRegistry,
        mode: str,
    ) -> ToolRegistry:
        # TianShu exposes one command conversation.  Approval behavior is
        # controlled exclusively by the four approval modes on the UI; there
        # is no alternate chat/ask path that can bypass the approval queue.
        return tool_registry

    @staticmethod
    def tool_names_for_log(tool_registry: ToolRegistry) -> str:
        names = tool_registry.tool_names
        return ", ".join(names) if len(names) <= 20 else f"and {len(names) - 20} more"


__all__ = ["CapabilityResolver", "ASK_DEFAULT_READONLY_CATEGORIES"]
