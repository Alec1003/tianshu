from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.agent_runtime.workspace.workspace import TianShuWorkspace
from app.ai.bridge import TianShuOpenClawBridge


class FakeRuntime:
    def __init__(self, scenario_path):
        self.scenario_path = scenario_path

    def get_exported_scenario(self):
        return {"name": "fake"}


class FakeSkillRegistry:
    def __init__(self, runtime):
        self.runtime = runtime

    def capabilities(self):
        return []


class FakeApprovalQueue:
    def __init__(self, runtime, registry):
        self.runtime = runtime
        self.registry = registry


class FakeMCPClient:
    @classmethod
    def from_env(cls, _raw=None):
        return cls()


class FakeDriverRegistry:
    @classmethod
    def from_workspace(cls, workspace):
        instance = cls()
        instance.workspace = workspace
        return instance


class FakeToolRegistry:
    @classmethod
    def from_workspace(cls, workspace):
        instance = cls()
        instance.workspace = workspace
        return instance

    def tools(self):
        return ["tool-a"]

    def schemas(self):
        return [{"name": "tool-a"}]


class FakeAgentRuntime:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeAgent:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _patch_workspace_dependencies(monkeypatch):
    from app.agent_runtime.workspace import workspace as ws_mod

    monkeypatch.setattr(ws_mod, "TianShuRuntime", FakeRuntime)
    monkeypatch.setattr(ws_mod, "TianShuSkillRegistry", FakeSkillRegistry)
    monkeypatch.setattr(ws_mod, "CommandApprovalQueue", FakeApprovalQueue)
    monkeypatch.setattr(ws_mod, "MCPClientSkeleton", FakeMCPClient)
    monkeypatch.setattr(ws_mod, "DriverRegistry", FakeDriverRegistry)
    monkeypatch.setattr(ws_mod, "ToolRegistry", FakeToolRegistry)
    monkeypatch.setattr(ws_mod, "TianShuRuntimeOrchestrator", FakeAgentRuntime)
    monkeypatch.setattr(ws_mod, "TianShuCommanderAgent", FakeAgent)


def test_workspace_owns_runtime_and_agent_services(monkeypatch):
    _patch_workspace_dependencies(monkeypatch)

    workspace = TianShuWorkspace.create(
        user_id="user-a",
        scenario_id="scenario-a",
        scenario_path=Path("scenario.json"),
    )

    assert isinstance(workspace.runtime, FakeRuntime)
    assert workspace.skill_registry.runtime is workspace.runtime
    assert workspace.command_approvals.runtime is workspace.runtime
    assert workspace.agent_runtime.kwargs["context_manager"] is workspace.context_manager
    assert workspace.driver_registry.workspace is workspace
    assert workspace.tool_registry.workspace is workspace
    assert workspace.get_tools() == ["tool-a"]
    assert workspace.get_memory() is workspace.memory_manager
    assert workspace.get_context() is workspace.context_manager


def test_bridge_facade_delegates_to_workspace():
    workspace = SimpleNamespace(
        runtime=object(),
        skill_registry=object(),
        command_approvals=object(),
        mcp_client=object(),
        sdk_adapter=object(),
        memory_manager=object(),
        context_manager=object(),
        agent_runtime=object(),
        agent_registry=object(),
        capability_registry=object(),
        workflow_orchestrator=object(),
        driver_registry=object(),
        tool_registry=object(),
        agent=object(),
    )

    bridge = TianShuOpenClawBridge(workspace=workspace)

    assert bridge.workspace is workspace
    assert bridge.runtime is workspace.runtime
    assert bridge.skill_registry is workspace.skill_registry
    assert bridge.command_approvals is workspace.command_approvals
    assert bridge.agent_runtime is workspace.agent_runtime


def test_bridge_exported_scenario_uses_workspace_runtime():
    runtime = SimpleNamespace(get_exported_scenario=lambda: {"ok": True})
    workspace = SimpleNamespace(
        runtime=runtime,
        skill_registry=object(),
        command_approvals=object(),
        mcp_client=object(),
        sdk_adapter=object(),
        memory_manager=object(),
        context_manager=object(),
        agent_runtime=object(),
        agent_registry=object(),
        capability_registry=object(),
        workflow_orchestrator=object(),
        driver_registry=object(),
        tool_registry=object(),
        agent=object(),
    )
    bridge = TianShuOpenClawBridge(workspace=workspace)

    assert bridge.exported_scenario() == {"ok": True}
