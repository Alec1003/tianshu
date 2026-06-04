from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
GYM_DIR = ROOT_DIR / "gym"
if str(GYM_DIR) not in sys.path:
    sys.path.insert(0, str(GYM_DIR))

from blade.engine.weaponEngagement import (  # noqa: E402
    is_threat_detected,
    launch_weapon,
    weapon_can_engage_target,
)
from blade.Game import Game  # noqa: E402
from blade.Relationships import Relationships  # noqa: E402
from blade.Scenario import Scenario  # noqa: E402
from blade.Side import Side  # noqa: E402
from blade.units.Aircraft import Aircraft  # noqa: E402
from blade.units.Facility import Facility  # noqa: E402
from blade.units.Obstacle import Obstacle  # noqa: E402
from blade.units.Ship import Ship  # noqa: E402
from blade.units.Weapon import Weapon  # noqa: E402
from blade.utils.constants import NAUTICAL_MILES_TO_METERS  # noqa: E402
from blade.utils.utils import get_distance_between_two_points, get_next_coordinates  # noqa: E402
from blade.mission.StrikeMission import StrikeMission  # noqa: E402


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


def test_weapon_engagement_uses_declared_range_not_fuel_endurance() -> None:
    target = Facility(
        id="target",
        name="Target",
        side_id="red",
        class_name="Radar",
        latitude=0.0,
        longitude=0.5,
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
        speed=1000.0,
        current_fuel=1.0,
        max_fuel=1.0,
        fuel_rate=1.0,
        range=10.0,
    )

    assert weapon_can_engage_target(target, weapon) is False


def test_manual_aircraft_attack_rejects_target_outside_declared_weapon_range() -> None:
    weapon = _surface_weapon(quantity=1)
    weapon.range = 10.0
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
        weapons=[weapon],
    )
    target = Facility(
        id="red-site",
        name="Red Site",
        side_id="red",
        class_name="Radar",
        latitude=0.0,
        longitude=0.5,
        range=100.0,
        weapons=[],
    )
    relationships = Relationships()
    relationships.add_hostile("blue", "red")
    scenario = Scenario(
        id="s1",
        name="Out of declared weapon range",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[
            Side(id="blue", name="BLUE", color="blue"),
            Side(id="red", name="RED", color="red"),
        ],
        aircraft=[aircraft],
        facilities=[target],
        relationships=relationships,
    )
    game = Game(current_scenario=scenario)

    game.handle_aircraft_attack("blue-aircraft", "red-site", weapon.id, 1)

    assert scenario.weapons == []
    assert weapon.current_quantity == 1


def test_weapon_target_types_reject_incompatible_target_domain() -> None:
    aircraft = Aircraft(
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
    ship = Ship(
        id="red-ship",
        name="Red Ship",
        side_id="red",
        class_name="Destroyer",
        latitude=0.0,
        longitude=0.0,
        altitude=0.0,
        heading=0.0,
        speed=20.0,
        current_fuel=1000.0,
        max_fuel=1000.0,
        fuel_rate=100.0,
        range=100.0,
    )
    harpoon = Weapon(
        id="harpoon",
        name="Harpoon",
        side_id="blue",
        class_name="RGM-84 Harpoon",
        latitude=0.0,
        longitude=0.0,
        altitude=1000.0,
        heading=0.0,
        speed=475.0,
        current_fuel=700.0,
        max_fuel=700.0,
        fuel_rate=150.0,
        range=67.0,
    )

    assert weapon_can_engage_target(aircraft, harpoon) is False
    assert weapon_can_engage_target(ship, harpoon) is True


def test_zero_speed_weapon_does_not_launch_or_raise() -> None:
    weapon = _surface_weapon(quantity=1)
    weapon.speed = 0.0
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
        weapons=[weapon],
    )
    target = Facility(
        id="red-site",
        name="Red Site",
        side_id="red",
        class_name="Radar",
        latitude=0.0,
        longitude=0.0,
        range=100.0,
        weapons=[],
    )
    scenario = Scenario(
        id="s1",
        name="Zero speed launch guard",
        start_time=0,
        current_time=0,
        duration=600,
        aircraft=[aircraft],
        facilities=[target],
    )

    launch_weapon(scenario, aircraft, target, weapon, 1)

    assert scenario.weapons == []
    assert weapon.current_quantity == 1


