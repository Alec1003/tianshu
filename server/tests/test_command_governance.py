from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ai.command_governance import CommandApprovalQueue
from app.ai.models import StructuredCommandStep
from app.tianshu_runtime.matching import canonical_aircraft_class_name


class FakeScenario:
    def __init__(self) -> None:
        self.sides = [SimpleNamespace(id="blue", name="BLUE", color="blue")]
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

    def get_target(self, unit_id: str):
        return self.get_aircraft(unit_id) or self.get_ship(unit_id) or self.get_facility(unit_id)


class FakeRuntime:
    def __init__(self) -> None:
        self.game = SimpleNamespace(current_scenario=FakeScenario())

    def is_known_aircraft_class(self, class_name: str) -> bool:
        return canonical_aircraft_class_name(class_name) in {
            "F-35A Lightning II",
            "F-22 Raptor",
        }

    def is_known_ship_class(self, class_name: str) -> bool:
        return class_name == "Destroyer"

    def is_known_facility_class(self, class_name: str) -> bool:
        return class_name == "S-400 Triumf"

    def is_known_airbase_class(self, class_name: str) -> bool:
        return class_name == "Al Udeid Air Base"


class FakeRegistry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def has_skill(self, skill: str) -> bool:
        return skill in {
            "simulation_step",
            "move_unit",
            "deploy_aircraft",
            "deploy_ship",
            "deploy_obstacle",
            "update_unit_state",
            "attack_unit",
            "update_weapon_quantity",
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


def test_unknown_aircraft_deploy_is_blocked_before_approval() -> None:
    registry = FakeRegistry()
    queue = CommandApprovalQueue(FakeRuntime(), registry)  # type: ignore[arg-type]

    proposal = queue.create_proposal(
        command="deploy imaginary aircraft",
        source="llm_tool",
        steps=[
            StructuredCommandStep(
                id="s1",
                skill="deploy_aircraft",
                parameters={
                    "class_name": "Imaginary Airframe",
                    "latitude": 10.0,
                    "longitude": 20.0,
                    "side": "blue",
                },
            )
        ],
    )

    assert proposal.status == "blocked"
    assert any(
        issue.code == "unknown_aircraft_class"
        for issue in proposal.adjudication.issues
    )
    with pytest.raises(ValueError):
        queue.approve_and_execute(proposal.id)
    assert registry.calls == []


def test_aircraft_alias_and_localized_blue_side_pass_governance() -> None:
    registry = FakeRegistry()
    runtime = FakeRuntime()
    runtime.game.current_scenario.sides = [
        SimpleNamespace(id="blue", name="蓝方", color="blue")
    ]
    queue = CommandApprovalQueue(runtime, registry)  # type: ignore[arg-type]

    proposal = queue.create_proposal(
        command="deploy blue-side f-22",
        source="llm_tool",
        steps=[
            StructuredCommandStep(
                id="s1",
                skill="deploy_aircraft",
                parameters={
                    "class_name": "F-22",
                    "latitude": 10.0,
                    "longitude": 20.0,
                    "side": "BLUE",
                },
            )
        ],
    )

    assert proposal.status == "pending"
    assert proposal.adjudication.status == "needs_review"
    assert not any(
        issue.code in {"unknown_aircraft_class", "side_not_found"}
        for issue in proposal.adjudication.issues
    )


def test_unknown_ship_deploy_is_blocked_before_approval() -> None:
    registry = FakeRegistry()
    queue = CommandApprovalQueue(FakeRuntime(), registry)  # type: ignore[arg-type]

    proposal = queue.create_proposal(
        command="deploy imaginary ship",
        source="llm_tool",
        steps=[
            StructuredCommandStep(
                id="s1",
                skill="deploy_ship",
                parameters={
                    "class_name": "Imaginary Ship",
                    "latitude": 10.0,
                    "longitude": 20.0,
                    "side": "blue",
                },
            )
        ],
    )

    assert proposal.status == "blocked"
    assert any(
        issue.code == "unknown_ship_class"
        for issue in proposal.adjudication.issues
    )
    with pytest.raises(ValueError):
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


def test_tactical_plan_options_become_grouped_approval_cards() -> None:
    from app.ai.models import TacticalPlanOptionDraft, TacticalPlanStepDraft
    from app.ai.pydantic_agent import AgentDeps, _propose_tactical_plan_options

    queue = CommandApprovalQueue(FakeRuntime(), FakeRegistry())  # type: ignore[arg-type]
    recorded = []
    deps = AgentDeps(
        registry=FakeRegistry(),  # type: ignore[arg-type]
        approval_queue=queue,
        proposal_recorder=recorded.append,
        source_command="生成三个作战方案",
    )

    output = _propose_tactical_plan_options(
        deps,
        [
            TacticalPlanOptionDraft(
                title="快速突击方案",
                label="快速打击",
                description="集中优势兵力，快速摧毁关键目标。",
                advantages=["压缩敌方反应时间"],
                risks=["对航线暴露敏感"],
                steps=[
                    TacticalPlanStepDraft(
                        skill="move_unit",
                        parameters={
                            "unit_type": "aircraft",
                            "unit_id": "air-1",
                            "route": [[1, 1]],
                        },
                        summary="突击编队前出",
                        rationale="占据攻击航线。",
                    ),
                    TacticalPlanStepDraft(
                        skill="attack_unit",
                        parameters={
                            "attacker_type": "aircraft",
                            "attacker_id": "air-1",
                            "target_id": "target-1",
                            "auto": True,
                        },
                        summary="自动分配武器打击目标",
                        rationale="由后端选择可发射武器。",
                        risk="high",
                    ),
                ],
            )
        ],
    )

    assert output["ok"] is True
    assert output["proposalCount"] == 1
    assert len(recorded) == 1
    assert recorded[0].source == "llm_plan"
    assert recorded[0].plan_metadata["title"] == "快速突击方案"
    assert [step.skill for step in recorded[0].steps] == ["move_unit", "attack_unit"]
