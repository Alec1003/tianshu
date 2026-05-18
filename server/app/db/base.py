"""SQLAlchemy declarative base shared by every model.

Splitting Base into its own module avoids circular imports between models
that reference each other (e.g. user <-> workspace <-> scenario).
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Project-wide declarative base. Add naming conventions here later."""

    pass
