from __future__ import annotations

from threading import RLock

from app.tianshu_runtime.runtime import TianShuRuntime

from blade.Game import Game
from blade.Relationships import Relationships
from blade.Scenario import Scenario
from blade.Side import Side
from blade.units.Aircraft import Aircraft
from blade.units.Facility import Facility
from blade.units.Ship import Ship
from blade.units.Weapon import Weapon


def _weapon(
    weapon_id: str, quantity: int = 2, target_types: list[str] | None = None
) -> Weapon:
    return Weapon(
        id=weapon_id,
        name=f"Weapon {weapon_id}",
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
        target_types=target_types,
    )


def _scenario() -> Scenario:
    relationships = Relationships()
    relationships.add_hostile("blue", "red")
    return Scenario(
        id="attack-scenario",
        name="Runtime attack",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[
            Side(id="blue", name="BLUE", color="blue"),
            Side(id="red", name="RED", color="red"),
        ],
        aircraft=[
            Aircraft(
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
                weapons=[_weapon("aircraft-weapon", 2)],
            )
        ],
        ships=[
            Ship(
                id="blue-ship",
                name="Blue Ship",
                side_id="blue",
                class_name="Test Ship",
                latitude=0.0,
                longitude=0.0,
                altitude=0.0,
                heading=0.0,
                speed=20.0,
                current_fuel=1000.0,
                max_fuel=1000.0,
                fuel_rate=100.0,
                range=100.0,
                weapons=[_weapon("ship-weapon", 1)],
            )
        ],
        facilities=[
            Facility(
                id="red-facility",
                name="Red Facility",
                side_id="red",
                class_name="SAM",
                latitude=0.0,
                longitude=0.0,
                range=100.0,
                weapons=[],
            )
        ],
        relationships=relationships,
    )


def _runtime_for_scenario(scenario: Scenario) -> TianShuRuntime:
    runtime = TianShuRuntime.__new__(TianShuRuntime)
    runtime._lock = RLock()
    runtime.game = Game(current_scenario=scenario)
    return runtime


def test_runtime_attack_unit_launches_manual_aircraft_weapon() -> None:
    scenario = _scenario()
    runtime = _runtime_for_scenario(scenario)

    state = runtime.attack_unit(
        attacker_type="aircraft",
        attacker_id="blue-aircraft",
        target_id="red-facility",
        weapon_id="aircraft-weapon",
        weapon_quantity=1,
    )

    assert state["attacked"] is True
    assert state["attackerType"] == "aircraft"
    assert state["targetId"] == "red-facility"
    assert state["launched"] == [
        {"weaponId": "aircraft-weapon", "weaponName": "Weapon aircraft-weapon", "quantity": 1}
    ]
    assert len(scenario.weapons) == 1
    assert scenario.weapons[0].target_id == "red-facility"
    assert scenario.aircraft[0].weapons[0].current_quantity == 1


def test_runtime_attack_unit_supports_ship_auto_attack() -> None:
    scenario = _scenario()
    runtime = _runtime_for_scenario(scenario)

    state = runtime.attack_unit(
        attacker_type="ship",
        attacker_id="blue-ship",
        target_id="red-facility",
        auto=True,
    )

    assert state["attacked"] is True
    assert state["auto"] is True
    assert state["launched"] == [
        {"weaponId": "ship-weapon", "weaponName": "Weapon ship-weapon", "quantity": 1}
    ]
    assert len(scenario.weapons) == 1
    assert scenario.ships[0].weapons == []


def test_runtime_attack_unit_rejects_target_outside_declared_weapon_range() -> None:
    scenario = _scenario()
    aircraft = scenario.aircraft[0]
    aircraft.weapons[0].range = 10.0
    scenario.facilities[0].longitude = 0.5
    runtime = _runtime_for_scenario(scenario)

    state = runtime.attack_unit(
        attacker_type="aircraft",
        attacker_id="blue-aircraft",
        target_id="red-facility",
        weapon_id="aircraft-weapon",
        weapon_quantity=1,
    )

    assert state["attacked"] is False
    assert state["launched"] == []
    assert len(scenario.weapons) == 0
    assert aircraft.weapons[0].current_quantity == 2


def test_runtime_attack_unit_rejects_incompatible_weapon_target_domain() -> None:
    scenario = _scenario()
    ship = scenario.ships[0]
    ship.weapons = [_weapon("harpoon", 1, target_types=["ship"])]
    scenario.aircraft.append(
        Aircraft(
            id="red-aircraft",
            name="Red Aircraft",
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
    )
    runtime = _runtime_for_scenario(scenario)

    state = runtime.attack_unit(
        attacker_type="ship",
        attacker_id="blue-ship",
        target_id="red-aircraft",
        weapon_id="harpoon",
        weapon_quantity=1,
    )

    assert state["attacked"] is False
    assert state["launched"] == []
    assert len(scenario.weapons) == 0
    assert ship.weapons[0].current_quantity == 1
