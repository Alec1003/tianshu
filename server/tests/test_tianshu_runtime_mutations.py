from __future__ import annotations

from threading import RLock

import pytest

from app.tianshu_runtime.runtime import TianShuRuntime

from blade.Game import Game
from blade.Relationships import Relationships
from blade.Scenario import Scenario
from blade.Side import Side
from blade.mission.StrikeMission import StrikeMission
from blade.units.Aircraft import Aircraft
from blade.units.Airbase import Airbase
from blade.units.ReferencePoint import ReferencePoint


def _runtime() -> TianShuRuntime:
    scenario = Scenario(
        id="runtime-mutations",
        name="Runtime mutations",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[
            Side(id="blue", name="BLUE", color="blue"),
            Side(id="red", name="RED", color="red"),
        ],
        relationships=Relationships(),
    )
    runtime = TianShuRuntime.__new__(TianShuRuntime)
    runtime._lock = RLock()
    runtime.game = Game(current_scenario=scenario)
    runtime.game.current_side_id = "blue"
    return runtime


def test_deploy_aircraft_uses_backend_weapon_loadout() -> None:
    runtime = _runtime()

    state = runtime.deploy_aircraft(
        "F-35A Lightning II",
        latitude=10.0,
        longitude=20.0,
        side="blue",
    )

    aircraft = runtime.game.current_scenario.get_aircraft(state["unitId"])
    assert aircraft is not None
    assert aircraft.side_id == "blue"
    assert [weapon.class_name for weapon in aircraft.weapons] == [
        "AIM-120 AMRAAM",
        "AIM-9 Sidewinder",
        "AGM-65 Maverick",
    ]
    assert [weapon.current_quantity for weapon in aircraft.weapons] == [4, 2, 2]
    assert [weapon.target_types for weapon in aircraft.weapons] == [
        ["aircraft"],
        ["aircraft"],
        ["facility", "airbase", "ship"],
    ]


def test_deploy_aircraft_uses_unit_asset_electronic_warfare_template() -> None:
    runtime = _runtime()

    state = runtime.deploy_aircraft(
        "Custom EW",
        latitude=10.0,
        longitude=20.0,
        side="blue",
        template={
            "className": "Custom EW",
            "speed": 820,
            "maxFuel": 14000,
            "fuelRate": 4200,
            "range": 800,
            "isElectronicWarfare": True,
            "jammingRange": 125,
            "jammingStrength": 0.5,
            "jammingModes": ["radar"],
            "communicationDisruption": 0.2,
        },
    )

    aircraft = runtime.game.current_scenario.get_aircraft(state["unitId"])
    assert aircraft is not None
    assert aircraft.is_electronic_warfare is True
    assert aircraft.jamming_range == 125
    assert aircraft.jamming_strength == 0.5
    assert aircraft.jamming_modes == ["radar"]
    assert aircraft.weapons == []


def test_deploy_aircraft_rejects_unknown_class_without_template() -> None:
    runtime = _runtime()

    with pytest.raises(ValueError, match="Unknown aircraft class"):
        runtime.deploy_aircraft(
            "Imaginary Airframe",
            latitude=10.0,
            longitude=20.0,
            side="blue",
        )

    assert runtime.game.current_scenario.aircraft == []


@pytest.mark.parametrize(
    ("method_name", "collection_name", "message"),
    [
        ("deploy_ship", "ships", "Unknown ship class"),
        ("deploy_facility", "facilities", "Unknown facility class"),
        ("deploy_airbase", "airbases", "Unknown airbase class"),
    ],
)
def test_deploy_units_reject_unknown_class_without_template(
    method_name: str,
    collection_name: str,
    message: str,
) -> None:
    runtime = _runtime()
    deploy = getattr(runtime, method_name)

    with pytest.raises(ValueError, match=message):
        deploy(
            "Imaginary Unit",
            latitude=10.0,
            longitude=20.0,
            side="blue",
        )

    assert getattr(runtime.game.current_scenario, collection_name) == []


