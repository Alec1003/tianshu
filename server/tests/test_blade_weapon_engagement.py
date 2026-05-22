from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
GYM_DIR = ROOT_DIR / "gym"
if str(GYM_DIR) not in sys.path:
    sys.path.insert(0, str(GYM_DIR))

from blade.engine.weaponEngagement import weapon_can_engage_target  # noqa: E402
from blade.Game import Game  # noqa: E402
from blade.Relationships import Relationships  # noqa: E402
from blade.Scenario import Scenario  # noqa: E402
from blade.Side import Side  # noqa: E402
from blade.units.Aircraft import Aircraft  # noqa: E402
from blade.units.Facility import Facility  # noqa: E402
from blade.units.Weapon import Weapon  # noqa: E402


def test_weapon_can_engage_target_on_exact_range_boundary() -> None:
    target = Aircraft(
        id="target",
        name="Target",
        side_id="red",
        class_name="Test Aircraft",
        latitude=0.0,
        longitude=0.0,
        altitude=1000.0,
        heading=0.0,
        speed=300.0,
        current_fuel=1000.0,
        max_fuel=1000.0,
        fuel_rate=100.0,
        range=100.0,
    )
    weapon = Weapon(
        id="weapon",
        name="Weapon",
        side_id="blue",
        class_name="Test Weapon",
        latitude=0.0,
        longitude=0.0,
        altitude=1000.0,
        heading=0.0,
        speed=0.0,
        current_fuel=0.0,
        max_fuel=0.0,
        fuel_rate=1.0,
        range=0.0,
    )

    assert weapon_can_engage_target(target, weapon) is True


def _surface_weapon(quantity: int = 2) -> Weapon:
    return Weapon(
        id="surface-weapon",
        name="Surface Weapon",
        side_id="blue",
        class_name="Test Weapon",
        latitude=0.0,
        longitude=0.0,
        altitude=1000.0,
        heading=0.0,
        speed=1000.0,
        current_fuel=1.0,
        max_fuel=1.0,
        fuel_rate=1.0,
        range=1000.0,
        current_quantity=quantity,
        max_quantity=quantity,
    )


def test_aircraft_surface_engagement_attacks_hostile_surface_target_once() -> None:
    aircraft = Aircraft(
        id="blue-aircraft",
        name="Blue Aircraft",
        side_id="blue",
        class_name="Test Aircraft",
        latitude=0.0,
        longitude=0.0,
        altitude=1000.0,
        heading=0.0,
        speed=300.0,
        current_fuel=1000.0,
        max_fuel=1000.0,
        fuel_rate=100.0,
        range=100.0,
        weapons=[_surface_weapon()],
    )
    facility = Facility(
        id="red-sam",
        name="Red SAM",
        side_id="red",
        class_name="SAM",
        latitude=0.0,
        longitude=0.0,
        range=100.0,
        weapons=[],
    )
    relationships = Relationships()
    relationships.add_hostile("blue", "red")
    scenario = Scenario(
        id="s1",
        name="Surface engagement",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[
            Side(id="blue", name="BLUE", color="blue"),
            Side(id="red", name="RED", color="red"),
        ],
        aircraft=[aircraft],
        facilities=[facility],
        relationships=relationships,
    )
    game = Game(current_scenario=scenario)

    game.aircraft_surface_engagement()

    assert len(scenario.weapons) == 1
    assert aircraft.weapons[0].current_quantity == 1
    assert scenario.weapons[-1].target_id == "red-sam"

    game.aircraft_surface_engagement()

    assert len(scenario.weapons) == 1
