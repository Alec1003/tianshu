from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
GYM_DIR = ROOT_DIR / "gym"
if str(GYM_DIR) not in sys.path:
    sys.path.insert(0, str(GYM_DIR))

from blade.Game import Game  # noqa: E402
from blade.Scenario import Scenario  # noqa: E402
from blade.Side import Side  # noqa: E402
from blade.units.Aircraft import Aircraft  # noqa: E402
from blade.units.Ship import Ship  # noqa: E402


def _aircraft(unit_id: str) -> Aircraft:
    return Aircraft(
        id=unit_id,
        name=unit_id,
        side_id="blue",
        class_name="Test Aircraft",
        latitude=0.0,
        longitude=0.0,
        altitude=1000.0,
        heading=0.0,
        speed=300.0,
        current_fuel=0.0,
        max_fuel=1000.0,
        fuel_rate=100.0,
        range=100.0,
    )


def _ship(unit_id: str) -> Ship:
    return Ship(
        id=unit_id,
        name=unit_id,
        side_id="blue",
        class_name="Test Ship",
        latitude=0.0,
        longitude=0.0,
        altitude=0.0,
        heading=0.0,
        speed=20.0,
        current_fuel=0.0,
        max_fuel=1000.0,
        fuel_rate=100.0,
        range=100.0,
        route=[[0.0, 0.0]],
    )


def _scenario() -> Scenario:
    return Scenario(
        id="fuel-depletion",
        name="Fuel Depletion",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[Side(id="blue", name="BLUE", color="blue")],
    )


def test_fuel_depletion_removes_adjacent_aircraft_without_skipping() -> None:
    scenario = _scenario()
    scenario.aircraft.extend([_aircraft("a1"), _aircraft("a2")])
    game = Game(current_scenario=scenario)

    game.update_all_aircraft_position()

    assert scenario.aircraft == []


def test_fuel_depletion_removes_adjacent_ships_without_skipping() -> None:
    scenario = _scenario()
    scenario.ships.extend([_ship("s1"), _ship("s2")])
    game = Game(current_scenario=scenario)

    game.update_all_ship_position()

    assert scenario.ships == []