def test_runtime_unit_mutations_are_applied_in_backend_scenario() -> None:
    runtime = _runtime()
    runtime.deploy_ship("Destroyer", 11.0, 21.0, side="blue")
    ship = runtime.game.current_scenario.ships[0]

    runtime.move_unit("ship", ship.id, [[12.0, 22.0], [13.0, 23.0]])
    runtime.set_unit_position("ship", ship.id, 14.0, 24.0)
    runtime.update_unit_state("ship", ship.id, {"is_objective": True})

    assert ship.route == [[12.0, 22.0], [13.0, 23.0]]
    assert ship.latitude == 14.0
    assert ship.longitude == 24.0
    assert ship.is_objective is True


def test_runtime_move_unit_rejects_invalid_route_coordinates() -> None:
    runtime = _runtime()
    runtime.deploy_ship("Destroyer", 11.0, 21.0, side="blue")
    ship = runtime.game.current_scenario.ships[0]

    with pytest.raises(ValueError, match="latitude out of range"):
        runtime.move_unit("ship", ship.id, [[999.0, 22.0]])

    with pytest.raises(ValueError, match="numeric coordinates"):
        runtime.move_unit("ship", ship.id, [["bad", 22.0]])  # type: ignore[list-item]

    assert ship.route == []


def test_runtime_obstacle_mutations_are_applied_in_backend_scenario() -> None:
    runtime = _runtime()

    state = runtime.deploy_obstacle(
        "禁行区",
        latitude=11.0,
        longitude=21.0,
        radius_nm=12.0,
        obstacle_type="no_go",
        movement_penalty=1.0,
        detection_penalty=0.0,
        affected_domains=["aircraft"],
    )
    obstacle = runtime.game.current_scenario.get_obstacle(state["unitId"])

    assert obstacle is not None
    assert obstacle.class_name == "禁行区"
    assert obstacle.radius_nm == 12.0
    assert obstacle.affected_domains == ["aircraft"]

    runtime.set_unit_position("obstacle", obstacle.id, 12.0, 22.0)
    runtime.update_unit_state(
        "obstacle",
        obstacle.id,
        {
            "name": "天气约束区",
            "obstacleType": "weather",
            "radiusNm": 20.0,
            "movementPenalty": 0.25,
            "detectionPenalty": 0.35,
            "communicationPenalty": 0.15,
            "affectedDomains": ["aircraft", "ship"],
        },
    )

    assert obstacle.latitude == 12.0
    assert obstacle.longitude == 22.0
    assert obstacle.name == "天气约束区"
    assert obstacle.obstacle_type == "weather"
    assert obstacle.radius_nm == 20.0
    assert obstacle.movement_penalty == 0.25
    assert obstacle.detection_penalty == 0.35
    assert obstacle.communication_penalty == 0.15
    assert obstacle.affected_domains == ["aircraft", "ship"]

    runtime.delete_unit("obstacle", obstacle.id)
    assert runtime.game.current_scenario.get_obstacle(obstacle.id) is None


def test_runtime_weapon_mutations_use_backend_weapon_templates() -> None:
    runtime = _runtime()
    scenario = runtime.game.current_scenario
    aircraft = Aircraft(
        id="aircraft-1",
        name="Blue Aircraft",
        side_id="blue",
        class_name="F-35A Lightning II",
        latitude=1.0,
        longitude=2.0,
        altitude=10000.0,
        heading=0.0,
        speed=300.0,
        current_fuel=1000.0,
        max_fuel=1000.0,
        fuel_rate=100.0,
        range=100.0,
    )
    scenario.aircraft.append(aircraft)

    state = runtime.add_weapon_to_unit(
        "aircraft",
        aircraft.id,
        "AIM-54 Phoenix",
        speed=1.0,
        max_fuel=1.0,
        fuel_rate=1.0,
        range_nm=1.0,
        lethality=0.01,
        quantity=3,
    )

    assert state["added"] is True
    weapon = aircraft.weapons[0]
    assert weapon.class_name == "AIM-54 Phoenix"
    assert weapon.speed == 3500.0
    assert weapon.range == 100.0
    assert weapon.lethality == 0.85
    assert weapon.current_quantity == 3

    runtime.update_weapon_quantity("aircraft", aircraft.id, weapon.id, -2)
    assert weapon.current_quantity == 1

    runtime.delete_weapon_from_unit("aircraft", aircraft.id, weapon.id)
    assert aircraft.weapons == []


