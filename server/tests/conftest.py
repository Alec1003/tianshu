"""pytest conftest: per-test in-memory SQLite + user fixtures.

为什么 in-memory：测试不能污染 dev SQLite 文件，也不能跨测试用例残留状态
（pyd 反例 9）。每个测试用独立 engine + 全建表，开销 ~10ms。

注意：``app.db.session`` 的 ``async_session_maker`` 是模块级常量绑定
``engine`` 的，所以测试里我们 monkey-patch 这两个全局，不重启进程。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.auth.models import User
from app.db.base import Base
from app.db import session as db_session_mod


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture(scope="function")
async def db_engine() -> AsyncIterator:
    """A fresh in-memory SQLite per test."""
    # SQLite shared cache: ``:memory:`` is per-connection by default, so we
    # use a named in-memory DB + URI flag to share across the test's session
    # pool. ``aiosqlite`` honours the same trick.
    engine = create_async_engine(
        "sqlite+aiosqlite:///file:test_aicc_mem?mode=memory&cache=shared&uri=true",
        future=True,
    )
    # Make sure tables are imported and registered on Base before create_all.
    from app.scenarios.models import AarRecord, Scenario  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture
async def session_maker(db_engine, monkeypatch) -> async_sessionmaker[AsyncSession]:
    """Bind the app's global session maker to the test engine so service
    code that imports ``async_session_maker`` directly still goes to the
    in-memory DB."""
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db_session_mod, "engine", db_engine)
    monkeypatch.setattr(db_session_mod, "async_session_maker", maker)
    return maker


@pytest_asyncio.fixture
async def db_session(session_maker) -> AsyncIterator[AsyncSession]:
    async with session_maker() as session:
        yield session


@pytest_asyncio.fixture
async def user(db_session) -> User:
    """A plain active non-superuser. UUID is stable per test for assertions."""
    u = User(
        id=uuid.uuid4(),
        email=f"u{uuid.uuid4().hex[:8]}@aicc.test",
        hashed_password="not-a-real-hash",
        is_active=True,
        is_superuser=False,
        is_verified=True,
        display_name="Tester",
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def other_user(db_session) -> User:
    """Another active user, used to assert cross-user 403 paths."""
    u = User(
        id=uuid.uuid4(),
        email=f"o{uuid.uuid4().hex[:8]}@aicc.test",
        hashed_password="not-a-real-hash",
        is_active=True,
        is_superuser=False,
        is_verified=True,
        display_name="Other",
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def superuser(db_session) -> User:
    u = User(
        id=uuid.uuid4(),
        email=f"s{uuid.uuid4().hex[:8]}@aicc.test",
        hashed_password="not-a-real-hash",
        is_active=True,
        is_superuser=True,
        is_verified=True,
        display_name="Super",
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u
