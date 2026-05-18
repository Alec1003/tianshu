"""Application settings loaded from env / .env.

We intentionally keep this minimal: only secrets and DB connection live here.
Other tunables remain hard-coded until the platform grows multi-tenant config.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # SQLite DB path lives under /app/server/data which is volume-mounted in
    # docker-compose so user data survives container rebuilds.
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/aicc.db",
        description="Async SQLAlchemy DSN. SQLite for dev, PostgreSQL in prod.",
    )

    # JWT signing secret. MUST be overridden in production via env var.
    jwt_secret: str = Field(
        default="aicc-dev-secret-change-me-in-production",
        description="Secret used to sign JWT tokens. Override via env in prod.",
    )
    jwt_lifetime_seconds: int = Field(default=60 * 60 * 24 * 7)  # 7d

    # First user auto-becomes superuser; useful in dev. Disable in shared envs.
    first_user_is_superuser: bool = Field(default=True)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="AICC_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
