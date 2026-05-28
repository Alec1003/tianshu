"""Persisted per-user AI model provider configuration."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.auth.models import User as _User  # noqa: F401
from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

MODEL_CONFIG_JSON = JSON().with_variant(JSONB, "postgresql")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid_pk():
    return mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )


class AIModelProviderConfig(Base):
    """User-owned provider settings with encrypted API credentials."""

    __tablename__ = "ai_model_provider_config"
    __table_args__ = (
        Index(
            "uq_ai_model_provider_owner_provider",
            "owner_id",
            "provider_id",
            unique=True,
        ),
    )

    id: Mapped[str] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    base_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    api_key_ciphertext: Mapped[str] = mapped_column(Text, default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_checked_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    custom_models: Mapped[list] = mapped_column(
        MODEL_CONFIG_JSON,
        default=list,
        nullable=False,
    )
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
