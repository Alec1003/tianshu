"""SQLAlchemy model for platform unit assets."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

UNIT_ASSET_JSON = JSON().with_variant(JSONB, "postgresql")


def _uuid_pk():
    return mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )


class UnitAsset(Base):
    """A reusable unit model available to the tactical workspace.

    ``is_system=True`` rows are seeded defaults. User-created rows are scoped to
    the creating user for edits, while list endpoints expose system rows plus
    the caller's custom rows. The canonical per-type payload remains in
    ``data`` so the existing simulator unit database can be reconstructed
    without lossy column splitting.
    """

    __tablename__ = "unit_asset"
    __table_args__ = (
        Index(
            "uq_unit_asset_system_type_name",
            "type",
            "name",
            unique=True,
            sqlite_where=text("owner_id IS NULL"),
            postgresql_where=text("owner_id IS NULL"),
        ),
        Index(
            "uq_unit_asset_owner_type_name",
            "owner_id",
            "type",
            "name",
            unique=True,
            sqlite_where=text("owner_id IS NOT NULL"),
            postgresql_where=text("owner_id IS NOT NULL"),
        ),
    )

    id: Mapped[str] = _uuid_pk()
    type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    data: Mapped[dict] = mapped_column(UNIT_ASSET_JSON, nullable=False)

    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
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
