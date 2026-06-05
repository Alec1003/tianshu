from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from sqlalchemy import select

from app.scenarios import seed as scenario_seed
from app.scenarios.models import Scenario


ROOT_DIR = Path(__file__).resolve().parents[2]

COMBAT_COLLECTIONS = ("aircraft", "ships", "facilities", "airbases")


def _distance_km(first: dict, second: dict) -> float:
    radius_km = 6371
    first_lat = math.radians(first["latitude"])
    second_lat = math.radians(second["latitude"])
    delta_lat = second_lat - first_lat
    delta_lon = math.radians(second["longitude"] - first["longitude"])
    half_chord = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(first_lat) * math.cos(second_lat) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * radius_km * math.asin(math.sqrt(half_chord))


def _combat_units_by_side(current: dict) -> dict[str, list[dict]]:
    units_by_side: dict[str, list[dict]] = {side["id"]: [] for side in current["sides"]}
    for collection in COMBAT_COLLECTIONS:
        for unit in current.get(collection, []):
            if not {"latitude", "longitude", "sideId"} <= unit.keys():
                continue
            units_by_side.setdefault(unit["sideId"], []).append(unit)
    return units_by_side


def _minimum_hostile_combat_distance_km(current: dict) -> float:
    units_by_side = _combat_units_by_side(current)
    minimum = math.inf
    for side_id, hostile_ids in current["relationships"]["hostiles"].items():
        for hostile_id in hostile_ids:
            if side_id > hostile_id:
                continue
            for first in units_by_side.get(side_id, []):
                for second in units_by_side.get(hostile_id, []):
                    minimum = min(minimum, _distance_km(first, second))
    return minimum


def test_template_specs_are_curated_historical_cases() -> None:
    stems = [stem for stem, _, _ in scenario_seed.template_specs()]

    assert stems == [
        "midway_1942",
        "overlord_1944",
        "desert_storm_1991",
    ]
    assert "SCS" not in stems
    assert "default_scenario" not in stems
    assert "blank_scenario" not in stems


def test_template_files_exist_and_have_basic_scenario_shape() -> None:
    scenario_dir = ROOT_DIR / "client" / "src" / "scenarios"
    minimum_counts = {
        "midway_1942": {
            "aircraft": 10,
            "ships": 8,
            "facilities": 3,
            "missions": 8,
        },
        "overlord_1944": {
            "aircraft": 10,
            "ships": 5,
            "facilities": 7,
            "missions": 8,
        },
        "desert_storm_1991": {
            "aircraft": 12,
            "facilities": 8,
            "airbases": 5,
            "missions": 10,
        },
    }

    for stem, name, description in scenario_seed.template_specs():
        data = json.loads((scenario_dir / f"{stem}.json").read_text(encoding="utf-8"))
        current = data["currentScenario"]
        expected = minimum_counts[stem]

        assert current["name"] == name
        assert description
        assert len(current["sides"]) >= 2
        assert current["relationships"]["hostiles"]
        assert current["doctrine"]
        assert "historicalCase" in current
        assert current["historicalCase"]["complexity"]
        for collection, minimum in expected.items():
            assert len(current[collection]) >= minimum


def test_template_combat_units_start_far_enough_apart() -> None:
    scenario_dir = ROOT_DIR / "client" / "src" / "scenarios"
    minimum_hostile_distances_km = {
        "midway_1942": 150,
        "overlord_1944": 45,
        "desert_storm_1991": 180,
    }

    for stem, _, _ in scenario_seed.template_specs():
        data = json.loads((scenario_dir / f"{stem}.json").read_text(encoding="utf-8"))
        current = data["currentScenario"]

        assert (
            _minimum_hostile_combat_distance_km(current)
            >= minimum_hostile_distances_km[stem]
        )


def test_overlord_naval_gunfire_mission_assigns_ships_not_aircraft() -> None:
    scenario_dir = ROOT_DIR / "client" / "src" / "scenarios"
    data = json.loads(
        (scenario_dir / "overlord_1944.json").read_text(encoding="utf-8")
    )
    current = data["currentScenario"]
    ship_ids = {ship["id"] for ship in current["ships"]}
    aircraft_ids = {aircraft["id"] for aircraft in current["aircraft"]}
    mission = next(
        mission
        for mission in current["missions"]
        if mission["id"] == "overlord-extra-mission-naval-gunfire"
    )

    assert mission["assignedUnitIds"] == [
        "overlord-ship-nevada",
        "overlord-extra-ship-augusta",
        "overlord-extra-ship-texas",
    ]
    assert set(mission["assignedUnitIds"]) <= ship_ids
    assert set(mission["assignedUnitIds"]).isdisjoint(aircraft_ids)


@pytest.mark.asyncio
async def test_retire_legacy_templates_only_removes_old_system_templates(db_session):
    db_session.add_all(
        [
            Scenario(
                id="tpl-SCS",
                name="Old SCS",
                description="old",
                data={},
                is_template=True,
                owner_id=None,
                status="draft",
            ),
            Scenario(
                id="tpl-default_scenario",
                name="Old Demo",
                description="old",
                data={},
                is_template=True,
                owner_id=None,
                status="draft",
            ),
            Scenario(
                id="tpl-blank_scenario",
                name="Old Blank",
                description="old",
                data={},
                is_template=True,
                owner_id=None,
                status="draft",
            ),
            Scenario(
                id="tpl-midway_1942",
                name="Midway",
                description="keep",
                data={},
                is_template=True,
                owner_id=None,
                status="draft",
            ),
        ]
    )
    await db_session.commit()

    await scenario_seed._retire_legacy_templates(db_session)
    await db_session.commit()

    rows = await db_session.execute(select(Scenario.id).order_by(Scenario.id))
    assert rows.scalars().all() == ["tpl-midway_1942"]
