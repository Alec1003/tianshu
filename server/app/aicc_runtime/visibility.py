from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[3]
GYM_DIR = ROOT_DIR / "gym"

if str(GYM_DIR) not in sys.path:
    sys.path.insert(0, str(GYM_DIR))

from blade.utils.constants import NAUTICAL_MILES_TO_METERS  # type: ignore  # noqa: E402
from blade.utils.utils import get_distance_between_two_points  # type: ignore  # noqa: E402


VISIBLE_COLLECTIONS: tuple[tuple[str, str], ...] = (
    ("aircraft", "aircraft"),
    ("ships", "ships"),
    ("facilities", "facilities"),
    ("airbases", "airbases"),
    ("referencePoints", "reference_points"),
    ("weapons", "weapons"),
)
SENSOR_COLLECTIONS = ("aircraft", "ships", "facilities")


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _object_id(obj: Any) -> str:
    return str(getattr(obj, "id", "") or "")


def _object_side_id(obj: Any) -> str:
    return str(getattr(obj, "side_id", "") or "")


def _is_hostile_to_viewer(scenario: Any, viewer_side_id: str, side_id: str) -> bool:
    if not viewer_side_id or not side_id or viewer_side_id == side_id:
        return False
    return bool(scenario.is_hostile(viewer_side_id, side_id))


def _sensor_platforms_for_viewer(scenario: Any, viewer_side_id: str) -> list[Any]:
    sensors: list[Any] = []
    for attr in SENSOR_COLLECTIONS:
        for sensor in getattr(scenario, attr, []) or []:
            if _is_hostile_to_viewer(scenario, viewer_side_id, _object_side_id(sensor)):
                continue
            if callable(getattr(sensor, "get_detection_range", None)):
                sensors.append(sensor)
    return sensors


def _detected_by_viewer_sensors(
    scenario: Any,
    obj: Any,
    viewer_side_id: str,
    sensors: list[Any],
) -> bool:
    if not viewer_side_id:
        return True

    for sensor in sensors:
        detection_range_nm = _as_float(sensor.get_detection_range())
        if detection_range_nm <= 0:
            continue

        distance_km = get_distance_between_two_points(
            _as_float(getattr(sensor, "latitude", 0.0)),
            _as_float(getattr(sensor, "longitude", 0.0)),
            _as_float(getattr(obj, "latitude", 0.0)),
            _as_float(getattr(obj, "longitude", 0.0)),
        )
        distance_nm = (distance_km * 1000) / NAUTICAL_MILES_TO_METERS
        if distance_nm <= detection_range_nm:
            return True

    return False


def _compute_side_visibility(scenario: Any, viewer_side_id: str) -> dict[str, Any]:
    sensors = _sensor_platforms_for_viewer(scenario, viewer_side_id)
    visible_counts = {key: 0 for key, _attr in VISIBLE_COLLECTIONS}
    total_counts = {
        key: len(getattr(scenario, attr, []) or [])
        for key, attr in VISIBLE_COLLECTIONS
    }
    visible_object_ids: list[str] = []
    operational_detail_object_ids: list[str] = []
    detected_hostile_object_ids: list[str] = []

    for key, attr in VISIBLE_COLLECTIONS:
        for obj in getattr(scenario, attr, []) or []:
            obj_id = _object_id(obj)
            if not obj_id:
                continue

            hostile = _is_hostile_to_viewer(
                scenario, viewer_side_id, _object_side_id(obj)
            )
            detected = False
            if hostile:
                detected = _detected_by_viewer_sensors(
                    scenario, obj, viewer_side_id, sensors
                )
                visible = detected
            else:
                visible = True

            if visible:
                visible_object_ids.append(obj_id)
                visible_counts[key] += 1
            if not hostile:
                operational_detail_object_ids.append(obj_id)
            if hostile and detected:
                detected_hostile_object_ids.append(obj_id)

    return {
        "side_id": viewer_side_id,
        "visible_object_ids": visible_object_ids,
        "operational_detail_object_ids": operational_detail_object_ids,
        "detected_hostile_object_ids": detected_hostile_object_ids,
        "visible_counts": visible_counts,
        "total_counts": total_counts,
    }


def compute_runtime_visibility(
    scenario: Any,
    current_side_id: str | None = "",
) -> dict[str, Any]:
    """Compute map/inspector visibility from the authoritative Python runtime."""

    side_ids = [
        str(getattr(side, "id", "") or "")
        for side in (getattr(scenario, "sides", []) or [])
    ]
    side_ids = [side_id for side_id in side_ids if side_id]
    if current_side_id and current_side_id not in side_ids:
        side_ids.append(str(current_side_id))

    return {
        "current_side_id": str(current_side_id or ""),
        "by_side": {
            side_id: _compute_side_visibility(scenario, side_id)
            for side_id in side_ids
        },
    }
