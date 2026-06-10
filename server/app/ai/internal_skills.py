from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.ai.models import (
    InternalSkillDraft,
    InternalSkillMissionDraft,
    StructuredCommandStep,
)
from app.tianshu_runtime.matching import resolve_side_id as resolve_side_reference_id
from app.tianshu_runtime.runtime import TianShuRuntime

INTERNAL_SKILL_ALLOWED_RUNTIME_SKILLS = {
    "create_patrol_mission",
    "create_strike_mission",
    "move_unit",
}


def build_internal_skill_steps(
    runtime: TianShuRuntime,
    draft: InternalSkillDraft,
) -> list[StructuredCommandStep]:
    """Validate a constrained tactical skill draft and convert it to proposal steps."""

    allowed = set(draft.allowed_runtime_skills or INTERNAL_SKILL_ALLOWED_RUNTIME_SKILLS)
    disallowed = sorted(allowed - INTERNAL_SKILL_ALLOWED_RUNTIME_SKILLS)
    if disallowed:
        raise ValueError(f"Unsupported runtime skills in internal skill: {', '.join(disallowed)}")

    scenario = runtime.game.current_scenario
    side_id = _resolve_side_id(scenario, draft.side_id)
    assigned_once: set[str] = set()
    steps: list[StructuredCommandStep] = []

    for index, mission in enumerate(draft.missions):
        _validate_duplicate_assignments(
            mission,
            assigned_once,
            allow_duplicates=draft.allow_duplicate_assignments,
        )
        if mission.type == "patrol":
            _require_allowed(allowed, "create_patrol_mission")
            _validate_units(scenario, mission.assigned_unit_ids, side_id=side_id)
            _validate_reference_points(scenario, mission.reference_point_ids, side_id=side_id)
            steps.append(
                _step(
                    index,
                    "create_patrol_mission",
                    {
                        "name": mission.name,
                        "assigned_unit_ids": mission.assigned_unit_ids,
                        "reference_point_ids": mission.reference_point_ids,
                    },
                    mission,
                )
            )
            continue

        if mission.type == "strike":
            _require_allowed(allowed, "create_strike_mission")
            _validate_units(scenario, mission.assigned_unit_ids, side_id=side_id)
            _validate_targets(scenario, mission.assigned_target_ids, side_id=side_id)
            steps.append(
                _step(
                    index,
                    "create_strike_mission",
                    {
                        "name": mission.name,
                        "assigned_unit_ids": mission.assigned_unit_ids,
                        "assigned_target_ids": mission.assigned_target_ids,
                    },
                    mission,
                )
            )
            continue

        if mission.type == "move":
            _require_allowed(allowed, "move_unit")
            unit_id = _single_assigned_unit(mission)
            unit_type = _unit_type_for_id(scenario, unit_id)
            if unit_type not in {"aircraft", "ship"}:
                raise ValueError(f"Move mission unit must be aircraft or ship: {unit_id}")
            _validate_route(mission.route)
            _validate_units(scenario, [unit_id], side_id=side_id)
            steps.append(
                _step(
                    index,
                    "move_unit",
                    {
                        "unit_type": unit_type,
                        "unit_id": unit_id,
                        "route": mission.route,
                    },
                    mission,
                )
            )
            continue

        raise ValueError(f"Unsupported mission type: {mission.type}")

    return steps


def _step(
    index: int,
    skill: str,
    parameters: dict[str, Any],
    mission: InternalSkillMissionDraft,
) -> StructuredCommandStep:
    return StructuredCommandStep(
        id=f"internal-skill-step-{index + 1}-{uuid4()}",
        skill=skill,
        parameters=parameters,
        source_text=mission.notes or mission.name,
        summary=f"{mission.type}: {mission.name}",
        risk="medium",
        writes_runtime=True,
    )


def _resolve_side_id(scenario: Any, side_ref: str) -> str:
    if not side_ref:
        return ""
    side_id = resolve_side_reference_id(scenario.sides, side_ref)
    if side_id is not None:
        return side_id
    raise ValueError(f"Side not found in current scenario: {side_ref}")


def _validate_duplicate_assignments(
    mission: InternalSkillMissionDraft,
    assigned_once: set[str],
    *,
    allow_duplicates: bool,
) -> None:
    if allow_duplicates:
        return
    for unit_id in mission.assigned_unit_ids:
        if unit_id in assigned_once:
            raise ValueError(f"Unit assigned to multiple internal-skill missions: {unit_id}")
        assigned_once.add(unit_id)


def _single_assigned_unit(mission: InternalSkillMissionDraft) -> str:
    if len(mission.assigned_unit_ids) != 1:
        raise ValueError("Move mission requires exactly one assigned unit.")
    return mission.assigned_unit_ids[0]


def _require_allowed(allowed: set[str], skill: str) -> None:
    if skill not in allowed:
        raise ValueError(f"Internal skill is not allowed to use runtime skill: {skill}")


def _validate_units(scenario: Any, unit_ids: list[str], *, side_id: str) -> None:
    if not unit_ids:
        raise ValueError("Mission requires at least one assigned unit.")
    for unit_id in unit_ids:
        unit = _unit_for_id(scenario, unit_id)
        if unit is None:
            raise ValueError(f"Assigned unit not found: {unit_id}")
        if side_id and getattr(unit, "side_id", "") != side_id:
            raise ValueError(f"Assigned unit does not belong to requested side: {unit_id}")


def _validate_reference_points(
    scenario: Any, reference_point_ids: list[str], *, side_id: str
) -> None:
    if len(reference_point_ids) < 3:
        raise ValueError("Patrol mission requires at least three reference points.")
    for point_id in reference_point_ids:
        point = scenario.get_reference_point(point_id)
        if point is None:
            raise ValueError(f"Reference point not found: {point_id}")
        if side_id and getattr(point, "side_id", "") not in {"", side_id}:
            raise ValueError(f"Reference point does not belong to requested side: {point_id}")


def _validate_targets(scenario: Any, target_ids: list[str], *, side_id: str) -> None:
    if not target_ids:
        raise ValueError("Strike mission requires at least one target.")
    for target_id in target_ids:
        target = _unit_for_id(scenario, target_id)
        if target is None:
            raise ValueError(f"Strike target not found: {target_id}")
        if side_id and getattr(target, "side_id", "") == side_id:
            raise ValueError(f"Strike target belongs to the same side: {target_id}")


def _validate_route(route: list[list[float]]) -> None:
    if not route:
        raise ValueError("Move mission requires at least one route point.")
    for index, point in enumerate(route):
        if len(point) != 2:
            raise ValueError(f"Route point {index} must be [latitude, longitude].")
        latitude, longitude = point
        if latitude < -90 or latitude > 90 or longitude < -180 or longitude > 180:
            raise ValueError(f"Route point {index} is outside valid coordinates.")


def _unit_type_for_id(scenario: Any, unit_id: str) -> str:
    for unit_type, getter in (
        ("aircraft", scenario.get_aircraft),
        ("ship", scenario.get_ship),
        ("facility", scenario.get_facility),
        ("airbase", scenario.get_airbase),
    ):
        if getter(unit_id) is not None:
            return unit_type
    return ""


def _unit_for_id(scenario: Any, unit_id: str) -> Any | None:
    for getter in (
        scenario.get_aircraft,
        scenario.get_ship,
        scenario.get_facility,
        scenario.get_airbase,
    ):
        unit = getter(unit_id)
        if unit is not None:
            return unit
    return None
