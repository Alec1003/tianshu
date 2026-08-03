from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent_runtime.tools.base import ToolContext
from app.agent_runtime.tools.registry import ToolRegistry
from app.agent_runtime.tools.runtime_tools import RuntimeSkillTool
from app.ai.models import CommandAdjudicationResult


class FakeSkillRegistry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, dict]] = []

    def capabilities(self):
        return [
            SimpleNamespace(
                name="move_unit",
                description="Move a unit",
                input_schema={
                    "unit_type": {"type": "string"},
                    "unit_id": {"type": "string"},
                    "route": {"type": "array"},
                },
                readonly=False,
            )
        ]

    def execute(self, name: str, parameters: dict, **kwargs):
        self.calls.append((name, parameters, kwargs))
        return {"ok": True, "name": name}


class FakeApprovalQueue:
    def __init__(self) -> None:
        self.created = []

    def create_single_step_proposal(self, **kwargs):
        self.created.append(kwargs)
        return SimpleNamespace(
            id="proposal-1",
            status="pending",
            adjudication=CommandAdjudicationResult(summary="needs review"),
        )


def test_tool_registry_can_register_tools():
    registry = ToolRegistry()
    tool = RuntimeSkillTool(
        name="ping",
        description="Ping",
        input_schema={"type": "object", "properties": {}},
        readonly=True,
    )

    registry.register(tool)

    assert registry.has_tool("ping")
    assert registry.get("ping") is tool


def test_tool_schema_is_generated_from_skill_registry():
    workspace = SimpleNamespace(skill_registry=FakeSkillRegistry())

    registry = ToolRegistry.from_workspace(workspace)
    schema = next(item for item in registry.schemas() if item["name"] == "move_unit")

    assert schema["inputSchema"]["type"] == "object"
    assert schema["inputSchema"]["properties"]["unit_id"]["type"] == "string"
    assert "inspect_current_scenario" in {item["name"] for item in registry.schemas()}


@pytest.mark.asyncio
async def test_readonly_tool_executes_directly():
    workspace = SimpleNamespace(
        skill_registry=FakeSkillRegistry(),
        exported_scenario=lambda: {"name": "Demo", "aircraft": [1], "ships": []},
    )
    registry = ToolRegistry.from_workspace(workspace)

    result = await registry.execute(
        "inspect_current_scenario",
        {},
        ToolContext(
            workspace=workspace,
            skill_registry=workspace.skill_registry,
            scenario_id="scenario-1",
        ),
    )

    assert result["ok"] is True
    assert result["counts"]["aircraft"] == 1


@pytest.mark.asyncio
async def test_write_tool_enters_command_approval_queue():
    skill_registry = FakeSkillRegistry()
    queue = FakeApprovalQueue()
    workspace = SimpleNamespace(skill_registry=skill_registry)
    registry = ToolRegistry.from_workspace(workspace)

    result = await registry.execute(
        "move_unit",
        {"unit_type": "aircraft", "unit_id": "a-1", "route": [[1, 2]]},
        ToolContext(
            workspace=workspace,
            skill_registry=skill_registry,
            approval_queue=queue,
            source_command="move aircraft",
        ),
    )

    assert result["proposalId"] == "proposal-1"
    assert result["requiresApproval"] is True
    assert skill_registry.calls == []
    assert queue.created[0]["skill"] == "move_unit"


@pytest.mark.asyncio
async def test_write_tool_can_call_skill_registry_without_approval_queue():
    skill_registry = FakeSkillRegistry()
    workspace = SimpleNamespace(skill_registry=skill_registry)
    registry = ToolRegistry.from_workspace(workspace)

    result = await registry.execute(
        "move_unit",
        {"unit_type": "aircraft", "unit_id": "a-1", "route": [[1, 2]]},
        ToolContext(
            workspace=workspace,
            skill_registry=skill_registry,
            user_id="user-1",
            scenario_id="scenario-1",
        ),
    )

    assert result == {"ok": True, "name": "move_unit"}
    assert skill_registry.calls[0][0] == "move_unit"
    assert skill_registry.calls[0][2]["source"] == "agent"
