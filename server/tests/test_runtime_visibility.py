from __future__ import annotations

from app.tianshu_runtime.visibility import compute_runtime_visibility

from blade.Relationships import Relationships
from blade.Scenario import Scenario
from blade.Side import Side
from blade.units.Aircraft import Aircraft


def _aircraft(
    aircraft_id: str,
    side_id: str,
    latitude: float,
    longitude: float,
    detection_range: float,
) -> Aircraft:
    return Aircraft(
        id=aircraft_id,
        name=aircraft_id,
        side_id=side_id,
        class_name="Test Aircraft",
        latitude=latitude,
        longitude=longitude,
        altitude=1000.0,
        heading=0.0,
        speed=300.0,
        current_fuel=1000.0,
        max_fuel=1000.0,
        fuel_rate=100.0,
        range=detection_range,
    )


def _scenario() -> Scenario:
    relationships = Relationships()
    relationships.add_hostile("blue", "red")
    return Scenario(
        id="visibility-scenario",
        name="Runtime visibility",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[
            Side(id="blue", name="BLUE", color="blue"),
            Side(id="red", name="RED", color="red"),
        ],
        aircraft=[
            _aircraft("blue-radar", "blue", 0.0, 0.0, 70.0),
            _aircraft("red-near", "red", 0.5, 0.0, 0.0),
            _aircraft("red-far", "red", 3.0, 0.0, 0.0),
        ],
        relationships=relationships,
    )


def test_runtime_visibility_detects_hostiles_in_backend_runtime() -> None:
    visibility = compute_runtime_visibility(_scenario(), "blue")
    blue_visibility = visibility["by_side"]["blue"]

    assert "blue-radar" in blue_visibility["visible_object_ids"]
    assert "red-near" in blue_visibility["visible_object_ids"]
    assert "red-near" in blue_visibility["detected_hostile_object_ids"]
    assert "red-far" not in blue_visibility["visible_object_ids"]
    assert blue_visibility["visible_counts"]["aircraft"] == 2
    assert blue_visibility["total_counts"]["aircraft"] == 3


def test_runtime_visibility_hides_hostile_operational_details() -> None:
    visibility = compute_runtime_visibility(_scenario(), "blue")
    blue_visibility = visibility["by_side"]["blue"]

    assert "blue-radar" in blue_visibility["operational_detail_object_ids"]
    assert "red-near" not in blue_visibility["operational_detail_object_ids"]
    assert "red-far" not in blue_visibility["operational_detail_object_ids"]


def test_runtime_visibility_applies_hostile_electronic_warfare_jamming() -> None:
    scenario = _scenario()
    scenario.aircraft.append(
        Aircraft(
            id="red-jammer",
            name="Red Jammer",
            side_id="red",
            class_name="EA-18G Growler",
            latitude=0.1,
            longitude=0.0,
            altitude=10000.0,
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
    )

    visibility = compute_runtime_visibility(scenario, "blue")
    blue_visibility = visibility["by_side"]["blue"]

    assert "red-near" not in blue_visibility["visible_object_ids"]
    assert "red-near" not in blue_visibility["detected_hostile_object_ids"]