def test_get_next_coordinates_returns_origin_for_zero_speed() -> None:
    assert get_next_coordinates(1.0, 2.0, 3.0, 4.0, 0.0) == [1.0, 2.0]


def test_threat_detection_includes_exact_sensor_range_boundary() -> None:
    threat = Aircraft(
        id="target",
        name="Target",
        side_id="red",
        class_name="Test Aircraft",
        latitude=0.0,
        longitude=1.0,
        altitude=1000.0,
        heading=0.0,
        speed=300.0,
        current_fuel=1000.0,
        max_fuel=1000.0,
        fuel_rate=100.0,
        range=0.0,
    )
    detection_range_nm = (
        get_distance_between_two_points(0.0, 0.0, threat.latitude, threat.longitude)
        * 1000
    ) / NAUTICAL_MILES_TO_METERS
    detector = Facility(
        id="radar",
        name="Radar",
        side_id="blue",
        class_name="Radar",
        latitude=0.0,
        longitude=0.0,
        range=detection_range_nm,
    )

    assert is_threat_detected(threat, detector) is True


def test_threat_detection_uses_electronic_warfare_adjusted_sensor_range() -> None:
    relationships = Relationships()
    relationships.add_hostile("blue", "red")
    threat = Aircraft(
        id="target",
        name="Target",
        side_id="red",
        class_name="Test Aircraft",
        latitude=0.5,
        longitude=0.0,
        altitude=1000.0,
        heading=0.0,
        speed=300.0,
        current_fuel=1000.0,
        max_fuel=1000.0,
        fuel_rate=100.0,
        range=0.0,
    )
    jammer = Aircraft(
        id="jammer",
        name="Jammer",
        side_id="red",
        class_name="EA-18G Growler",
        latitude=0.1,
        longitude=0.0,
        altitude=1000.0,
        heading=0.0,
        speed=300.0,
        current_fuel=1000.0,
        max_fuel=1000.0,
        fuel_rate=100.0,
        range=0.0,
        is_electronic_warfare=True,
        jamming_range=40.0,
        jamming_strength=0.85,
        jamming_modes=["radar"],
    )
    detector = Facility(
        id="radar",
        name="Radar",
        side_id="blue",
        class_name="Radar",
        latitude=0.0,
        longitude=0.0,
        range=70.0,
    )
    scenario = Scenario(
        sides=[
            Side(id="blue", name="Blue", color="blue"),
            Side(id="red", name="Red", color="red"),
        ],
        aircraft=[threat, jammer],
        facilities=[detector],
        relationships=relationships,
    )

    assert is_threat_detected(threat, detector, scenario) is False


def test_scenario_defaults_do_not_share_mutable_state() -> None:
    first = Scenario()
    second = Scenario()
    first.relationships.add_hostile("blue", "red")
    first.aircraft.append(
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
        )
    )

    assert second.relationships.is_hostile("blue", "red") is False
    assert second.aircraft == []


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


def test_aircraft_surface_engagement_respects_sensor_shadow_obstacle() -> None:
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
        range=50.0,
        weapons=[_surface_weapon()],
    )
    facility = Facility(
        id="red-sam",
        name="Red SAM",
        side_id="red",
        class_name="SAM",
        latitude=0.0,
        longitude=0.5,
        range=100.0,
        weapons=[],
    )
    relationships = Relationships()
    relationships.add_hostile("blue", "red")
    scenario = Scenario(
        id="s1",
        name="Surface engagement through sensor shadow",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[
            Side(id="blue", name="BLUE", color="blue"),
            Side(id="red", name="RED", color="red"),
        ],
        aircraft=[aircraft],
        facilities=[facility],
        obstacles=[
            Obstacle(
                id="shadow",
                name="Sensor Shadow",
                class_name="Sensor Shadow",
                latitude=facility.latitude,
                longitude=facility.longitude,
                radius_nm=5.0,
                obstacle_type="sensor_shadow",
                detection_penalty=0.6,
                affected_domains=["aircraft"],
            )
        ],
        relationships=relationships,
    )
    game = Game(current_scenario=scenario)

    game.aircraft_surface_engagement()

    assert scenario.weapons == []
    assert aircraft.weapons[0].current_quantity == 2


