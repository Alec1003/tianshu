"""Scenario + AarRecord SQLAlchemy models.

v1 schema (flat, single-user-owned):
    Scenario       -- player-saved or system-template scenario JSON
    AarRecord      -- post-game After-Action-Review record per played session

Workspace / WorkspaceMember tables are intentionally deferred to S4 when we
introduce multi-user collaboration. Adding them now would only inflate the
code surface without serving the v1 user story.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid_pk():
    """UUID primary-key helper. Stored as string for portability across
    SQLite (no native UUID) and PostgreSQL (native uuid type later)."""
    return mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )


SCENARIO_JSON = JSON().with_variant(JSONB, "postgresql")


class Scenario(Base):
    """A scenario the user can load into the tactical platform.

    ``is_template=True`` rows are seeded from the JSON files under
    ``client/src/scenarios/`` and are read-only for non-superusers; they show
    up in every user's "templates" list.

    ``owner_id`` is nullable so system templates (no human owner) coexist with
    user-saved scenarios. It uses the same GUID type as ``User.id`` so
    PostgreSQL can enforce the foreign key. List endpoints filter by
    ``owner_id == me OR
    is_template == true`` to give the right scoping.
    """

    __tablename__ = "scenario"

    id: Mapped[str] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Whole scenario JSON (sides, units, missions, ...). SQLite maps this to a
    # JSON-text affinity, while PostgreSQL stores it as JSONB.
    data: Mapped[dict] = mapped_column(SCENARIO_JSON, nullable=False)

    is_template: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # 项目状态：草稿 / 推演中 / 已完成。
    # - draft     : 刚创建、还未开始推演
    # - running   : 用户进入过推演状态（点过「开始」但未结束）
    # - completed : gameOutcome.ended === true
    # MVP 阶段状态转换由前端在保存/归档时明示传入。
    status: Mapped[str] = mapped_column(
        String(16), default="draft", nullable=False
    )

    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    aar_records: Mapped[list["AarRecord"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan", lazy="selectin"
    )


class AarRecord(Base):
    """One after-action-review entry per finished simulation session.

    The frontend posts the snapshot of game.gameOutcome + per-side stats here
    when a game ends. We keep ``scenario_id`` nullable so AARs from imported
    JSONs (no scenario row) still get archived.
    """

    __tablename__ = "aar_record"

    id: Mapped[str] = _uuid_pk()

    scenario_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("scenario.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    outcome_reason: Mapped[str] = mapped_column(String(40), nullable=False)
    winner_side_id: Mapped[str] = mapped_column(String(80), default="", nullable=False)

    # JSON: { scenarioName, endedAt, elapsedSeconds, sides:[{id,name,score,...}] }
    summary: Mapped[dict] = mapped_column(SCENARIO_JSON, nullable=False)

    ended_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    scenario: Mapped["Scenario | None"] = relationship(back_populates="aar_records")
