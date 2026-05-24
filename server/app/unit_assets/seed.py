"""Startup seed for default unit assets."""

from __future__ import annotations

from app.db.session import async_session_maker
from app.unit_assets.service import seed_default_unit_assets


async def seed_system_unit_assets() -> int:
    async with async_session_maker() as session:
        return await seed_default_unit_assets(session)

