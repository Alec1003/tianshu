from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.aicc_runtime.models import RuntimeEvent, RuntimeState
from app.auth.models import User
from app.db import session as db_session_mod
from app.scenarios.models import AarRecord, Scenario
from app.unit_assets.models import UnitAsset


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
    unit_ddl = str(
        CreateTable(UnitAsset.__table__).compile(dialect=postgresql.dialect())
    )
    runtime_state_ddl = str(
        CreateTable(RuntimeState.__table__).compile(dialect=postgresql.dialect())
    )
    runtime_event_ddl = str(
        CreateTable(RuntimeEvent.__table__).compile(dialect=postgresql.dialect())
    )

    assert "data JSONB NOT NULL" in ddl
    assert "data JSONB NOT NULL" in unit_ddl
    assert "scenario JSONB NOT NULL" in runtime_state_ddl
    assert "runtime_metadata JSONB NOT NULL" in runtime_state_ddl
    assert "payload JSONB NOT NULL" in runtime_event_ddl
    assert "unit_changes JSONB NOT NULL" in runtime_event_ddl


def test_user_foreign_keys_compile_as_uuid_for_postgres() -> None:
    user_ddl = str(CreateTable(User.__table__).compile(dialect=postgresql.dialect()))
    scenario_ddl = str(
        CreateTable(Scenario.__table__).compile(dialect=postgresql.dialect())
    )
    aar_ddl = str(
        CreateTable(AarRecord.__table__).compile(dialect=postgresql.dialect())
    )
    unit_ddl = str(
        CreateTable(UnitAsset.__table__).compile(dialect=postgresql.dialect())
    )
    runtime_state_ddl = str(
        CreateTable(RuntimeState.__table__).compile(dialect=postgresql.dialect())
    )
    runtime_event_ddl = str(
        CreateTable(RuntimeEvent.__table__).compile(dialect=postgresql.dialect())
    )

    assert "id UUID NOT NULL" in user_ddl
    assert "owner_id UUID" in scenario_ddl
    assert 'FOREIGN KEY(owner_id) REFERENCES "user" (id)' in scenario_ddl
    assert "owner_id UUID" in aar_ddl
    assert 'FOREIGN KEY(owner_id) REFERENCES "user" (id)' in aar_ddl
    assert "owner_id UUID" in unit_ddl
    assert 'FOREIGN KEY(owner_id) REFERENCES "user" (id)' in unit_ddl
    assert "owner_id UUID NOT NULL" in runtime_state_ddl
    assert 'FOREIGN KEY(owner_id) REFERENCES "user" (id)' in runtime_state_ddl
    assert "owner_id UUID NOT NULL" in runtime_event_ddl
    assert 'FOREIGN KEY(owner_id) REFERENCES "user" (id)' in runtime_event_ddl


def test_unit_asset_has_scoped_unique_indexes_for_postgres() -> None:
    index_ddls = {
        index.name: str(CreateIndex(index).compile(dialect=postgresql.dialect()))
        for index in UnitAsset.__table__.indexes
    }

    assert (
        "CREATE UNIQUE INDEX uq_unit_asset_system_type_name "
        "ON unit_asset (type, name) WHERE owner_id IS NULL"
    ) in index_ddls["uq_unit_asset_system_type_name"]
    assert (
        "CREATE UNIQUE INDEX uq_unit_asset_owner_type_name "
        "ON unit_asset (owner_id, type, name) WHERE owner_id IS NOT NULL"
    ) in index_ddls["uq_unit_asset_owner_type_name"]
