from __future__ import annotations

from typing import Any

from app.agent_runtime.context.models import AgentContext


class ContextCompressor:
    """Interface placeholder for future LLM/token-aware compression."""

    def compress(self, messages: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for message in messages[-8:]:
            role = str(message.get("role") or "user")
            content = str(message.get("content") or "")
            if content:
                lines.append(f"{role}: {content[:300]}")
        return "\n".join(lines)


class ContextBuilder:
    """Build prompt-ready context text from AgentContext."""

    def __init__(self, compressor: ContextCompressor | None = None) -> None:
        self.compressor = compressor or ContextCompressor()

    def build_prompt_context(self, context: AgentContext) -> str:
        return context.to_prompt_context()

    def recent_message_summary(self, messages: list[dict[str, Any]]) -> str:
        return self.compressor.compress(messages)


def runtime_state_from_workspace(workspace: Any) -> dict[str, Any]:
    try:
        exported = workspace.exported_scenario()
    except Exception:
        return {}
    current = (
        exported.get("currentScenario")
        if isinstance(exported, dict) and isinstance(exported.get("currentScenario"), dict)
        else exported
    )
    if not isinstance(current, dict):
        return {}
    return {
        "scenarioName": current.get("name") or "",
        "aircraft": len(current.get("aircraft") or []),
        "ships": len(current.get("ships") or []),
        "facilities": len(current.get("facilities") or []),
        "airbases": len(current.get("airbases") or []),
        "missions": len(current.get("missions") or []),
        "obstacles": len(current.get("obstacles") or []),
    }
