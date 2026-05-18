from __future__ import annotations

from typing import Any

from app.ai.models import SkillDefinition


class OpenClawSDKAdapter:
    """Embedded OpenClaw SDK adapter skeleton.

    This module is intentionally in-process and does not launch a separate gateway.
    It provides the SDK integration seam while keeping runtime single-service.
    """

    def __init__(self) -> None:
        self.available = False
        self._client: Any = None
        self._bootstrap()

    def _bootstrap(self) -> None:
        try:
            # Reserved: replace with actual OpenClaw SDK import when SDK package/API
            # is available in your environment.
            #
            # Example:
            # from openclaw import EmbeddedAgent
            # self._client = EmbeddedAgent(...)
            #
            # Keep this in-process (no separate gateway process, no new port).
            self.available = False
        except Exception:
            self.available = False
            self._client = None

    def plan_skill_calls(
        self,
        system_prompt: str,
        command: str,
        skill_definitions: list[SkillDefinition],
    ) -> list[dict[str, Any]] | None:
        if not self.available or self._client is None:
            return None
        # -------------------------- SDK planning extension --------------------------
        # Return a list like:
        # [{"name": "simulation_start", "parameters": {}}, ...]
        # -------------------------------------------------------------------------
        return None

