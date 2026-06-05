"""SQLAlchemy User model.

We extend ``SQLAlchemyBaseUserTable`` (UUID variant) so fastapi-users can
hand the row to its UserManager. ``display_name`` is project-specific and
shows up in the top-bar user menu.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(SQLAlchemyBaseUserTableUUID, Base):
    """TianShu user. id/email/hashed_password/is_active/is_superuser/is_verified
    are inherited from fastapi-users base."""

    display_name: Mapped[str] = mapped_column(String(80), default="", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
