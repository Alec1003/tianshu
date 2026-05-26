"""SQLAlchemy model for persisted per-user runtime snapshots."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

# Keep this import before GUID; fastapi-users patches exports during auth model
# import and Docker startup is sensitive to the ordering.
from app.auth.models import User as _User  # noqa: F401
from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

RUNTIME_STATE_JSON = JSON().with_variant(JSONB, "postgresql")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid_pk():
    return mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )


class RuntimeState(Base):
    """Latest authoritative backend Runtime snapshot for one user."""

    __tablename__ = "runtime_state"

    id: Mapped[str] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("user.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    scenario: Mapped[dict] = mapped_column(RUNTIME_STATE_JSON, nullable=False)
    runtime_metadata: Mapped[dict] = mapped_column(
        RUNTIME_STATE_JSON,
        default=dict,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class RuntimeEvent(Base):
    """Replay/AAR timeline event for one user's authoritative runtime."""

    __tablename__ = "runtime_event"
    __table_args__ = (
        Index("ix_runtime_event_owner_created", "owner_id", "created_at"),
        Index(
            "ix_runtime_event_owner_scenario_created",
            "owner_id",
            "scenario_id",
            "created_at",
        ),
        Index("ix_runtime_event_owner_type_created", "owner_id", "event_type", "created_at"),
    )

    id: Mapped[str] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    scenario_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    actor: Mapped[str] = mapped_column(String(32), default="system", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload: Mapped[dict] = mapped_column(RUNTIME_STATE_JSON, default=dict, nullable=False)
    unit_changes: Mapped[list] = mapped_column(
        RUNTIME_STATE_JSON,
        default=list,
        nullable=False,
    )
    current_time: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    proposal_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    aar_record_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        server_default=func.now(),
        nullable=False,
    )
