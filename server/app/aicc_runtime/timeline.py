"""Replay/AAR timeline persistence for authoritative runtime events."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.aicc_runtime.models import RuntimeEvent

UNIT_COLLECTIONS: tuple[tuple[str, str], ...] = (
    ("aircraft", "aircraft"),
    ("ships", "ship"),
    ("facilities", "facility"),
    ("airbases", "airbase"),
    ("weapons", "weapon"),
    ("referencePoints", "reference_point"),
    ("obstacles", "obstacle"),
)

NESTED_UNIT_COLLECTIONS: tuple[tuple[str, str], ...] = (
    ("aircraft", "aircraft"),
    ("weapons", "weapon"),
)

TRACKED_UNIT_FIELDS = (
    "id",
    "name",
    "sideId",
    "className",
    "latitude",
    "longitude",
    "altitude",
    "heading",
    "speed",
    "currentFuel",
    "maxFuel",
    "fuelRate",
    "range",
    "route",
    "rtb",
    "targetId",
    "currentQuantity",
    "maxQuantity",
    "lethality",
    "selected",
    "active",
    "isObjective",
    "isTanker",
    "fuelOffloadCapacity",
    "fuelTransferRate",
    "refuelRange",
    "isElectronicWarfare",
    "jammingRange",
    "jammingStrength",
    "jammingModes",
    "communicationDisruption",
    "homeBaseId",
    "radiusNm",
    "obstacleType",
    "active",
    "movementPenalty",
    "detectionPenalty",
    "communicationPenalty",
    "affectedDomains",
    "description",
)


def _owner_uuid(user: Any) -> uuid.UUID | None:
    raw = getattr(user, "id", None)
    if isinstance(raw, uuid.UUID):
        return raw
    try:
        return uuid.UUID(str(raw))
    except (TypeError, ValueError, AttributeError):
        return None


def _current_scenario(scenario: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(scenario, dict):
        return {}
    inner = scenario.get("currentScenario")
    return inner if isinstance(inner, dict) else scenario


def runtime_scenario_id(scenario: dict[str, Any] | None) -> str | None:
    inner = _current_scenario(scenario)
    value = inner.get("id")
    return str(value) if value else None


def runtime_current_time(scenario: dict[str, Any] | None) -> int | None:
    inner = _current_scenario(scenario)
    value = inner.get("currentTime")
    if value is None:
        value = inner.get("startTime")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _unit_summary(
    unit: dict[str, Any],
    unit_type: str,
    *,
    location: str,
    container_id: str = "",
) -> dict[str, Any]:
    out = {
        "unitType": unit_type,
        "unitId": str(unit.get("id") or ""),
        "location": location,
    }
    if container_id:
        out["containerId"] = container_id
    for field in TRACKED_UNIT_FIELDS:
        if field in unit:
            out[field] = _json_safe(unit.get(field))
    return out


def _iter_units(
    scenario: dict[str, Any] | None,
) -> Iterable[tuple[tuple[str, str], dict[str, Any]]]:
    inner = _current_scenario(scenario)
    for collection, unit_type in UNIT_COLLECTIONS:
        rows = inner.get(collection)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict) or not row.get("id"):
                continue
            key = (unit_type, str(row["id"]))
            yield key, _unit_summary(row, unit_type, location=collection)

            if unit_type not in {"ship", "facility", "airbase"}:
                continue
            for nested_collection, nested_type in NESTED_UNIT_COLLECTIONS:
                nested_rows = row.get(nested_collection)
                if not isinstance(nested_rows, list):
                    continue
                for nested in nested_rows:
                    if not isinstance(nested, dict) or not nested.get("id"):
                        continue
                    nested_key = (nested_type, str(nested["id"]))
                    yield nested_key, _unit_summary(
                        nested,
                        nested_type,
                        location=f"{collection}.{nested_collection}",
                        container_id=str(row["id"]),
                    )


def diff_runtime_unit_changes(
    before_scenario: dict[str, Any] | None,
    after_scenario: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if before_scenario is None or after_scenario is None:
        return []

    before = dict(_iter_units(before_scenario))
    after = dict(_iter_units(after_scenario))
    changes: list[dict[str, Any]] = []

    for key in sorted(after.keys() - before.keys()):
        unit = after[key]
        changes.append(
            {
                "change_type": "added",
                "unit_type": key[0],
                "unit_id": key[1],
                "name": str(unit.get("name") or ""),
                "side_id": str(unit.get("sideId") or ""),
                "after": unit,
            }
        )

    for key in sorted(before.keys() - after.keys()):
        unit = before[key]
        changes.append(
            {
                "change_type": "removed",
                "unit_type": key[0],
                "unit_id": key[1],
                "name": str(unit.get("name") or ""),
                "side_id": str(unit.get("sideId") or ""),
                "before": unit,
            }
        )

    for key in sorted(before.keys() & after.keys()):
        before_unit = before[key]
        after_unit = after[key]
        field_changes = {
            field: {
                "before": before_unit.get(field),
                "after": after_unit.get(field),
            }
            for field in sorted(set(before_unit) | set(after_unit))
            if before_unit.get(field) != after_unit.get(field)
        }
        if not field_changes:
            continue
        changes.append(
            {
                "change_type": "updated",
                "unit_type": key[0],
                "unit_id": key[1],
                "name": str(after_unit.get("name") or before_unit.get("name") or ""),
                "side_id": str(after_unit.get("sideId") or before_unit.get("sideId") or ""),
                "fields": field_changes,
            }
        )

    return changes


def _category_for_event(event_type: str) -> str:
    return event_type.split(".", 1)[0] if "." in event_type else "runtime"


async def record_runtime_event(
    session: AsyncSession,
    user: Any,
    *,
    event_type: str,
    action: str = "",
    actor: str = "system",
    summary: str = "",
    payload: dict[str, Any] | None = None,
    runtime: Any | None = None,
    before_scenario: dict[str, Any] | None = None,
    after_scenario: dict[str, Any] | None = None,
    scenario_id: str | None = None,
    proposal_id: str | None = None,
    aar_record_id: str | None = None,
    unit_changes: list[dict[str, Any]] | None = None,
) -> RuntimeEvent | None:
    owner_id = _owner_uuid(user)
    if owner_id is None:
        return None

    if after_scenario is None and runtime is not None:
        try:
            after_scenario = runtime.get_exported_scenario()
        except AttributeError:
            after_scenario = None

    effective_scenario_id = (
        scenario_id
        or runtime_scenario_id(after_scenario)
        or runtime_scenario_id(before_scenario)
    )
    current_time = runtime_current_time(after_scenario)
    if current_time is None:
        current_time = runtime_current_time(before_scenario)
    changes = unit_changes
    if changes is None:
        changes = diff_runtime_unit_changes(before_scenario, after_scenario)

    record = RuntimeEvent(
        owner_id=owner_id,
        scenario_id=effective_scenario_id,
        event_type=event_type,
        category=_category_for_event(event_type),
        action=action,
        actor=actor,
        summary=summary,
        payload=_json_safe(payload or {}),
        unit_changes=_json_safe(changes),
        current_time=current_time,
        proposal_id=proposal_id,
        aar_record_id=aar_record_id,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


async def list_runtime_events(
    session: AsyncSession,
    user: Any,
    *,
    scenario_id: str | Sequence[str] | None = None,
    event_type: str | None = None,
    category: str | None = None,
    limit: int = 200,
) -> Sequence[RuntimeEvent]:
    owner_id = _owner_uuid(user)
    if owner_id is None:
        return []

    stmt = select(RuntimeEvent).where(RuntimeEvent.owner_id == owner_id)
    if scenario_id:
        scenario_ids = (
            [scenario_id]
            if isinstance(scenario_id, str)
            else [item for item in scenario_id if item]
        )
        if scenario_ids:
            stmt = stmt.where(RuntimeEvent.scenario_id.in_(scenario_ids))
    if event_type:
        stmt = stmt.where(RuntimeEvent.event_type == event_type)
    if category:
        stmt = stmt.where(RuntimeEvent.category == category)
    stmt = stmt.order_by(RuntimeEvent.created_at.asc(), RuntimeEvent.id.asc()).limit(
        max(1, min(limit, 500))
    )
    result = await session.execute(stmt)
    return result.scalars().all()
