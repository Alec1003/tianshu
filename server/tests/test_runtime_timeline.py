from __future__ import annotations

import asyncio

import pytest

from app.tianshu_runtime.schemas import RuntimeTimelineEventRead
from app.tianshu_runtime.timeline import (
    diff_runtime_unit_changes,
    list_runtime_events,
    record_runtime_event,
)


def _scenario(current_time: int, aircraft: list[dict]) -> dict:
    return {
        "currentSideId": "blue",
        "mapView": {},
        "currentScenario": {
            "id": "scenario-a",
            "name": "Timeline Scenario",
            "startTime": 0,
            "currentTime": current_time,
            "duration": 600,
            "aircraft": aircraft,
            "ships": [],
            "facilities": [],
            "airbases": [],
            "weapons": [],
            "referencePoints": [],
            "sides": [{"id": "blue", "name": "BLUE", "color": "blue"}],
        },
    }


@pytest.mark.anyio
async def test_runtime_event_records_unit_diff_and_lists_by_scenario(
    db_session,
    user,
) -> None:
    before = _scenario(
        10,
        [
            {
                "id": "aircraft-1",
                "name": "Falcon 1",
                "sideId": "blue",
                "latitude": 1.0,
                "longitude": 2.0,
                "currentFuel": 100.0,
                "route": [],
            }
        ],
    )
    after = _scenario(
        13,
        [
            {
                "id": "aircraft-1",
                "name": "Falcon 1",
                "sideId": "blue",
                "latitude": 3.0,
                "longitude": 2.0,
                "currentFuel": 90.0,
                "route": [[3.0, 2.0]],
            },
            {
                "id": "aircraft-2",
                "name": "Falcon 2",
                "sideId": "blue",
                "latitude": 4.0,
                "longitude": 5.0,
                "currentFuel": 100.0,
                "route": [],
            },
        ],
    )

    record = await record_runtime_event(
        db_session,
        user,
        event_type="runtime.step",
        action="step",
        actor="operator",
        summary="仿真推进 3 秒",
        payload={"state": {"steps": 3}},
        before_scenario=before,
        after_scenario=after,
    )

    assert record is not None
    assert record.scenario_id == "scenario-a"
    assert record.current_time == 13
    assert {change["change_type"] for change in record.unit_changes} == {
        "added",
        "updated",
    }
    updated = next(
        change for change in record.unit_changes if change["change_type"] == "updated"
    )
    assert updated["unit_id"] == "aircraft-1"
    assert updated["fields"]["currentFuel"] == {"before": 100.0, "after": 90.0}
    RuntimeTimelineEventRead.model_validate(record)

    rows = await list_runtime_events(db_session, user, scenario_id="scenario-a")
    assert [row.id for row in rows] == [record.id]


@pytest.mark.anyio
async def test_runtime_events_are_listed_in_replay_order(db_session, user) -> None:
    first = await record_runtime_event(
        db_session,
        user,
        event_type="command.proposed",
        action="proposal_created",
        summary="first",
        before_scenario=_scenario(1, []),
        after_scenario=_scenario(1, []),
    )
    await asyncio.sleep(0.001)
    second = await record_runtime_event(
        db_session,
        user,
        event_type="command.approved",
        action="approve_command_proposal",
        summary="second",
        before_scenario=_scenario(2, []),
        after_scenario=_scenario(2, []),
    )

    rows = await list_runtime_events(db_session, user, scenario_id="scenario-a")

    assert first is not None
    assert second is not None
    assert [row.id for row in rows] == [first.id, second.id]


@pytest.mark.anyio
async def test_runtime_event_keeps_zero_current_time(db_session, user) -> None:
    record = await record_runtime_event(
        db_session,
        user,
        event_type="runtime.reset",
        action="reset",
        before_scenario=_scenario(30, []),
        after_scenario=_scenario(0, []),
    )

    assert record is not None
    assert record.current_time == 0


def test_diff_runtime_unit_changes_detects_removed_units() -> None:
    before = _scenario(
        10,
        [{"id": "aircraft-1", "name": "Falcon 1", "sideId": "blue"}],
    )
    after = _scenario(11, [])

    changes = diff_runtime_unit_changes(before, after)

    assert changes == [
        {
            "change_type": "removed",
            "unit_type": "aircraft",
            "unit_id": "aircraft-1",
            "name": "Falcon 1",
            "side_id": "blue",
            "before": {
                "unitType": "aircraft",
                "unitId": "aircraft-1",
                "location": "aircraft",
                "id": "aircraft-1",
                "name": "Falcon 1",
                "sideId": "blue",
            },
        }
    ]
