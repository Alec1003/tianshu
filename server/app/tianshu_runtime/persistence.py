"""Persistence service for authoritative backend runtime state."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.tianshu_runtime.models import RuntimeState

_LOADED_ATTR = "_tianshu_runtime_state_loaded"
DEFAULT_RUNTIME_SCENARIO_ID = "__default__"


def runtime_context_id(scenario_id: str | None = None) -> str:
    value = (scenario_id or "").strip()
    return value[:120] if value else DEFAULT_RUNTIME_SCENARIO_ID


def _owner_uuid(user: Any) -> uuid.UUID | None:
    raw = getattr(user, "id", None)
    if isinstance(raw, uuid.UUID):
        return raw
    try:
        return uuid.UUID(str(raw))
    except (TypeError, ValueError, AttributeError):
        return None


def runtime_persistence_supported(user: Any) -> bool:
    """Return whether ``user`` can be safely scoped in the DB."""
    return _owner_uuid(user) is not None


async def load_runtime_state(
    session: AsyncSession,
    user: Any,
    scenario_id: str | None = None,
) -> RuntimeState | None:
    owner_id = _owner_uuid(user)
    if owner_id is None:
        return None
    stmt = select(RuntimeState).where(
        RuntimeState.owner_id == owner_id,
        RuntimeState.scenario_id == runtime_context_id(scenario_id),
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def restore_runtime_state(
    session: AsyncSession,
    user: Any,
    runtime: Any,
    scenario_id: str | None = None,
) -> RuntimeState | None:
    """Load the user's latest snapshot into ``runtime`` when one exists."""
    record = await load_runtime_state(session, user, scenario_id=scenario_id)
    if record is None:
        return None
    runtime.load_runtime_state(record.scenario, record.runtime_metadata or {})
    return record


async def ensure_runtime_state_loaded(
    session: AsyncSession,
    user: Any,
    runtime: Any,
    scenario_id: str | None = None,
) -> RuntimeState | None:
    """Restore once per in-memory runtime instance."""
    if getattr(runtime, _LOADED_ATTR, False):
        return None
    try:
        return await restore_runtime_state(
            session,
            user,
            runtime,
            scenario_id=scenario_id,
        )
    finally:
        setattr(runtime, _LOADED_ATTR, True)


async def save_runtime_state(
    session: AsyncSession,
    user: Any,
    runtime: Any,
    scenario_id: str | None = None,
) -> RuntimeState | None:
    """Upsert the latest authoritative runtime snapshot for ``user``."""
    owner_id = _owner_uuid(user)
    if owner_id is None:
        setattr(runtime, _LOADED_ATTR, True)
        return None

    if hasattr(runtime, "export_runtime_state"):
        state = runtime.export_runtime_state()
        scenario = state.get("scenario") or {}
        runtime_metadata = state.get("runtime_metadata") or {}
    else:
        scenario = runtime.get_exported_scenario()
        runtime_metadata = {
            "paused": bool(getattr(runtime.game, "scenario_paused", True)),
            "currentSideId": getattr(runtime.game, "current_side_id", ""),
            "gameOutcome": getattr(runtime.game, "game_outcome", {}) or {},
        }

    context_id = runtime_context_id(scenario_id)
    record = await load_runtime_state(session, user, scenario_id=context_id)
    if record is None:
        record = RuntimeState(
            owner_id=owner_id,
            scenario_id=context_id,
            scenario=scenario,
            runtime_metadata=runtime_metadata,
            version=1,
        )
        session.add(record)
    else:
        record.scenario_id = context_id
        record.scenario = scenario
        record.runtime_metadata = runtime_metadata
        record.version = int(record.version or 0) + 1

    await session.commit()
    await session.refresh(record)
    setattr(runtime, _LOADED_ATTR, True)
    return record
