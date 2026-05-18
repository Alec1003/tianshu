"""Async DB engine + session factory + FastAPI dependency.

Usage::

    from app.db.session import get_async_session

    @router.get("/items")
    async def list_items(session: AsyncSession = Depends(get_async_session)):
        ...
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

_settings = get_settings()

# echo=False: turn on locally for SQL trace; keep off in CI to reduce noise.
engine = create_async_engine(_settings.database_url, echo=False, future=True)
async_session_maker = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async session bound to the request."""
    async with async_session_maker() as session:
        yield session


async def create_db_and_tables() -> None:
    """Best-effort dev/test bootstrap.

    For first runs without Alembic in place we fall back to ``Base.metadata
    .create_all``. Production deploys MUST run ``alembic upgrade head`` instead
    so schema evolution stays auditable.
    """
    # Imported here to avoid circular imports when this module is reused by
    # the migration env.py. v1 keeps the schema flat: User + Scenario +
    # AarRecord. Workspace/Member tables are deferred to S4 (multi-user
    # collaboration) -- adding them now would only inflate code surface.
    from app.auth.models import User  # noqa: F401
    from app.scenarios.models import (  # noqa: F401
        AarRecord,
        Scenario,
    )
    from app.db.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
