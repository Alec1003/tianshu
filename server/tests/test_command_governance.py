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
                latitude=0.0,
                longitude=0.0,
                range=500.0,
            )
        ]
        self.ships = []
        self.facilities = []
        self.airbases = []
        self.reference_points = []

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
