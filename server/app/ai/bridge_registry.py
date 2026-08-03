from __future__ import annotations

import inspect
from pathlib import Path
from threading import RLock
from typing import Protocol

from app.ai.bridge import TianShuOpenClawBridge, DEFAULT_SCENARIO_PATH
from app.agent_runtime.workspace.registry import WorkspaceRegistry
from app.tianshu_runtime.runtime import TianShuRuntime
from app.tianshu_runtime.persistence import runtime_context_id
from app.platform.paths import default_scenario_path


class UserRef(Protocol):
    id: object


class TianShuBridgeRegistry:
    """Per-user bridge/runtime registry for the FastAPI process.

    Each bridge owns a skill registry, commander agent, and TianShuRuntime. Keeping
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
        external_mcp_servers: str | None = None,
    ) -> None:
        self._lock = RLock()
        self._scenario_path = scenario_path
        self._llm_model = llm_model
        self._llm_api_key = llm_api_key
        self._llm_base_url = llm_base_url
        self._external_mcp_servers = external_mcp_servers
        self.workspace_registry = WorkspaceRegistry(
            scenario_path=scenario_path,
            external_mcp_servers=external_mcp_servers,
        )
        self._bridges: dict[tuple[str, str], TianShuOpenClawBridge] = {}

    @classmethod
    def from_env(cls) -> "TianShuBridgeRegistry":
        from app.config import get_settings  # noqa: PLC0415

        settings = get_settings()
        return cls(
            scenario_path=default_scenario_path(),
            llm_model=settings.llm_model,
            llm_api_key=settings.llm_api_key,
            llm_base_url=settings.llm_base_url,
            external_mcp_servers=settings.external_mcp_servers,
        )

    @staticmethod
    def _user_key(user: UserRef) -> str:
        return str(user.id)

    def get_bridge_for_user(
        self,
        user: UserRef,
        scenario_id: str | None = None,
    ) -> TianShuOpenClawBridge:
        user_key = self._user_key(user)
        context_key = runtime_context_id(scenario_id)
        bridge_key = (user_key, context_key)
        with self._lock:
            bridge = self._bridges.get(bridge_key)
            if bridge is None:
                if self._bridge_supports_workspace():
                    workspace = self.workspace_registry.get_workspace(
                        user_id=user_key,
                        scenario_id=context_key,
                    )
                    bridge = self._create_bridge(workspace)
                else:
                    bridge = self._create_legacy_bridge()
                self._bridges[bridge_key] = bridge
            return bridge

    def get_runtime_for_user(
        self,
        user: UserRef,
        scenario_id: str | None = None,
    ) -> TianShuRuntime:
        user_key = self._user_key(user)
        context_key = runtime_context_id(scenario_id)
        bridge = self._bridges.get((user_key, context_key))
        if bridge is not None:
            return bridge.runtime
        return self.workspace_registry.get_workspace_for_user(
            user,
            scenario_id=scenario_id,
        ).runtime

    def clear(self) -> None:
        with self._lock:
            self._bridges.clear()
        self.workspace_registry.clear()

    def _create_bridge(self, workspace) -> TianShuOpenClawBridge:
        kwargs = {
            "scenario_path": self._scenario_path,
            "llm_model": self._llm_model,
            "llm_api_key": self._llm_api_key,
            "llm_base_url": self._llm_base_url,
            "external_mcp_servers": self._external_mcp_servers,
            "workspace": workspace,
        }
        return TianShuOpenClawBridge(**kwargs)

    def _create_legacy_bridge(self) -> TianShuOpenClawBridge:
        return TianShuOpenClawBridge(
            scenario_path=self._scenario_path,
            llm_model=self._llm_model,
            llm_api_key=self._llm_api_key,
            llm_base_url=self._llm_base_url,
        )

    @staticmethod
    def _bridge_supports_workspace() -> bool:
        try:
            return "workspace" in inspect.signature(TianShuOpenClawBridge).parameters
        except (TypeError, ValueError):
            return True
