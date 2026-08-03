from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from app.agent_runtime.capabilities import CapabilityRegistry
from app.agent_runtime.capabilities.models import Capability
from app.agent_runtime.tools.base import ToolContext


@dataclass
class SkillCapability:
    name: str
    description: str
    input_schema: dict
    readonly: bool = False


class FakeSkillRegistry:
    def __init__(self) -> None:
        self.executed = []

    def capabilities(self):
        return [
            SkillCapability(
                name="query_status",
                description="Query status",
                input_schema={"type": "object", "properties": {}},
                readonly=True,
            ),
            SkillCapability(
                name="move_unit",
                description="Move unit",
                input_schema={"unit_id": {"type": "string"}},
                readonly=False,
            ),
        ]

    def execute(self, name, arguments, **kwargs):
        self.executed.append((name, arguments, kwargs))
        return {"ok": True, "skill": name, "arguments": arguments}


class FakeDriverRegistry:
    def __init__(self) -> None:
        self.executed = []

    async def capabilities(self):
        return [
            Capability(
                name="external_lookup",
                description="External lookup",
                source="driver",
                provider="mcp",
                permission="read",
                input_schema={"type": "object", "properties": {}},
            )
        ]

    async def execute(self, provider, capability, arguments):
        self.executed.append((provider, capability, arguments))
        return {"ok": True, "driver": provider, "capability": capability}


class FakeApprovalQueue:
    def create_single_step_proposal(self, **kwargs):
        adjudication = SimpleNamespace(model_dump=lambda mode="json": {"ok": True})
        return SimpleNamespace(id="proposal-1", status="blocked", adjudication=adjudication)


@pytest.mark.asyncio
async def test_capability_discovery_from_skill_and_driver():
    workspace = SimpleNamespace(
        skill_registry=FakeSkillRegistry(),
        driver_registry=FakeDriverRegistry(),
    )
    registry = CapabilityRegistry.from_workspace(workspace)

    await registry.load_from_workspace(workspace)

    names = {capability.name for capability in registry.capabilities()}
    assert {"query_status", "move_unit", "external_lookup", "inspect_current_scenario", "list_capabilities"} <= names
    assert registry.get("move_unit").permission == "write"
    assert registry.get("external_lookup").source == "driver"


@pytest.mark.asyncio
async def test_skill_capability_write_goes_to_approval_queue():
    workspace = SimpleNamespace(
        skill_registry=FakeSkillRegistry(),
        driver_registry=None,
    )
    registry = CapabilityRegistry.from_workspace(workspace)
    await registry.load_from_workspace(workspace)
    context = ToolContext(
        workspace=workspace,
        skill_registry=workspace.skill_registry,
        capability_registry=registry,
        approval_queue=FakeApprovalQueue(),
        user_id="user-a",
        scenario_id="scenario-a",
        source_command="move",
    )

    result = await registry.execute("move_unit", {"unit_id": "u-1"}, context)

    assert result["proposalId"] == "proposal-1"
    assert result["requiresApproval"] is True
    assert workspace.skill_registry.executed == []


@pytest.mark.asyncio
async def test_driver_capability_executes_driver_directly_when_readonly():
    driver_registry = FakeDriverRegistry()
    workspace = SimpleNamespace(
        skill_registry=FakeSkillRegistry(),
        driver_registry=driver_registry,
    )
    registry = CapabilityRegistry.from_workspace(workspace)
    await registry.load_from_workspace(workspace)
    context = ToolContext(
        workspace=workspace,
        skill_registry=workspace.skill_registry,
        capability_registry=registry,
    )

    result = await registry.execute("external_lookup", {"q": "x"}, context)

    assert result["ok"] is True
    assert driver_registry.executed == [("mcp", "external_lookup", {"q": "x"})]
