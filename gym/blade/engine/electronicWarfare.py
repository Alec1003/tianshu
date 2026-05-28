from typing import Any

from blade.utils.constants import NAUTICAL_MILES_TO_METERS
from blade.utils.utils import get_distance_between_two_points


JAMMING_PLATFORMS = ("aircraft", "ships", "facilities")
DEFAULT_JAMMING_MODES = ("radar", "communications")
MAX_JAMMING_STRENGTH = 0.85
MIN_DETECTION_RANGE_FACTOR = 0.15


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _distance_nm(first: Any, second: Any) -> float:
    distance_km = get_distance_between_two_points(
        _as_float(getattr(first, "latitude", 0.0)),
        _as_float(getattr(first, "longitude", 0.0)),
        _as_float(getattr(second, "latitude", 0.0)),
        _as_float(getattr(second, "longitude", 0.0)),
    )
    return (distance_km * 1000) / NAUTICAL_MILES_TO_METERS


def _modes_for(unit: Any) -> list[str]:
    modes = getattr(unit, "jamming_modes", None)
    if isinstance(modes, list):
        normalized = [
            str(mode).strip().lower() for mode in modes if str(mode).strip()
        ]
        return normalized or list(DEFAULT_JAMMING_MODES)
    return list(DEFAULT_JAMMING_MODES)


def is_electronic_warfare_unit(unit: Any) -> bool:
    if bool(getattr(unit, "is_electronic_warfare", False)):
        return True
    class_name = str(getattr(unit, "class_name", "") or "").lower()
    name = str(getattr(unit, "name", "") or "").lower()
    tokens = (
        "electronic",
        "ewar",
        "jammer",
        "growler",
        "prowler",
        "raven",
        "电子战",
        "干扰",
    )
    return any(token in class_name or token in name for token in tokens)


def strongest_jamming_effect(
    current_scenario: Any,
    detector: Any,
    *,
    mode: str = "radar",
) -> float:
    detector_side_id = str(getattr(detector, "side_id", "") or "")
    if not detector_side_id:
        return 0.0

    normalized_mode = mode.strip().lower()
    strongest = 0.0
    for attr in JAMMING_PLATFORMS:
        for jammer in getattr(current_scenario, attr, []) or []:
            if jammer is detector or not is_electronic_warfare_unit(jammer):
                continue
            jammer_side_id = str(getattr(jammer, "side_id", "") or "")
            if not jammer_side_id or not current_scenario.is_hostile(
                detector_side_id, jammer_side_id
            ):
                continue
            modes = _modes_for(jammer)
            if normalized_mode not in modes and "all" not in modes:
                continue
            jamming_range = _as_float(getattr(jammer, "jamming_range", 0.0))
            if jamming_range <= 0 or _distance_nm(jammer, detector) > jamming_range:
                continue
            strength = _clamp(
                _as_float(getattr(jammer, "jamming_strength", 0.0)),
                0.0,
                MAX_JAMMING_STRENGTH,
            )
            strongest = max(strongest, strength)
    return strongest


def get_effective_detection_range(
    current_scenario: Any,
    detector: Any,
    *,
    mode: str = "radar",
) -> float:
    base_range = _as_float(detector.get_detection_range())
    if base_range <= 0:
        return 0.0
    jam_strength = strongest_jamming_effect(current_scenario, detector, mode=mode)
    if jam_strength <= 0:
        return base_range
    return max(base_range * MIN_DETECTION_RANGE_FACTOR, base_range * (1 - jam_strength))
