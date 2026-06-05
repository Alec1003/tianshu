from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.tianshu_runtime.models import RuntimeEvent
from app.scenarios.models import AarRecord, Scenario
from app.scenarios.training_score import build_training_score


OWNER_ID = uuid.uuid4()
BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _scenario(*, side_id: str = "blue", aircraft_count: int = 4) -> Scenario:
    aircraft = [
        {
            "id": f"{side_id}-air-{index}",
            "name": f"{side_id.upper()} {index}",
            "sideId": side_id,
            "currentFuel": 100.0,
        }
        for index in range(aircraft_count)
    ]
    return Scenario(
        id="scenario-1",
        name="Training Drill",
        description="",
        data={
            "currentSideId": side_id,
            "currentScenario": {
                "id": "runtime-1",
                "name": "Training Drill",
                "startTime": 0,
                "currentTime": 0,
                "duration": 600,
                "sides": [{"id": side_id, "name": "BLUE"}],
                "aircraft": aircraft,
                "ships": [],
                "facilities": [],
                "airbases": [],
            },
        },
        is_template=False,
        owner_id=OWNER_ID,
        status="completed",
        version=1,
    )


def _event(
    event_type: str,
    *,
    index: int,
    action: str = "",
    payload: dict | None = None,
    unit_changes: list[dict] | None = None,
    current_time: int | None = None,
) -> RuntimeEvent:
    category = event_type.split(".", 1)[0] if "." in event_type else "runtime"
    return RuntimeEvent(
        id=f"event-{index}",
        owner_id=OWNER_ID,
        scenario_id="runtime-1",
        event_type=event_type,
        category=category,
        action=action,
        actor="operator",
        summary=event_type,
        payload=payload or {},
        unit_changes=unit_changes or [],
        current_time=current_time,
        created_at=BASE_TIME + timedelta(seconds=index),
    )


def _aar(
    *,
    winner_side_id: str,
    elapsed_seconds: int = 120,
    outcome_reason: str = "objective_completed",
) -> AarRecord:
    return AarRecord(
        id="aar-1",
        scenario_id="scenario-1",
        owner_id=OWNER_ID,
        outcome_reason=outcome_reason,
        winner_side_id=winner_side_id,
        summary={"elapsedSeconds": elapsed_seconds},
        ended_at=BASE_TIME + timedelta(minutes=5),
        created_at=BASE_TIME + timedelta(minutes=5),
    )


def _dimensions(score):
    return {dimension.key: dimension for dimension in score.dimensions}


def test_training_score_rewards_successful_auditable_run() -> None:
    scenario = _scenario()
    events = [
        _event("command.proposed", index=1),
        _event("command.approved", index=2),
        _event(
            "runtime.step",
            index=3,
            action="approved_execution",
            unit_changes=[
                {
                    "change_type": "updated",
                    "unit_type": "aircraft",
                    "unit_id": "blue-air-1",
                    "side_id": "blue",
                    "fields": {"currentFuel": {"before": 100.0, "after": 90.0}},
                }
            ],
            current_time=60,
        ),
        _event("runtime.step", index=4, current_time=120),
        _event("aar.created", index=5),
    ]

    score = build_training_score(scenario, events, [_aar(winner_side_id="blue")])
    dimensions = _dimensions(score)

    assert score.runtime_scenario_id == "runtime-1"
    assert score.overall_score >= 85
    assert score.grade in {"优秀", "良好"}
    assert score.confidence == "high"
    assert dimensions["task_effectiveness"].score == 96
    assert dimensions["force_preservation"].score == 100
    assert score.metrics["executed_count"] == 1


def test_training_score_penalizes_losses_rejections_and_rule_issues() -> None:
    scenario = _scenario(aircraft_count=4)
    rejected_payload = {
        "adjudication": {
            "issues": [
                {"severity": "blocking", "message": "invalid target"},
                {"severity": "warning", "message": "low fuel"},
            ]
        }
    }
    events = [
        _event("command.proposed", index=1),
        _event("command.rejected", index=2, payload=rejected_payload),
        _event(
            "runtime.step",
            index=3,
            unit_changes=[
                {
                    "change_type": "removed",
                    "unit_type": "aircraft",
                    "unit_id": "blue-air-1",
                    "side_id": "blue",
                },
                {
                    "change_type": "removed",
                    "unit_type": "aircraft",
                    "unit_id": "blue-air-2",
                    "side_id": "blue",
                },
                {
                    "change_type": "removed",
                    "unit_type": "aircraft",
                    "unit_id": "red-air-1",
                    "side_id": "red",
                },
                {
                    "change_type": "updated",
                    "unit_type": "aircraft",
                    "unit_id": "blue-air-3",
                    "side_id": "blue",
                    "fields": {
                        "currentFuel": {"before": 100.0, "after": 10.0},
                        "currentQuantity": {"before": 4, "after": 0},
                    },
                },
            ],
            current_time=400,
        ),
    ]

    score = build_training_score(scenario, events, [_aar(winner_side_id="red")])
    dimensions = _dimensions(score)

    assert score.overall_score < 75
    assert dimensions["task_effectiveness"].score == 45
    assert dimensions["force_preservation"].score < 60
    assert dimensions["resource_efficiency"].score < 75
    assert dimensions["rule_compliance"].score < 65
    assert score.metrics["loss_count"] == 2
    assert score.metrics["enemy_loss_count"] == 1


def test_training_score_marks_sparse_data_as_low_confidence() -> None:
    score = build_training_score(_scenario(), [], [])
    dimensions = _dimensions(score)

    assert score.confidence == "low"
    assert score.metrics["event_count"] == 0
    assert dimensions["task_effectiveness"].score == 40
    assert any("样本" in item for item in score.improvements)


def test_training_score_includes_refueling_and_obstacle_evidence() -> None:
    scenario = _scenario()
    scenario.data["currentScenario"]["obstacles"] = [
        {
            "id": "weather-zone",
            "name": "天气约束区",
            "className": "天气约束区",
            "obstacleType": "weather",
        }
    ]
    scenario.data["currentScenario"]["aircraft"][0]["isTanker"] = True
    events = [
        _event(
            "runtime.step",
            index=1,
            payload={
                "state": {
                    "refuelingEvents": [
                        {
                            "receiverId": "blue-air-1",
                            "tankerId": "blue-air-0",
                            "fuelTransferred": 250.0,
                        }
                    ]
                }
            },
            unit_changes=[
                {
                    "change_type": "updated",
                    "unit_type": "aircraft",
                    "unit_id": "blue-air-1",
                    "side_id": "blue",
                    "fields": {"currentFuel": {"before": 100.0, "after": 80.0}},
                }
            ],
        )
    ]

    score = build_training_score(scenario, events, [_aar(winner_side_id="blue")])
    resource = _dimensions(score)["resource_efficiency"]

    assert score.metrics["refueling_event_count"] == 1
    assert score.metrics["refueled_amount"] == 250.0
    assert score.metrics["tanker_count"] == 1
    assert score.metrics["obstacle_count"] == 1
    assert any("空中加油事件=1" == item for item in resource.evidence)
    assert any("障碍/约束区=1" == item for item in resource.evidence)