def test_manual_aircraft_attack_requires_declared_hostile_relationship() -> None:
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
        weapons=[_surface_weapon(quantity=1)],
    )
    neutral_facility = Facility(
        id="neutral-site",
        name="Neutral Site",
        side_id="neutral",
        class_name="Radar",
        latitude=0.0,
        longitude=0.0,
        range=100.0,
        weapons=[],
    )
    scenario = Scenario(
        id="s1",
        name="Neutral attack guard",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[
            Side(id="blue", name="BLUE", color="blue"),
            Side(id="neutral", name="NEUTRAL", color="gray"),
        ],
        aircraft=[aircraft],
        facilities=[neutral_facility],
        relationships=Relationships(),
    )
    game = Game(current_scenario=scenario)

    game.handle_aircraft_attack(
        "blue-aircraft", "neutral-site", "surface-weapon", 1
    )

    assert len(scenario.weapons) == 0
    assert aircraft.weapons[0].current_quantity == 1


def test_manual_aircraft_attack_requires_detected_target() -> None:
    target_longitude = 0.45
    target_distance_nm = (
        get_distance_between_two_points(0.0, 0.0, 0.0, target_longitude) * 1000
    ) / NAUTICAL_MILES_TO_METERS
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
        range=target_distance_nm * 0.95,
        weapons=[_surface_weapon(quantity=1)],
    )
    target = Facility(
        id="red-site",
        name="Red Site",
        side_id="red",
        class_name="Radar",
        latitude=0.0,
        longitude=target_longitude,
        range=100.0,
        weapons=[],
    )
    relationships = Relationships()
    relationships.add_hostile("blue", "red")
    scenario = Scenario(
        id="s1",
        name="Manual attack detection guard",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[
            Side(id="blue", name="BLUE", color="blue"),
            Side(id="red", name="RED", color="red"),
        ],
        aircraft=[aircraft],
        facilities=[target],
        relationships=relationships,
    )
    game = Game(current_scenario=scenario)

    game.handle_aircraft_attack("blue-aircraft", "red-site", "surface-weapon", 1)

    assert scenario.weapons == []
    assert aircraft.weapons[0].current_quantity == 1


def test_strike_mission_requires_hostile_target() -> None:
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
        weapons=[_surface_weapon(quantity=1)],
    )
    neutral_facility = Facility(
        id="neutral-site",
        name="Neutral Site",
        side_id="neutral",
        class_name="Radar",
        latitude=0.0,
        longitude=0.0,
        range=100.0,
        weapons=[],
    )
    scenario = Scenario(
        id="s1",
        name="Neutral strike guard",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[
            Side(id="blue", name="BLUE", color="blue"),
            Side(id="neutral", name="NEUTRAL", color="gray"),
        ],
        aircraft=[aircraft],
        facilities=[neutral_facility],
        missions=[
            StrikeMission(
                id="strike-1",
                name="Strike",
                side_id="blue",
                assigned_unit_ids=[aircraft.id],
                assigned_target_ids=[neutral_facility.id],
                active=True,
            )
        ],
        relationships=Relationships(),
    )
    game = Game(current_scenario=scenario)

    game.update_units_on_strike_mission()

    assert len(scenario.weapons) == 0
    assert aircraft.weapons[0].current_quantity == 1


