"""utils 模块的纯函数测试：scenario.data → sides / units / threats 拆解。

MCP tool 的"读"语义建立在这层之上，所以保它稳。
"""

from __future__ import annotations

from app.mcp import utils as u


_SCENARIO = {
    "currentScenario": {
        "id": "demo",
        "startTime": 100,
        "currentTime": 200,
        "duration": 3600,
        "sides": [
            {"id": "blue", "name": "BLUE", "color": "blue", "totalScore": 0},
            {"id": "red", "name": "RED", "color": "red", "totalScore": 0},
        ],
        "aircraft": [
            {
                "id": "a1",
                "name": "F35-1",
                "sideId": "blue",
                "latitude": 10.0,
                "longitude": 20.0,
            },
            {
                "id": "a2",
                "name": "Su57-1",
                "sideId": "red",
                "latitude": 12.0,
                "longitude": 22.0,
            },
        ],
        "ships": [
            {"id": "s1", "name": "DDG-1", "sideId": "blue", "latitude": 11.0, "longitude": 21.0}
        ],
        "facilities": [],
        "airbases": [],
        "weapons": [],
        "referencePoints": [],
        "obstacles": [
            {
                "id": "o1",
                "name": "No-go",
                "sideId": "blue",
                "latitude": 10.5,
                "longitude": 20.5,
            }
        ],
        "missions": [{"id": "m1", "type": "patrol"}],
        "relationships": {
            "hostiles": {"blue": ["red"], "red": ["blue"]},
            "allies": {"blue": [], "red": []},
        },
    },
}


def test_get_current_scenario_unwraps():
    assert u.get_current_scenario(_SCENARIO)["id"] == "demo"


def test_get_current_scenario_passthrough_when_flat():
    flat = {"sides": [], "aircraft": []}
    assert u.get_current_scenario(flat) is flat


def test_get_sides_returns_dicts_only():
    sides = u.get_sides(_SCENARIO)
    assert len(sides) == 2
    assert {s["id"] for s in sides} == {"blue", "red"}


def test_iter_units_collects_all_types_and_injects_marker():
    units = u.iter_units(_SCENARIO)
    types = {un["_unit_type"] for un in units}
    assert "aircraft" in types
    assert "ship" in types
    assert "obstacle" in types
    assert len(units) == 4  # a1 + a2 + s1 + o1


def test_iter_units_filters_by_type():
    only_aircraft = u.iter_units(_SCENARIO, types=("aircraft",))
    assert {u_["id"] for u_ in only_aircraft} == {"a1", "a2"}


def test_find_unit_by_id():
    unit = u.find_unit(_SCENARIO, "s1")
    assert unit is not None
    assert unit["name"] == "DDG-1"
    assert unit["_unit_type"] == "ship"


def test_find_unit_missing_returns_none():
    assert u.find_unit(_SCENARIO, "ghost") is None


def test_hostile_side_ids():
    assert u.hostile_side_ids(_SCENARIO, "blue") == {"red"}
    assert u.hostile_side_ids(_SCENARIO, "red") == {"blue"}
    assert u.hostile_side_ids(_SCENARIO, "ghost") == set()


def test_unit_brief_projection_drops_irrelevant_fields():
    a1 = u.iter_units(_SCENARIO, types=("aircraft",))[0]
    brief = u.unit_brief(a1)
    assert brief["id"] == a1["id"]
    assert brief["type"] == "aircraft"
    assert brief["side_id"] == "blue"
    # No raw fields like _unit_type leaked.
    assert "_unit_type" not in brief
