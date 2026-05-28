"""SQLAlchemy persistence models for AI command approval proposals."""

from __future__ import annotations

import uuid
from datetime import datetime

# fastapi-users-db-sqlalchemy imports patch fastapi_users.db exports at import
# time. Load the auth model first so SQLAlchemyBaseUserTableUUID is available
# before GUID is imported, matching the rest of the app startup order.
from app.auth.models import User as _User  # noqa: F401
from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

COMMAND_JSON = JSON().with_variant(JSONB, "postgresql")


def _uuid_pk():
    return mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )


class CommandProposalRecord(Base):
    """Human approval proposal for a runtime-changing AI/MCP command."""

    __tablename__ = "command_proposal"
    __table_args__ = (
        Index("ix_command_proposal_owner_status", "owner_id", "status"),
        Index(
            "ix_command_proposal_owner_scenario_status",
            "owner_id",
            "scenario_id",
            "status",
        ),
    )

    id: Mapped[str] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scenario_id: Mapped[str] = mapped_column(
        String(120),
        default="__default__",
        nullable=False,
        index=True,
    )

    command: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    adjudication: Mapped[dict] = mapped_column(COMMAND_JSON, nullable=False)
    execution: Mapped[list] = mapped_column(COMMAND_JSON, default=list, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    steps: Mapped[list["CommandProposalStepRecord"]] = relationship(
        back_populates="proposal",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="CommandProposalStepRecord.position",
    )


class CommandProposalStepRecord(Base):
    """One structured simulation action inside a command proposal."""

    __tablename__ = "command_proposal_step"
    __table_args__ = (
        Index("ix_command_proposal_step_proposal_position", "proposal_id", "position"),
    )

    id: Mapped[str] = _uuid_pk()
    proposal_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("command_proposal.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    step_id: Mapped[str] = mapped_column(String(80), nullable=False)
    skill: Mapped[str] = mapped_column(String(80), nullable=False)
    parameters: Mapped[dict] = mapped_column(COMMAND_JSON, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    risk: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    writes_runtime: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    proposal: Mapped[CommandProposalRecord] = relationship(back_populates="steps")
