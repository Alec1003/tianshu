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


def _engine_kwargs() -> dict:
    kwargs = {"echo": False, "future": True}
    if not _settings.database_url.strip().startswith("sqlite"):
        kwargs.update(
            pool_size=_settings.database_pool_size,
            max_overflow=_settings.database_max_overflow,
            pool_timeout=_settings.database_pool_timeout_seconds,
            pool_recycle=_settings.database_pool_recycle_seconds,
            pool_pre_ping=True,
        )
    return kwargs


# echo=False: turn on locally for SQL trace; keep off in CI to reduce noise.
engine = create_async_engine(_settings.database_url, **_engine_kwargs())
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

    We also run a tiny dev-only schema migration step so existing SQLite
    files can pick up new columns added between commits without losing the
    user data we already accumulated. SQLAlchemy's ``create_all`` is
    idempotent at the *table* level but does NOT add new columns to existing
    tables -- hence the explicit ``ALTER TABLE ADD COLUMN`` block below.
    """
    # Imported here to avoid circular imports when this module is reused by
    # the migration env.py. v1 keeps the schema flat: User + Scenario +
    # AarRecord + UnitAsset + command approval proposals.
    # Workspace/Member tables are deferred to S4
    # (multi-user collaboration) -- adding them now would only inflate code
    # surface.
    from app.ai.command_models import (  # noqa: F401
        CommandProposalRecord,
        CommandProposalStepRecord,
    )
    from app.ai.model_config_models import AIModelProviderConfig  # noqa: F401
    from app.aicc_runtime.models import RuntimeEvent, RuntimeState  # noqa: F401
    from app.auth.models import User  # noqa: F401
    from app.scenarios.models import (  # noqa: F401
        AarRecord,
        Scenario,
        TrainingScoreRecord,
    )
    from app.unit_assets.models import UnitAsset  # noqa: F401
    from app.db.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _bootstrap_schema_migrations(conn)


async def _bootstrap_schema_migrations(conn) -> None:
    """Ad-hoc dev-only ALTER TABLE block.

    SQLite supports ``ALTER TABLE ... ADD COLUMN`` natively (since 3.2),
    and PostgreSQL supports it too, so the same SQL works on both backends
    we target. Each entry below should:

      - be idempotent (we check for the column first via PRAGMA / pg_attribute);
      - default to a non-NULL value so existing rows pass NOT NULL;
      - mirror the corresponding ``mapped_column`` declaration in models.py.

    Alembic is now the production path; this helper remains only as a
    backwards-compatible dev bootstrap for existing local SQLite files.
    """
    backend = conn.engine.dialect.name
    if backend == "postgresql":
        await _migrate_command_proposal_scope_postgres(conn)
        await _migrate_unit_asset_scope_postgres(conn)
        await _migrate_runtime_state_scope_postgres(conn)
        return

    from sqlalchemy import text

    if backend != "sqlite":
        return

    # Each row = (table, column, sql to add). Order matters only when one
    # column references another (none today).
    pending: list[tuple[str, str, str]] = [
        (
            "scenario",
            "status",
            "ALTER TABLE scenario ADD COLUMN status VARCHAR(16) "
            "NOT NULL DEFAULT 'draft'",
        ),
    ]

    for table, column, ddl in pending:
        result = await conn.execute(text(f"PRAGMA table_info({table})"))
        existing_cols = {row[1] for row in result.fetchall()}
        if column in existing_cols:
            continue
        await conn.execute(text(ddl))

    await _migrate_unit_asset_scope_sqlite(conn)
    await _migrate_runtime_state_scope_sqlite(conn)
    await _migrate_command_proposal_scope_sqlite(conn)


async def _migrate_unit_asset_scope_postgres(conn) -> None:
    """Replace the old global unit-asset unique constraint with scoped indexes."""
    from sqlalchemy import text

    await conn.execute(
        text("ALTER TABLE unit_asset DROP CONSTRAINT IF EXISTS uq_unit_asset_type_name")
    )
    await conn.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_unit_asset_system_type_name "
            "ON unit_asset (type, name) WHERE owner_id IS NULL"
        )
    )
    await conn.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_unit_asset_owner_type_name "
            "ON unit_asset (owner_id, type, name) WHERE owner_id IS NOT NULL"
        )
    )


async def _migrate_command_proposal_scope_postgres(conn) -> None:
    """Add scenario scoping to AI command approval proposals."""
    from sqlalchemy import text

    await conn.execute(
        text(
            "ALTER TABLE command_proposal "
            "ADD COLUMN IF NOT EXISTS scenario_id VARCHAR(120) "
            "NOT NULL DEFAULT '__default__'"
        )
    )
    await conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_command_proposal_owner_scenario_status "
            "ON command_proposal (owner_id, scenario_id, status)"
        )
    )


async def _migrate_runtime_state_scope_postgres(conn) -> None:
    """Move runtime_state from per-user to per-user/per-scenario snapshots."""
    from sqlalchemy import text

    await conn.execute(
        text(
            "ALTER TABLE runtime_state "
            "ADD COLUMN IF NOT EXISTS scenario_id VARCHAR(120) "
            "NOT NULL DEFAULT '__default__'"
        )
    )
    await conn.execute(
        text("ALTER TABLE runtime_state DROP CONSTRAINT IF EXISTS runtime_state_owner_id_key")
    )
    await conn.execute(
        text("ALTER TABLE runtime_state DROP CONSTRAINT IF EXISTS ix_runtime_state_owner_id")
    )
    await conn.execute(text("DROP INDEX IF EXISTS ix_runtime_state_owner_id"))
    await conn.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_runtime_state_owner_scenario "
            "ON runtime_state (owner_id, scenario_id)"
        )
    )


async def _migrate_unit_asset_scope_sqlite(conn) -> None:
    """Rebuild SQLite unit_asset table if it still has the old global unique key."""
    from sqlalchemy import text

    result = await conn.execute(
        text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'unit_asset'")
    )
    create_sql = result.scalar_one_or_none() or ""
    if "uq_unit_asset_type_name" not in create_sql and "UNIQUE (type, name)" not in create_sql:
        return

    from app.unit_assets.models import UnitAsset

    await conn.execute(text("ALTER TABLE unit_asset RENAME TO unit_asset_legacy"))
    await conn.run_sync(lambda sync_conn: UnitAsset.__table__.create(sync_conn))
    await conn.execute(
        text(
            """
            INSERT INTO unit_asset (
                id, type, name, data, is_system, owner_id, version, created_at, updated_at
            )
            SELECT
                id, type, name, data, is_system, owner_id, version, created_at, updated_at
            FROM unit_asset_legacy
            """
        )
    )
    await conn.execute(text("DROP TABLE unit_asset_legacy"))


async def _migrate_runtime_state_scope_sqlite(conn) -> None:
    """Rebuild SQLite runtime_state when it still stores one snapshot per user."""
    from sqlalchemy import text

    result = await conn.execute(
        text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'runtime_state'")
    )
    create_sql = result.scalar_one_or_none() or ""
    if not create_sql:
        return
    result = await conn.execute(text("PRAGMA table_info(runtime_state)"))
    existing_cols = {row[1] for row in result.fetchall()}
    has_scenario_id = "scenario_id" in existing_cols
    has_old_unique_owner = "UNIQUE (owner_id)" in create_sql
    if has_scenario_id and not has_old_unique_owner:
        return

    from app.aicc_runtime.models import RuntimeState

    scenario_expr = "scenario_id" if has_scenario_id else "'__default__'"
    await conn.execute(text("ALTER TABLE runtime_state RENAME TO runtime_state_legacy"))
    await conn.run_sync(lambda sync_conn: RuntimeState.__table__.create(sync_conn))
    await conn.execute(
        text(
            f"""
            INSERT INTO runtime_state (
                id, owner_id, scenario_id, scenario, runtime_metadata,
                version, created_at, updated_at
            )
            SELECT
                id, owner_id, {scenario_expr}, scenario, runtime_metadata,
                version, created_at, updated_at
            FROM runtime_state_legacy
            """
        )
    )
    await conn.execute(text("DROP TABLE runtime_state_legacy"))


async def _migrate_command_proposal_scope_sqlite(conn) -> None:
    """Add scenario scope to SQLite command proposals for existing dev DBs."""
    from sqlalchemy import text

    result = await conn.execute(text("PRAGMA table_info(command_proposal)"))
    existing_cols = {row[1] for row in result.fetchall()}
    if "scenario_id" not in existing_cols:
        await conn.execute(
            text(
                "ALTER TABLE command_proposal ADD COLUMN scenario_id VARCHAR(120) "
                "NOT NULL DEFAULT '__default__'"
            )
        )
    await conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_command_proposal_owner_scenario_status "
            "ON command_proposal (owner_id, scenario_id, status)"
        )
    )
