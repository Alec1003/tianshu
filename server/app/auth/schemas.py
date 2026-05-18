"""Pydantic DTOs exposed by /auth/* endpoints.

fastapi-users uses these to validate/serialise the wire shape, distinct from
the SQLAlchemy ``User`` model (DB shape).
"""

from __future__ import annotations

import uuid

from fastapi_users import schemas
from pydantic import Field


class UserRead(schemas.BaseUser[uuid.UUID]):
    display_name: str = ""


class UserCreate(schemas.BaseUserCreate):
    display_name: str = Field(default="", max_length=80)


class UserUpdate(schemas.BaseUserUpdate):
    display_name: str | None = Field(default=None, max_length=80)
