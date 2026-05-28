from __future__ import annotations

from typing import Any

from blade.utils.constants import NAUTICAL_MILES_TO_METERS
from blade.utils.utils import get_distance_between_two_points


IMPASSABLE_OBSTACLE_TYPES = {"no_go", "restricted_airspace", "blocked_area"}
SPEED_OBSTACLE_TYPES = {"terrain", "weather", "no_go", "restricted_airspace", "blocked_area"}
SENSOR_OBSTACLE_TYPES = {"sensor_shadow", "weather", "terrain"}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _domain_for_unit(unit: Any) -> str:
    module = unit.__class__.__name__.lower()
    if module == "aircraft":
        return "aircraft"
    if module == "ship":
        return "ship"
    if module == "facility":
        return "facility"
    return module


def _active_obstacles(scenario: Any) -> list[Any]:
    return [
        obstacle
        for obstacle in (getattr(scenario, "obstacles", []) or [])
        if bool(getattr(obstacle, "active", True))
        and _as_float(getattr(obstacle, "radius_nm", 0.0)) > 0
    ]


def _affects_unit(obstacle: Any, unit: Any) -> bool:
    affected = getattr(obstacle, "affected_domains", None) or []
    if not affected:
        return True
    domain = _domain_for_unit(unit)
    return domain in {str(item).lower() for item in affected}


def distance_to_obstacle_nm(obstacle: Any, latitude: float, longitude: float) -> float:
    distance_km = get_distance_between_two_points(
        _as_float(getattr(obstacle, "latitude", 0.0)),
        _as_float(getattr(obstacle, "longitude", 0.0)),
        latitude,
        longitude,
    )
    return (distance_km * 1000) / NAUTICAL_MILES_TO_METERS


def point_inside_obstacle(obstacle: Any, latitude: float, longitude: float) -> bool:
    return distance_to_obstacle_nm(obstacle, latitude, longitude) <= _as_float(
        getattr(obstacle, "radius_nm", 0.0)
    )


def blocking_obstacle_for_point(
    scenario: Any,
    unit: Any,
    latitude: float,
    longitude: float,
) -> Any | None:
    for obstacle in _active_obstacles(scenario):
        if not _affects_unit(obstacle, unit):
            continue
        obstacle_type = str(getattr(obstacle, "obstacle_type", "")).lower()
        if obstacle_type not in IMPASSABLE_OBSTACLE_TYPES:
            continue
        if point_inside_obstacle(obstacle, latitude, longitude):
            return obstacle
    return None


def get_effective_unit_speed(
    scenario: Any,
    unit: Any,
    base_speed: float,
) -> float:
    speed_factor = 1.0
    for obstacle in _active_obstacles(scenario):
        if not _affects_unit(obstacle, unit):
            continue
        obstacle_type = str(getattr(obstacle, "obstacle_type", "")).lower()
        if obstacle_type not in SPEED_OBSTACLE_TYPES:
            continue
        if not point_inside_obstacle(
            obstacle,
            _as_float(getattr(unit, "latitude", 0.0)),
            _as_float(getattr(unit, "longitude", 0.0)),
        ):
            continue
        penalty = min(1.0, max(0.0, _as_float(getattr(obstacle, "movement_penalty", 0.0))))
        speed_factor = min(speed_factor, 1.0 - penalty)
    return max(0.0, base_speed * speed_factor)


def get_environment_detection_range(
    scenario: Any,
    detector: Any,
    threat: Any,
    base_detection_range_nm: float,
) -> float:
    detection_factor = 1.0
    for obstacle in _active_obstacles(scenario):
        if not _affects_unit(obstacle, detector):
            continue
        obstacle_type = str(getattr(obstacle, "obstacle_type", "")).lower()
        if obstacle_type not in SENSOR_OBSTACLE_TYPES:
            continue
        detector_inside = point_inside_obstacle(
            obstacle,
            _as_float(getattr(detector, "latitude", 0.0)),
            _as_float(getattr(detector, "longitude", 0.0)),
        )
        threat_inside = point_inside_obstacle(
            obstacle,
            _as_float(getattr(threat, "latitude", 0.0)),
            _as_float(getattr(threat, "longitude", 0.0)),
        )
        if not (detector_inside or threat_inside):
            continue
        penalty = min(1.0, max(0.0, _as_float(getattr(obstacle, "detection_penalty", 0.0))))
        detection_factor = min(detection_factor, 1.0 - penalty)
    return max(0.0, base_detection_range_nm * detection_factor)
