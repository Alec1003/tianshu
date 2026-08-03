from __future__ import annotations

from typing import Any, Protocol

from app.agent_runtime.agents.profile import AgentProfile


QWENPAW_TEXT_PROMPT = """
You are the TianShu tactical assistant.
You can use the exposed TianShu tools when the operator asks for scenario inspection
or command proposals. Runtime write tools create human approval proposals; they do
not directly mutate the simulation.
For direct tool testing, a user message may be JSON like:
{"tool":"inspect_current_scenario","arguments":{}}
Answer concisely and clearly based on the provided conversation and workspace context.
""".strip()


class PromptManager(Protocol):
    def build(self, request: Any) -> str:
        """Build a system prompt for one agent request."""


class PromptBuilder:
    """Build prompt text from workspace prompt and prepared context."""

    def build(self, request: Any, profile: AgentProfile | None = None) -> str:
        workspace = getattr(request, "workspace", None)
        prompt = getattr(workspace, "agent_prompt", None)
        if profile is not None and profile.system_prompt.strip():
            prompt = profile.system_prompt
        base_prompt = (
            prompt.strip()
            if isinstance(prompt, str) and prompt.strip()
            else QWENPAW_TEXT_PROMPT
        )
        prompt_context = str(getattr(request, "prompt_context", "") or "").strip()
        if not prompt_context:
            return base_prompt
        return f"{base_prompt}\n\n{prompt_context}"


__all__ = ["PromptBuilder", "PromptManager", "QWENPAW_TEXT_PROMPT"]
