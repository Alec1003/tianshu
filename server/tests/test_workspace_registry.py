from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.agent_runtime.workspace.registry import WorkspaceRegistry
from app.ai import bridge_registry as bridge_registry_mod
from app.ai.bridge_registry import TianShuBridgeRegistry


class FakeWorkspace:
    created: list["FakeWorkspace"] = []

    def __init__(self, *, user_id, scenario_id, scenario_path, external_mcp_servers):
        self.user_id = user_id
        self.scenario_id = scenario_id
        self.scenario_path = scenario_path
        self.external_mcp_servers = external_mcp_servers
        self.runtime = SimpleNamespace(id=f"runtime:{user_id}:{scenario_id}")
        self.closed = False
        FakeWorkspace.created.append(self)

    @classmethod
    def create(cls, **kwargs):
        return cls(**kwargs)

    def close(self):
        self.closed = True


class FakeBridge:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.workspace = kwargs.get("workspace") or FakeWorkspace.create(
            user_id="legacy", scenario_id="legacy",
            scenario_path=kwargs.get("scenario_path", Path(".")),
            external_mcp_servers=kwargs.get("external_mcp_servers", ""),
        )
        self.runtime = self.workspace.runtime


def test_workspace_registry_reuses_user_scenario_workspace(monkeypatch):
    from app.agent_runtime.workspace import registry as registry_mod

    FakeWorkspace.created.clear()
    monkeypatch.setattr(registry_mod, "TianShuWorkspace", FakeWorkspace)
    registry = WorkspaceRegistry(
        scenario_path=Path("scenario.json"),
        external_mcp_servers="[]",
    )

    alpha_1 = registry.get_workspace(user_id="user-a", scenario_id="alpha")
    alpha_2 = registry.get_workspace(user_id="user-a", scenario_id="alpha")
    bravo = registry.get_workspace(user_id="user-a", scenario_id="bravo")
    other_user = registry.get_workspace(user_id="user-b", scenario_id="alpha")

    assert alpha_1 is alpha_2
    assert alpha_1 is not bravo
    assert alpha_1 is not other_user
    assert alpha_1.runtime.id == "runtime:user-a:alpha"


def test_workspace_registry_clear_closes_workspaces(monkeypatch):
    from app.agent_runtime.workspace import registry as registry_mod

    FakeWorkspace.created.clear()
    monkeypatch.setattr(registry_mod, "TianShuWorkspace", FakeWorkspace)
    registry = WorkspaceRegistry(scenario_path=Path("scenario.json"))
    workspace = registry.get_workspace(user_id="user-a", scenario_id="alpha")

    registry.clear()

    assert workspace.closed is True


def test_bridge_registry_uses_workspace_registry(monkeypatch):
    FakeWorkspace.created.clear()
    monkeypatch.setattr(
        bridge_registry_mod,
        "WorkspaceRegistry",
        lambda **kwargs: WorkspaceRegistry(**kwargs),
    )
    from app.agent_runtime.workspace import registry as registry_mod

    monkeypatch.setattr(registry_mod, "TianShuWorkspace", FakeWorkspace)
    monkeypatch.setattr(bridge_registry_mod, "TianShuOpenClawBridge", FakeBridge)
    registry = TianShuBridgeRegistry(scenario_path=Path("scenario.json"))
    user = SimpleNamespace(id="user-a")

    bridge_1 = registry.get_bridge_for_user(user, scenario_id="alpha")
    bridge_2 = registry.get_bridge_for_user(user, scenario_id="alpha")
    bridge_3 = registry.get_bridge_for_user(user, scenario_id="bravo")

    assert bridge_1 is bridge_2
    assert bridge_1 is not bridge_3
    assert bridge_1.workspace is registry.workspace_registry.get_workspace_for_user(
        user,
        scenario_id="alpha",
    )
    assert registry.get_runtime_for_user(user, scenario_id="alpha") is bridge_1.runtime


def test_pydantic_backend_default_is_unchanged(monkeypatch):
    from app.api import ai as ai_api
    from app.config import get_settings

    monkeypatch.delenv("TIANSHU_AGENT_BACKEND", raising=False)
    get_settings.cache_clear()

    assert get_settings().agent_backend == "qwenpaw"
    get_settings.cache_clear()