def test_strike_mission_respects_sensor_shadow_obstacle() -> None:
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
        range=50.0,
        weapons=[_surface_weapon(quantity=1)],
    )
    target = Facility(
        id="red-site",
        name="Red Site",
        side_id="red",
        class_name="Radar",
        latitude=0.0,
        longitude=0.5,
        range=100.0,
        weapons=[],
    )
    relationships = Relationships()
    relationships.add_hostile("blue", "red")
    scenario = Scenario(
        id="s1",
        name="Strike through sensor shadow",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[
            Side(id="blue", name="BLUE", color="blue"),
            Side(id="red", name="RED", color="red"),
        ],
        aircraft=[aircraft],
        facilities=[target],
        obstacles=[
            Obstacle(
                id="shadow",
                name="Sensor Shadow",
                class_name="Sensor Shadow",
                latitude=target.latitude,
                longitude=target.longitude,
                radius_nm=5.0,
                obstacle_type="sensor_shadow",
                detection_penalty=0.6,
                affected_domains=["aircraft"],
            )
        ],
        missions=[
            StrikeMission(
                id="strike-1",
                name="Strike",
                side_id="blue",
                assigned_unit_ids=[aircraft.id],
                assigned_target_ids=[target.id],
                active=True,
            )
        ],
        relationships=relationships,
    )
    game = Game(current_scenario=scenario)

    game.update_units_on_strike_mission()

    assert scenario.weapons == []
    assert aircraft.weapons[0].current_quantity == 1


def test_strike_mission_does_not_launch_when_target_is_only_inside_tolerance_margin() -> None:
    target_longitude = 0.45
    target_distance_nm = (
        get_distance_between_two_points(0.0, 0.0, 0.0, target_longitude) * 1000
    ) / NAUTICAL_MILES_TO_METERS
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
        range=target_distance_nm * 0.95,
        weapons=[_surface_weapon(quantity=1)],
    )
    target = Facility(
        id="red-site",
        name="Red Site",
        side_id="red",
        class_name="Radar",
        latitude=0.0,
        longitude=target_longitude,
        range=100.0,
        weapons=[],
    )
    relationships = Relationships()
    relationships.add_hostile("blue", "red")
    scenario = Scenario(
        id="s1",
        name="Strike outside exact detection range",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[
            Side(id="blue", name="BLUE", color="blue"),
            Side(id="red", name="RED", color="red"),
        ],
        aircraft=[aircraft],
        facilities=[target],
        missions=[
            StrikeMission(
                id="strike-1",
                name="Strike",
                side_id="blue",
                assigned_unit_ids=[aircraft.id],
                assigned_target_ids=[target.id],
                active=True,
            )
        ],
        relationships=relationships,
    )
    game = Game(current_scenario=scenario)

    game.update_units_on_strike_mission()

    assert scenario.weapons == []
    assert aircraft.weapons[0].current_quantity == 1


def test_strike_mission_without_targets_is_not_created_or_kept() -> None:
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
        weapons=[_surface_weapon(quantity=1)],
    )
    scenario = Scenario(
        id="s1",
        name="Empty strike guard",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[Side(id="blue", name="BLUE", color="blue")],
        aircraft=[aircraft],
        missions=[
            StrikeMission(
                id="strike-empty",
                name="Empty Strike",
                side_id="blue",
                assigned_unit_ids=[aircraft.id],
                assigned_target_ids=[],
                active=True,
            )
        ],
    )
    game = Game(current_scenario=scenario)
    game.current_side_id = "blue"

    game.clear_completed_strike_missions()
    game.create_strike_mission("New Empty Strike", [aircraft.id], [])

    assert scenario.missions == []


def test_strike_mission_rejects_cross_side_attackers() -> None:
    red_weapon = _surface_weapon(quantity=1)
    red_weapon.side_id = "red"
    red_weapon.id = "red-weapon"
    red_aircraft = Aircraft(
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
        weapons=[red_weapon],
    )
    blue_target = Facility(
        id="blue-target",
        name="Blue Target",
        side_id="blue",
        class_name="Radar",
        latitude=0.0,
        longitude=0.0,
        range=100.0,
        weapons=[],
    )
    relationships = Relationships()
    relationships.add_hostile("blue", "red")
    scenario = Scenario(
        id="s1",
        name="Cross-side strike guard",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[
            Side(id="blue", name="BLUE", color="blue"),
            Side(id="red", name="RED", color="red"),
        ],
        aircraft=[red_aircraft],
        facilities=[blue_target],
        relationships=relationships,
    )
    game = Game(current_scenario=scenario)
    game.current_side_id = "blue"

    game.create_strike_mission("Invalid Strike", [red_aircraft.id], [blue_target.id])
    scenario.missions.append(
        StrikeMission(
            id="imported-invalid-strike",
            name="Imported Invalid Strike",
            side_id="blue",
            assigned_unit_ids=[red_aircraft.id],
            assigned_target_ids=[blue_target.id],
            active=True,
        )
    )
    game.update_units_on_strike_mission()

    assert len(scenario.missions) == 1
    assert len(scenario.weapons) == 0
    assert red_weapon.current_quantity == 1


