"""Scenario + AarRecord SQLAlchemy models.

v1 schema (flat, single-user-owned):
    Scenario              -- player-saved or system-template scenario JSON
    AarRecord             -- post-game After-Action-Review record per played session
    TrainingScoreRecord   -- immutable score snapshot for a played session
    ScenarioCompareReport -- persisted scenario comparison snapshot
    ScenarioCompareSession -- persisted compare workspace session

Workspace / WorkspaceMember tables are intentionally deferred to S4 when we
introduce multi-user collaboration. Adding them now would only inflate the
code surface without serving the v1 user story.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

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
BRANCH_META_KEY = "_tianshu_branch"


def extract_branch_meta(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    raw = data.get(BRANCH_META_KEY)
    if not isinstance(raw, dict):
        return None

    parent_scenario_id = str(raw.get("parent_scenario_id", "")).strip()
    root_scenario_id = str(raw.get("root_scenario_id", "")).strip()
    parent_scenario_name = str(raw.get("parent_scenario_name", "")).strip()
    root_scenario_name = str(raw.get("root_scenario_name", "")).strip()
    branch_label = str(raw.get("branch_label", "")).strip()
    if not parent_scenario_id or not root_scenario_id:
        return None

    branch_depth_raw = raw.get("branch_depth", 1)
    try:
        branch_depth = max(1, int(branch_depth_raw))
    except (TypeError, ValueError):
        branch_depth = 1

    created_from_version_raw = raw.get("created_from_version")
    try:
        created_from_version = (
            int(created_from_version_raw)
            if created_from_version_raw is not None
            else None
        )
    except (TypeError, ValueError):
        created_from_version = None

    created_at = raw.get("created_at")
    created_at_value = str(created_at).strip() if created_at is not None else None

    return {
        "parent_scenario_id": parent_scenario_id,
        "parent_scenario_name": parent_scenario_name,
        "root_scenario_id": root_scenario_id,
        "root_scenario_name": root_scenario_name or parent_scenario_name,
        "branch_label": branch_label or f"分支 {branch_depth}",
        "branch_depth": branch_depth,
        "created_from_version": created_from_version,
        "created_at": created_at_value or None,
    }


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

    @staticmethod
    def _scenario_root(data: dict | None) -> dict:
        if not isinstance(data, dict):
            return {}
        root = data.get("currentScenario")
        return root if isinstance(root, dict) else data

    @staticmethod
    def _list_len(root: dict, key: str) -> int:
        value = root.get(key)
        return len(value) if isinstance(value, list) else 0

    @staticmethod
    def _nested_aircraft_count(root: dict, carrier_key: str) -> int:
        carriers = root.get(carrier_key)
        if not isinstance(carriers, list):
            return 0
        count = 0
        for carrier in carriers:
            if not isinstance(carrier, dict):
                continue
            aircraft = carrier.get("aircraft")
            if isinstance(aircraft, list):
                count += len(aircraft)
        return count

    @property
    def mission_count(self) -> int:
        root = self._scenario_root(self.data)
        return self._list_len(root, "missions")

    @property
    def side_count(self) -> int:
        root = self._scenario_root(self.data)
        return self._list_len(root, "sides")

    @property
    def unit_count(self) -> int:
        root = self._scenario_root(self.data)
        return (
            self._list_len(root, "aircraft")
            + self._nested_aircraft_count(root, "airbases")
            + self._nested_aircraft_count(root, "ships")
            + self._list_len(root, "ships")
            + self._list_len(root, "facilities")
            + self._list_len(root, "airbases")
        )

    @property
    def branch_meta(self) -> dict[str, Any] | None:
        return extract_branch_meta(self.data)

    aar_records: Mapped[list["AarRecord"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan", lazy="selectin"
    )
    training_score_records: Mapped[list["TrainingScoreRecord"]] = relationship(
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


class TrainingScoreRecord(Base):
    """Immutable training score snapshot for score history and comparison."""

    __tablename__ = "training_score_record"

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
    runtime_scenario_id: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        index=True,
    )
    aar_record_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("aar_record.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    overall_score: Mapped[int] = mapped_column(Integer, nullable=False)
    grade: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[dict] = mapped_column(SCENARIO_JSON, nullable=False)
    metrics: Mapped[dict] = mapped_column(SCENARIO_JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    scenario: Mapped["Scenario | None"] = relationship(
        back_populates="training_score_records"
    )


class ScenarioCompareReport(Base):
    """Persisted scenario comparison snapshot for later review/export."""

    __tablename__ = "scenario_compare_report"

    id: Mapped[str] = _uuid_pk()

    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    baseline_scenario_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    scenario_ids: Mapped[list[str]] = mapped_column(
        SCENARIO_JSON,
        default=list,
        nullable=False,
    )
    snapshot: Mapped[dict] = mapped_column(SCENARIO_JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ScenarioCompareSession(Base):
    """Persisted compare workspace session for multi-branch evaluation."""

    __tablename__ = "scenario_compare_session"

    id: Mapped[str] = _uuid_pk()

    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    source_scenario_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    baseline_scenario_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    scenario_ids: Mapped[list[str]] = mapped_column(
        SCENARIO_JSON,
        default=list,
        nullable=False,
    )
    state: Mapped[dict] = mapped_column(
        SCENARIO_JSON,
        default=dict,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
