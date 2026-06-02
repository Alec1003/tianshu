from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ai.command_governance import CommandApprovalQueue
from app.ai.models import StructuredCommandStep


class FakeScenario:
    def __init__(self) -> None:
        self.sides = [SimpleNamespace(id="blue", name="BLUE")]
        self.aircraft = [
            SimpleNamespace(
                id="air-1",
                side_id="blue",
                latitude=0.0,
                longitude=0.0,
                range=500.0,
            )
        ]
        self.ships = []
        self.facilities = [SimpleNamespace(id="target-1", side_id="red")]
        self.airbases = []
        self.reference_points = [
            SimpleNamespace(id="rp-1", side_id="blue"),
            SimpleNamespace(id="rp-2", side_id="blue"),
            SimpleNamespace(id="rp-3", side_id="blue"),
        ]
        self.obstacles = [SimpleNamespace(id="obstacle-1", latitude=0.0, longitude=0.0)]

    def get_aircraft(self, unit_id: str):
        return next((item for item in self.aircraft if item.id == unit_id), None)

    def get_ship(self, unit_id: str):
        return next((item for item in self.ships if item.id == unit_id), None)

    def get_facility(self, unit_id: str):
        return next((item for item in self.facilities if item.id == unit_id), None)

    def get_airbase(self, unit_id: str):
        return next((item for item in self.airbases if item.id == unit_id), None)

    def get_reference_point(self, unit_id: str):
        return next((item for item in self.reference_points if item.id == unit_id), None)

    def get_obstacle(self, unit_id: str):
        return next((item for item in self.obstacles if item.id == unit_id), None)


class FakeRuntime:
    def __init__(self) -> None:
        self.game = SimpleNamespace(current_scenario=FakeScenario())


class FakeRegistry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def has_skill(self, skill: str) -> bool:
        return skill in {
            "simulation_step",
            "move_unit",
            "deploy_aircraft",
            "deploy_obstacle",
            "update_unit_state",
            "create_patrol_mission",
            "create_strike_mission",
            "load_scenario_file",
        }

    def execute(self, skill: str, parameters: dict) -> dict:
        self.calls.append((skill, parameters))
        return {"skill": skill, "ok": True}


def test_pending_proposal_requires_approval_before_runtime_execution() -> None:
    registry = FakeRegistry()
    queue = CommandApprovalQueue(FakeRuntime(), registry)  # type: ignore[arg-type]

    proposal = queue.create_proposal(
        command="advance one second",
        source="regex",
        steps=[
            StructuredCommandStep(
                id="s1",
                skill="simulation_step",
                parameters={"steps": 1},
            )
        ],
    )

    assert proposal.status == "pending"
    assert registry.calls == []

    executed = queue.approve_and_execute(proposal.id)

    assert executed.status == "executed"
    assert registry.calls == [("simulation_step", {"steps": 1})]


def test_blocked_proposal_cannot_be_approved() -> None:
    registry = FakeRegistry()
    queue = CommandApprovalQueue(FakeRuntime(), registry)  # type: ignore[arg-type]

    proposal = queue.create_proposal(
        command="load a server file",
        source="regex",
        steps=[
            StructuredCommandStep(
                id="s1",
                skill="load_scenario_file",
                parameters={"scenario_path": "/tmp/a.json"},
            )
        ],
    )

    assert proposal.status == "blocked"
    assert proposal.adjudication.issues[0].severity == "blocking"
    with pytest.raises(ValueError, match="不能审批执行"):
        queue.approve_and_execute(proposal.id)
    assert registry.calls == []


def test_rule_engine_blocks_missing_unit_target() -> None:
    queue = CommandApprovalQueue(FakeRuntime(), FakeRegistry())  # type: ignore[arg-type]

    proposal = queue.create_proposal(
        command="move missing aircraft",
        source="regex",
        steps=[
            StructuredCommandStep(
                id="s1",
                skill="move_unit",
                parameters={
                    "unit_type": "aircraft",
                    "unit_id": "missing",
                    "route": [[1, 1]],
                },
            )
        ],
    )

    assert proposal.status == "blocked"
    assert any(
        issue.code == "unit_not_found" for issue in proposal.adjudication.issues
    )


def test_rule_engine_allows_obstacle_deploy_and_target_lookup() -> None:
    queue = CommandApprovalQueue(FakeRuntime(), FakeRegistry())  # type: ignore[arg-type]

    deploy = queue.create_proposal(
        command="deploy obstacle",
        source="regex",
        steps=[
            StructuredCommandStep(
                id="s1",
                skill="deploy_obstacle",
                parameters={
                    "class_name": "No-go zone",
                    "latitude": 1.0,
                    "longitude": 2.0,
                    "radius_nm": 15.0,
                },
            )
        ],
    )
    update = queue.create_proposal(
        command="update obstacle",
        source="regex",
        steps=[
            StructuredCommandStep(
                id="s2",
                skill="update_unit_state",
                parameters={
                    "unit_type": "obstacle",
                    "unit_id": "obstacle-1",
                    "patch": {"radiusNm": 20},
                },
            )
        ],
    )

    assert deploy.status == "pending"
    assert update.status == "pending"


def test_pydantic_tool_proposal_recorder_receives_created_proposal() -> None:
    from app.ai.pydantic_agent import AgentDeps, _exec

    queue = CommandApprovalQueue(FakeRuntime(), FakeRegistry())  # type: ignore[arg-type]
    recorded = []
    deps = AgentDeps(
        registry=FakeRegistry(),  # type: ignore[arg-type]
        approval_queue=queue,
        source_command="advance one second",
        proposal_recorder=recorded.append,
    )

    output = _exec(deps, "simulation_step", {"steps": 1})

    assert output["proposalId"] == recorded[0].id
    assert recorded[0].source == "llm_tool"


def test_internal_skill_draft_becomes_reviewed_mission_proposal() -> None:
    from app.ai.internal_skills import build_internal_skill_steps
    from app.ai.models import InternalSkillDraft, InternalSkillMissionDraft

    runtime = FakeRuntime()
    queue = CommandApprovalQueue(runtime, FakeRegistry())  # type: ignore[arg-type]
    draft = InternalSkillDraft(
        name="CAP package",
        side_id="blue",
        missions=[
            InternalSkillMissionDraft(
                type="patrol",
                name="CAP Alpha",
                assigned_unit_ids=["air-1"],
                reference_point_ids=["rp-1", "rp-2", "rp-3"],
            ),
            InternalSkillMissionDraft(
                type="strike",
                name="Strike Red Facility",
                assigned_unit_ids=["air-1"],
                assigned_target_ids=["target-1"],
            ),
        ],
        allow_duplicate_assignments=True,
    )

    steps = build_internal_skill_steps(runtime, draft)  # type: ignore[arg-type]
    proposal = queue.create_proposal(
        command=draft.name,
        source="internal_skill",
        steps=steps,
    )

    assert proposal.status == "pending"
    assert [step.skill for step in proposal.steps] == [
        "create_patrol_mission",
        "create_strike_mission",
    ]