def test_strike_mission_uses_loaded_weapon_when_longest_range_weapon_is_empty() -> None:
    empty_long_range = Weapon(
        id="empty-long-range",
        name="Empty Long Range",
        side_id="blue",
        class_name="Empty Long Range",
        latitude=0.0,
        longitude=0.0,
        altitude=1000.0,
        heading=0.0,
        speed=1000.0,
        current_fuel=1.0,
        max_fuel=1.0,
        fuel_rate=1.0,
        range=1000.0,
        current_quantity=0,
        max_quantity=1,
    )
    loaded_short_range = _surface_weapon(quantity=1)
    loaded_short_range.id = "loaded-short-range"
    loaded_short_range.range = 100.0
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
        weapons=[empty_long_range, loaded_short_range],
    )
    target = Facility(
        id="red-site",
        name="Red Site",
        side_id="red",
        class_name="Radar",
        latitude=0.0,
        longitude=0.0,
        range=100.0,
        weapons=[],
    )
    relationships = Relationships()
    relationships.add_hostile("blue", "red")
    scenario = Scenario(
        id="s1",
        name="Strike weapon choice",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[
            Side(id="blue", name="BLUE", color="blue"),
            Side(id="red", name="RED", color="red"),
        ],
        aircraft=[aircraft],
        facilities=[target],
        missions=[
            StrikeMission(
                id="strike-1",
                name="Strike",
                side_id="blue",
                assigned_unit_ids=[aircraft.id],
                assigned_target_ids=[target.id],
                active=True,
            )
        ],
        relationships=relationships,
    )
    game = Game(current_scenario=scenario)

    game.update_units_on_strike_mission()

    assert len(scenario.weapons) == 1
    assert scenario.weapons[0].class_name == "Test Weapon"
    assert loaded_short_range.current_quantity == 0


def test_ship_assigned_to_strike_mission_launches_against_hostile_surface_target() -> None:
    naval_gun = _surface_weapon(quantity=1)
    naval_gun.id = "naval-gun"
    naval_gun.class_name = "Naval Gunfire"
    ship = Ship(
        id="blue-ship",
        name="Blue Ship",
        side_id="blue",
        class_name="Battleship",
        latitude=0.0,
        longitude=0.0,
        altitude=0.0,
        heading=0.0,
        speed=20.0,
        current_fuel=1000.0,
        max_fuel=1000.0,
        fuel_rate=10.0,
        range=100.0,
        weapons=[naval_gun],
    )
    target = Facility(
        id="red-site",
        name="Red Site",
        side_id="red",
        class_name="Coastal Battery",
        latitude=0.0,
        longitude=0.0,
        range=100.0,
        weapons=[],
    )
    relationships = Relationships()
    relationships.add_hostile("blue", "red")
    scenario = Scenario(
        id="s1",
        name="Ship strike mission",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[
            Side(id="blue", name="BLUE", color="blue"),
            Side(id="red", name="RED", color="red"),
        ],
        ships=[ship],
        facilities=[target],
        missions=[
            StrikeMission(
                id="strike-1",
                name="Naval Strike",
                side_id="blue",
                assigned_unit_ids=[ship.id],
                assigned_target_ids=[target.id],
                active=True,
            )
        ],
        relationships=relationships,
    )
    game = Game(current_scenario=scenario)

    game.update_units_on_strike_mission()

    assert len(scenario.weapons) == 1
    assert scenario.weapons[0].class_name == "Naval Gunfire"
    assert scenario.weapons[0].target_id == target.id
    assert naval_gun.current_quantity == 0


