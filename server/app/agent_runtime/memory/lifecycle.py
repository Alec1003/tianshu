from __future__ import annotations

from datetime import UTC, datetime

from app.agent_runtime.memory.models import MemoryItem, MemoryStatus, parse_time

ACTIVE_STATUSES: set[MemoryStatus] = {"confirmed", "active"}


def initial_status(*, confirmed: bool, system_marked: bool) -> MemoryStatus:
    if confirmed or system_marked:
        return "active"
    return "candidate"


def can_activate(*, confirmed: bool, system_marked: bool) -> bool:
    return confirmed or system_marked


def is_active(item: MemoryItem) -> bool:
    return item.status in ACTIVE_STATUSES and not is_expired(item)


def is_expired(item: MemoryItem, *, now: datetime | None = None) -> bool:
    expires_at = parse_time(item.expires_at)
    if expires_at is None:
        return False
    current = now or datetime.now(UTC)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= current
