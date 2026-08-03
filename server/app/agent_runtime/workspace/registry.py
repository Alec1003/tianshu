from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any, Protocol

from app.platform.paths import default_scenario_path


TianShuWorkspace: Any | None = None
DEFAULT_RUNTIME_SCENARIO_ID = "__default__"


class UserRef(Protocol):
    id: object


class WorkspaceRegistry:
    """Per-user/scenario workspace registry."""

    def __init__(
        self,
        *,
        scenario_path: Path | None = None,
        external_mcp_servers: str | None = None,
    ) -> None:
        self._lock = RLock()
        self._scenario_path = scenario_path or default_scenario_path()
        self._external_mcp_servers = external_mcp_servers
        self._workspaces: dict[tuple[str, str], Any] = {}

    @classmethod
    def from_env(cls) -> "WorkspaceRegistry":
        from app.config import get_settings  # noqa: PLC0415

        settings = get_settings()
        return cls(
            scenario_path=default_scenario_path(),
            external_mcp_servers=settings.external_mcp_servers,
        )

    def get_workspace(
        self,
        *,
        user_id: str,
        scenario_id: str | None = None,
    ) -> Any:
        context_key = runtime_context_id(scenario_id)
        key = (user_id, context_key)
        with self._lock:
            workspace = self._workspaces.get(key)
            if workspace is None:
                workspace_cls = _workspace_class()
                workspace = workspace_cls.create(
                    user_id=user_id,
                    scenario_id=context_key,
                    scenario_path=self._scenario_path,
                    external_mcp_servers=self._external_mcp_servers,
                )
                self._workspaces[key] = workspace
            return workspace

    def get_workspace_for_user(
        self,
        user: UserRef,
        scenario_id: str | None = None,
    ) -> Any:
        return self.get_workspace(user_id=str(user.id), scenario_id=scenario_id)

    def clear(self) -> None:
        with self._lock:
            workspaces = list(self._workspaces.values())
            self._workspaces.clear()
        for workspace in workspaces:
            workspace.close()


__all__ = ["WorkspaceRegistry"]


def _workspace_class() -> Any:
    global TianShuWorkspace
    if TianShuWorkspace is None:
        from app.agent_runtime.workspace.workspace import TianShuWorkspace as cls

        TianShuWorkspace = cls
    return TianShuWorkspace


def runtime_context_id(scenario_id: str | None = None) -> str:
    value = (scenario_id or "").strip()
    return value[:120] if value else DEFAULT_RUNTIME_SCENARIO_ID