def test_facility_auto_defense_uses_loaded_weapon_when_longest_range_weapon_is_empty() -> None:
    empty_long_range = Weapon(
        id="empty-long-range",
        name="Empty Long Range",
        side_id="blue",
        class_name="Empty Long Range",
        latitude=0.0,
        longitude=0.0,
        altitude=1000.0,
        heading=0.0,
        speed=1000.0,
        current_fuel=1.0,
        max_fuel=1.0,
        fuel_rate=1.0,
        range=1000.0,
        current_quantity=0,
        max_quantity=1,
    )
    loaded_short_range = _surface_weapon(quantity=1)
    loaded_short_range.id = "loaded-short-range"
    loaded_short_range.range = 100.0
    facility = Facility(
        id="blue-sam",
        name="Blue SAM",
        side_id="blue",
        class_name="SAM",
        latitude=0.0,
        longitude=0.0,
        range=100.0,
        weapons=[empty_long_range, loaded_short_range],
    )
    aircraft = Aircraft(
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
    relationships = Relationships()
    relationships.add_hostile("blue", "red")
    scenario = Scenario(
        id="s1",
        name="Facility weapon choice",
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

    game.facility_auto_defense()

    assert len(scenario.weapons) == 1
    assert scenario.weapons[0].class_name == "Test Weapon"
    assert loaded_short_range.current_quantity == 0


def test_ship_auto_defense_uses_loaded_weapon_when_longest_range_weapon_is_empty() -> None:
    empty_long_range = Weapon(
        id="empty-long-range",
        name="Empty Long Range",
        side_id="blue",
        class_name="Empty Long Range",
        latitude=0.0,
        longitude=0.0,
        altitude=1000.0,
        heading=0.0,
        speed=1000.0,
        current_fuel=1.0,
        max_fuel=1.0,
        fuel_rate=1.0,
        range=1000.0,
        current_quantity=0,
        max_quantity=1,
    )
    loaded_short_range = _surface_weapon(quantity=1)
    loaded_short_range.id = "loaded-short-range"
    loaded_short_range.range = 100.0
    ship = Ship(
        id="blue-ship",
        name="Blue Ship",
        side_id="blue",
        class_name="Destroyer",
        latitude=0.0,
        longitude=0.0,
        altitude=0.0,
        heading=0.0,
        speed=20.0,
        current_fuel=1000.0,
        max_fuel=1000.0,
        fuel_rate=10.0,
        range=100.0,
        weapons=[empty_long_range, loaded_short_range],
    )
    aircraft = Aircraft(
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
    relationships = Relationships()
    relationships.add_hostile("blue", "red")
    scenario = Scenario(
        id="s1",
        name="Ship weapon choice",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[
            Side(id="blue", name="BLUE", color="blue"),
            Side(id="red", name="RED", color="red"),
        ],
        aircraft=[aircraft],
        ships=[ship],
        relationships=relationships,
    )
    game = Game(current_scenario=scenario)

    game.ship_auto_defense()

    assert len(scenario.weapons) == 1
    assert scenario.weapons[0].class_name == "Test Weapon"
    assert loaded_short_range.current_quantity == 0


def test_update_game_state_processes_every_weapon_when_some_are_removed() -> None:
    scenario = Scenario(
        id="s1",
        name="Weapon removal iteration",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[Side(id="blue", name="BLUE", color="blue")],
        weapons=[
            Weapon(
                id="orphan-1",
                name="Orphan 1",
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
                target_id="missing",
                current_quantity=1,
                max_quantity=1,
            ),
            Weapon(
                id="orphan-2",
                name="Orphan 2",
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
                target_id="missing",
                current_quantity=1,
                max_quantity=1,
            ),
        ],
    )
    game = Game(current_scenario=scenario)

    game.update_game_state()

    assert scenario.weapons == []