def test_delete_unit_cleans_mission_and_homebase_references() -> None:
    runtime = _runtime()
    scenario = runtime.game.current_scenario
    airbase = Airbase(
        id="base-1",
        name="Blue Base",
        side_id="blue",
        class_name="Airbase",
        latitude=0.0,
        longitude=0.0,
        altitude=0.0,
        side_color="blue",
    )
    aircraft = Aircraft(
        id="aircraft-1",
        name="Blue Aircraft",
        side_id="blue",
        class_name="F-35A Lightning II",
        latitude=0.0,
        longitude=0.0,
        altitude=10000.0,
        heading=0.0,
        speed=300.0,
        current_fuel=1000.0,
        max_fuel=1000.0,
        fuel_rate=100.0,
        range=100.0,
        home_base_id=airbase.id,
        rtb=True,
    )
    mission = StrikeMission(
        id="mission-1",
        name="Strike",
        side_id="blue",
        assigned_unit_ids=[aircraft.id],
        assigned_target_ids=[airbase.id],
        active=True,
    )
    scenario.airbases.append(airbase)
    scenario.aircraft.append(aircraft)
    scenario.missions.append(mission)

    runtime.delete_unit("airbase", airbase.id)

    assert scenario.airbases == []
    assert aircraft.home_base_id == ""
    assert aircraft.rtb is False
    assert mission.assigned_target_ids == []


def test_runtime_mission_mutations_are_authoritative() -> None:
    runtime = _runtime()
    scenario = runtime.game.current_scenario
    scenario.aircraft.append(
        Aircraft(
            id="aircraft-1",
            name="Blue Aircraft",
            side_id="blue",
            class_name="F-35A Lightning II",
            latitude=0.0,
            longitude=0.0,
            altitude=10000.0,
            heading=0.0,
            speed=300.0,
            current_fuel=1000.0,
            max_fuel=1000.0,
            fuel_rate=100.0,
            range=100.0,
        )
    )
    for idx in range(3):
        scenario.reference_points.append(
            ReferencePoint(
                id=f"rp-{idx}",
                name=f"RP {idx}",
                side_id="blue",
                latitude=float(idx),
                longitude=float(idx),
                altitude=0.0,
                side_color="blue",
            )
        )

    created = runtime.create_patrol_mission(
        "Patrol",
        ["aircraft-1"],
        ["rp-0", "rp-1", "rp-2"],
    )
    mission_id = created["missionId"]
    runtime.update_patrol_mission(
        mission_id,
        "Updated Patrol",
        ["aircraft-1"],
        ["rp-0", "rp-1", "rp-2"],
    )

    patrol = scenario.get_patrol_mission(mission_id)
    assert patrol is not None
    assert patrol.name == "Updated Patrol"
    assert patrol.assigned_unit_ids == ["aircraft-1"]

    runtime.delete_mission(mission_id)
    assert scenario.missions == []


def test_step_simulation_reports_actual_steps_when_time_limit_stops_early() -> None:
    runtime = _runtime()
    runtime.game.current_scenario.duration = 1

    state = runtime.step_simulation(5)

    assert state == {
        "steps": 1,
        "requestedSteps": 5,
        "currentTime": 1,
        "refuelingEvents": [],
    }

    already_done = runtime.step_simulation(5)
    assert already_done == {
        "steps": 0,
        "requestedSteps": 5,
        "currentTime": 1,
        "refuelingEvents": [],
    }


def test_step_simulation_rejects_invalid_step_count() -> None:
    runtime = _runtime()

    with pytest.raises(ValueError, match="between 1 and 7200"):
        runtime.step_simulation(0)

    with pytest.raises(ValueError, match="between 1 and 7200"):
        runtime.step_simulation(7201)
