from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.db import session as db_session_mod
from app.scenarios.models import Scenario


def _settings(database_url: str) -> SimpleNamespace:
    return SimpleNamespace(
        database_url=database_url,
        database_pool_size=7,
        database_max_overflow=3,
        database_pool_timeout_seconds=11,
        database_pool_recycle_seconds=101,
    )


def test_engine_kwargs_skip_pool_options_for_sqlite(monkeypatch) -> None:
    monkeypatch.setattr(
        db_session_mod,
        "_settings",
        _settings("sqlite+aiosqlite:///./data/aicc.db"),
    )

    kwargs = db_session_mod._engine_kwargs()

    assert kwargs == {"echo": False, "future": True}


def test_engine_kwargs_enable_pool_options_for_postgres(monkeypatch) -> None:
    monkeypatch.setattr(
        db_session_mod,
        "_settings",
        _settings("postgresql+asyncpg://aicc:secret@db/aicc"),
    )

    kwargs = db_session_mod._engine_kwargs()

    assert kwargs["pool_size"] == 7
    assert kwargs["max_overflow"] == 3
    assert kwargs["pool_timeout"] == 11
    assert kwargs["pool_recycle"] == 101
    assert kwargs["pool_pre_ping"] is True


def test_scenario_json_columns_compile_as_jsonb_for_postgres() -> None:
    ddl = str(CreateTable(Scenario.__table__).compile(dialect=postgresql.dialect()))

    assert "data JSONB NOT NULL" in ddl
