from __future__ import annotations

import os
from pathlib import Path
from threading import RLock
from typing import Protocol

from app.ai.bridge import AICCOpenClawBridge, DEFAULT_SCENARIO_PATH
from app.aicc_runtime.runtime import AICCRuntime
from app.aicc_runtime.persistence import runtime_context_id


class UserRef(Protocol):
    id: object


class AICCBridgeRegistry:
    """Per-user bridge/runtime registry for the FastAPI process.

    Each bridge owns a skill registry, commander agent, and AICCRuntime. Keeping
    one bridge per user prevents live scenario mutations from crossing account
    boundaries while preserving the current single-runtime programming model
    inside each user session.
    """

    def __init__(
        self,
        *,
        scenario_path: Path = DEFAULT_SCENARIO_PATH,
        llm_model: str = "",
        llm_api_key: str = "",
        llm_base_url: str = "",
    ) -> None:
        self._lock = RLock()
        self._scenario_path = scenario_path
        self._llm_model = llm_model
        self._llm_api_key = llm_api_key
        self._llm_base_url = llm_base_url
        self._bridges: dict[tuple[str, str], AICCOpenClawBridge] = {}

    @classmethod
    def from_env(cls) -> "AICCBridgeRegistry":
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

    @staticmethod
    def _user_key(user: UserRef) -> str:
        return str(user.id)

    def get_bridge_for_user(
        self,
        user: UserRef,
        scenario_id: str | None = None,
    ) -> AICCOpenClawBridge:
        user_key = self._user_key(user)
        context_key = runtime_context_id(scenario_id)
        bridge_key = (user_key, context_key)
        with self._lock:
            bridge = self._bridges.get(bridge_key)
            if bridge is None:
                bridge = AICCOpenClawBridge(
                    scenario_path=self._scenario_path,
                    llm_model=self._llm_model,
                    llm_api_key=self._llm_api_key,
                    llm_base_url=self._llm_base_url,
                )
                self._bridges[bridge_key] = bridge
            return bridge

    def get_runtime_for_user(
        self,
        user: UserRef,
        scenario_id: str | None = None,
    ) -> AICCRuntime:
        return self.get_bridge_for_user(user, scenario_id=scenario_id).runtime

    def clear(self) -> None:
        with self._lock:
            self._bridges.clear()
