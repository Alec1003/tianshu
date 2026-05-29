from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.ai.command_models import CommandProposalRecord
from app.ai.model_config_models import AIModelProviderConfig
from app.aicc_runtime.models import RuntimeEvent, RuntimeState
from app.auth.models import User
from app.db import session as db_session_mod
from app.scenarios.models import AarRecord, Scenario, TrainingScoreRecord
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
    training_score_ddl = str(
        CreateTable(TrainingScoreRecord.__table__).compile(
            dialect=postgresql.dialect()
        )
    )
    command_proposal_ddl = str(
        CreateTable(CommandProposalRecord.__table__).compile(
            dialect=postgresql.dialect()
        )
    )
    model_config_ddl = str(
        CreateTable(AIModelProviderConfig.__table__).compile(
            dialect=postgresql.dialect()
        )
    )

    assert "data JSONB NOT NULL" in ddl
    assert "data JSONB NOT NULL" in unit_ddl
    assert "scenario JSONB NOT NULL" in runtime_state_ddl
    assert "runtime_metadata JSONB NOT NULL" in runtime_state_ddl
    assert "scenario_id VARCHAR(120) NOT NULL" in runtime_state_ddl
    assert "payload JSONB NOT NULL" in runtime_event_ddl
    assert "unit_changes JSONB NOT NULL" in runtime_event_ddl
    assert "score JSONB NOT NULL" in training_score_ddl
    assert "metrics JSONB NOT NULL" in training_score_ddl
    assert "scenario_id VARCHAR(120) NOT NULL" in command_proposal_ddl
    assert "adjudication JSONB NOT NULL" in command_proposal_ddl
    assert "execution JSONB NOT NULL" in command_proposal_ddl
    assert "custom_models JSONB NOT NULL" in model_config_ddl


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
    training_score_ddl = str(
        CreateTable(TrainingScoreRecord.__table__).compile(
            dialect=postgresql.dialect()
        )
    )
    command_proposal_ddl = str(
        CreateTable(CommandProposalRecord.__table__).compile(
            dialect=postgresql.dialect()
        )
    )
    model_config_ddl = str(
        CreateTable(AIModelProviderConfig.__table__).compile(
            dialect=postgresql.dialect()
        )
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
    assert "owner_id UUID" in training_score_ddl
    assert 'FOREIGN KEY(owner_id) REFERENCES "user" (id)' in training_score_ddl
    assert "owner_id UUID NOT NULL" in command_proposal_ddl
    assert 'FOREIGN KEY(owner_id) REFERENCES "user" (id)' in command_proposal_ddl
    assert "owner_id UUID NOT NULL" in model_config_ddl
    assert 'FOREIGN KEY(owner_id) REFERENCES "user" (id)' in model_config_ddl


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


def test_runtime_state_has_scoped_unique_index_for_postgres() -> None:
    index_ddls = {
        index.name: str(CreateIndex(index).compile(dialect=postgresql.dialect()))
        for index in RuntimeState.__table__.indexes
    }

    assert (
        "CREATE UNIQUE INDEX ix_runtime_state_owner_scenario "
        "ON runtime_state (owner_id, scenario_id)"
    ) in index_ddls["ix_runtime_state_owner_scenario"]


def test_runtime_state_postgres_migration_drops_legacy_owner_unique_index() -> None:
    class FakeConn:
        def __init__(self) -> None:
            self.sql: list[str] = []

        async def execute(self, statement) -> None:
            self.sql.append(str(statement))

    conn = FakeConn()

    asyncio.run(db_session_mod._migrate_runtime_state_scope_postgres(conn))

    assert (
        "ALTER TABLE runtime_state DROP CONSTRAINT IF EXISTS ix_runtime_state_owner_id"
        in conn.sql
    )
    assert "DROP INDEX IF EXISTS ix_runtime_state_owner_id" in conn.sql
    assert (
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_runtime_state_owner_scenario "
        "ON runtime_state (owner_id, scenario_id)"
        in conn.sql
    )


def test_command_proposal_has_scenario_scope_index_for_postgres() -> None:
    index_ddls = {
        index.name: str(CreateIndex(index).compile(dialect=postgresql.dialect()))
        for index in CommandProposalRecord.__table__.indexes
    }

    assert (
        "CREATE INDEX ix_command_proposal_owner_scenario_status "
        "ON command_proposal (owner_id, scenario_id, status)"
    ) in index_ddls["ix_command_proposal_owner_scenario_status"]


def test_ai_model_provider_config_has_owner_provider_unique_index() -> None:
    index_ddls = {
        index.name: str(CreateIndex(index).compile(dialect=postgresql.dialect()))
        for index in AIModelProviderConfig.__table__.indexes
    }

    assert (
        "CREATE UNIQUE INDEX uq_ai_model_provider_owner_provider "
        "ON ai_model_provider_config (owner_id, provider_id)"
    ) in index_ddls["uq_ai_model_provider_owner_provider"]
