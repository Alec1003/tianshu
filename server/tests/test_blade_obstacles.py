from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
GYM_DIR = ROOT_DIR / "gym"
if str(GYM_DIR) not in sys.path:
    sys.path.insert(0, str(GYM_DIR))

from blade.Game import Game  # noqa: E402
from blade.Scenario import Scenario  # noqa: E402
from blade.Side import Side  # noqa: E402
from blade.engine.weaponEngagement import is_threat_detected  # noqa: E402
from blade.units.Aircraft import Aircraft  # noqa: E402
from blade.units.Obstacle import Obstacle  # noqa: E402


def _aircraft(
    aircraft_id: str,
    *,
    latitude: float = 0.0,
    longitude: float = 0.0,
    range_nm: float = 100.0,
) -> Aircraft:
    return Aircraft(
        id=aircraft_id,
        name=aircraft_id,
        side_id="blue",
        class_name="Test Aircraft",
        latitude=latitude,
        longitude=longitude,
        altitude=10000.0,
        heading=90.0,
        speed=600.0,
        current_fuel=10000.0,
        max_fuel=10000.0,
        fuel_rate=0.0,
        range=range_nm,
    )


def test_no_go_obstacle_blocks_waypoint_entry() -> None:
    aircraft = _aircraft("aircraft")
    aircraft.route = [[0.0, 0.002]]
    obstacle = Obstacle(
        id="no-go",
        name="No-go",
        class_name="No-go",
        latitude=0.0,
        longitude=0.002,
        radius_nm=1.0,
        obstacle_type="no_go",
        movement_penalty=1.0,
    )
    scenario = Scenario(
        id="obstacle-block",
        name="Obstacle Block",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[Side(id="blue", name="BLUE", color="blue")],
        aircraft=[aircraft],
        obstacles=[obstacle],
    )

    Game(current_scenario=scenario).update_all_aircraft_position()

    assert aircraft.latitude == 0.0
    assert aircraft.longitude == 0.0
    assert aircraft.route == [[0.0, 0.002]]


def test_terrain_obstacle_reduces_effective_aircraft_speed() -> None:
    fast = _aircraft("fast")
    slow = _aircraft("slow")
    fast.route = [[0.0, 1.0]]
    slow.route = [[0.0, 1.0]]
    clear_scenario = Scenario(
        id="clear",
        name="Clear",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[Side(id="blue", name="BLUE", color="blue")],
        aircraft=[fast],
    )
    terrain_scenario = Scenario(
        id="terrain",
        name="Terrain",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[Side(id="blue", name="BLUE", color="blue")],
        aircraft=[slow],
        obstacles=[
            Obstacle(
                id="terrain-zone",
                name="Terrain",
                class_name="Terrain",
                latitude=0.0,
                longitude=0.0,
                radius_nm=10.0,
                obstacle_type="terrain",
                movement_penalty=0.5,
            )
        ],
    )

    Game(current_scenario=clear_scenario).update_all_aircraft_position()
    Game(current_scenario=terrain_scenario).update_all_aircraft_position()

    assert 0.0 < slow.longitude < fast.longitude


def test_sensor_shadow_obstacle_reduces_detection_range() -> None:
    detector = _aircraft("detector", latitude=0.0, longitude=0.0, range_nm=50.0)
    threat = _aircraft("threat", latitude=0.0, longitude=0.5, range_nm=0.0)
    scenario = Scenario(
        id="sensor-shadow",
        name="Sensor Shadow",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[
            Side(id="blue", name="BLUE", color="blue"),
            Side(id="red", name="RED", color="red"),
        ],
        aircraft=[detector, threat],
        obstacles=[
            Obstacle(
                id="shadow",
                name="Shadow",
                class_name="Shadow",
                latitude=0.0,
                longitude=0.5,
                radius_nm=5.0,
                obstacle_type="sensor_shadow",
                detection_penalty=0.6,
                affected_domains=["aircraft"],
            )
        ],
    )

    assert is_threat_detected(threat, detector) is True
    assert is_threat_detected(threat, detector, scenario) is False


def test_scenario_load_export_preserves_obstacles() -> None:
    scenario = Scenario(
        id="obstacle-roundtrip",
        name="Obstacle Roundtrip",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[Side(id="blue", name="BLUE", color="blue")],
        obstacles=[
            Obstacle(
                id="weather",
                name="Weather",
                class_name="Weather",
                latitude=1.0,
                longitude=2.0,
                radius_nm=12.0,
                obstacle_type="weather",
                movement_penalty=0.25,
                detection_penalty=0.35,
                communication_penalty=0.15,
                affected_domains=["aircraft", "ship"],
                description="Training weather constraint",
            )
        ],
    )
    exported = Game(current_scenario=scenario).export_scenario()
    loaded = Game(current_scenario=Scenario())

    loaded.load_scenario(json.dumps(exported))

    obstacle = loaded.current_scenario.get_obstacle("weather")
    assert obstacle is not None
    assert obstacle.obstacle_type == "weather"
    assert obstacle.radius_nm == 12.0
    assert obstacle.movement_penalty == 0.25
    assert obstacle.detection_penalty == 0.35
    assert obstacle.communication_penalty == 0.15
    assert obstacle.affected_domains == ["aircraft", "ship"]
