from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
GYM_DIR = ROOT_DIR / "gym"
if str(GYM_DIR) not in sys.path:
    sys.path.insert(0, str(GYM_DIR))

from blade.Game import Game  # noqa: E402
from blade.Scenario import Scenario  # noqa: E402


def _by_id(items: list[dict[str, Any]], item_id: str) -> dict[str, Any]:
    for item in items:
        if item["id"] == item_id:
            return item
    raise AssertionError(f"item {item_id!r} not found")


def _mark_objective(items: list[dict[str, Any]]) -> str:
    assert items
    items[0]["isObjective"] = True
    return str(items[0]["id"])


def _load_fixture() -> tuple[dict[str, Any], dict[str, str]]:
    data = json.loads((ROOT_DIR / "client/src/scenarios/SCS.json").read_text())
    scenario = data["currentScenario"]
    scenario.setdefault("doctrine", {side["id"]: {} for side in scenario["sides"]})

    ids = {
        "aircraft": _mark_objective(scenario["aircraft"]),
        "ship": _mark_objective(scenario["ships"]),
        "facility": _mark_objective(scenario["facilities"]),
        "airbase": _mark_objective(scenario["airbases"]),
        "airbase_aircraft": _mark_objective(scenario["airbases"][0]["aircraft"]),
        "ship_aircraft": _mark_objective(scenario["ships"][0]["aircraft"]),
    }
    return data, ids


def test_blade_load_export_preserves_is_objective_flags() -> None:
    data, ids = _load_fixture()

    game = Game(current_scenario=Scenario())
    game.load_scenario(json.dumps(data))

    assert game.current_scenario.get_aircraft(ids["aircraft"]).is_objective is True
    assert game.current_scenario.get_ship(ids["ship"]).is_objective is True
    assert game.current_scenario.get_facility(ids["facility"]).is_objective is True
    assert game.current_scenario.get_airbase(ids["airbase"]).is_objective is True

    exported = game.export_scenario()["currentScenario"]
    assert _by_id(exported["aircraft"], ids["aircraft"])["isObjective"] is True
    assert _by_id(exported["ships"], ids["ship"])["isObjective"] is True
    assert _by_id(exported["facilities"], ids["facility"])["isObjective"] is True
    assert _by_id(exported["airbases"], ids["airbase"])["isObjective"] is True

    exported_airbase = _by_id(exported["airbases"], ids["airbase"])
    assert (
        _by_id(exported_airbase["aircraft"], ids["airbase_aircraft"])["isObjective"]
        is True
    )

    exported_ship = _by_id(exported["ships"], ids["ship"])
    assert _by_id(exported_ship["aircraft"], ids["ship_aircraft"])["isObjective"] is True
