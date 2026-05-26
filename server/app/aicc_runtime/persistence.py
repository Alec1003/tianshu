"""Persistence service for authoritative backend runtime state."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.aicc_runtime.models import RuntimeState

_LOADED_ATTR = "_aicc_runtime_state_loaded"


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
) -> RuntimeState | None:
    owner_id = _owner_uuid(user)
    if owner_id is None:
        return None
    stmt = select(RuntimeState).where(RuntimeState.owner_id == owner_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def restore_runtime_state(
    session: AsyncSession,
    user: Any,
    runtime: Any,
) -> RuntimeState | None:
    """Load the user's latest snapshot into ``runtime`` when one exists."""
    record = await load_runtime_state(session, user)
    if record is None:
        return None
    runtime.load_runtime_state(record.scenario, record.runtime_metadata or {})
    return record


async def ensure_runtime_state_loaded(
    session: AsyncSession,
    user: Any,
    runtime: Any,
) -> RuntimeState | None:
    """Restore once per in-memory runtime instance."""
    if getattr(runtime, _LOADED_ATTR, False):
        return None
    try:
        return await restore_runtime_state(session, user, runtime)
    finally:
        setattr(runtime, _LOADED_ATTR, True)


async def save_runtime_state(
    session: AsyncSession,
    user: Any,
    runtime: Any,
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

    record = await load_runtime_state(session, user)
    if record is None:
        record = RuntimeState(
            owner_id=owner_id,
            scenario=scenario,
            runtime_metadata=runtime_metadata,
            version=1,
        )
        session.add(record)
    else:
        record.scenario = scenario
        record.runtime_metadata = runtime_metadata
        record.version = int(record.version or 0) + 1

    await session.commit()
    await session.refresh(record)
    setattr(runtime, _LOADED_ATTR, True)
    return record
