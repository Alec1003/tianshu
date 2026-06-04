"""Application settings loaded from env / .env.

We intentionally keep this minimal: only secrets and DB connection live here.
Other tunables remain hard-coded until the platform grows multi-tenant config.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.compat import install_legacy_env_aliases

DEFAULT_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"
DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./data/tianshu.db"
DEFAULT_SKILLS_DIR = "./data/skills"
DEFAULT_JWT_SECRET = "tianshu-dev-secret-change-me-in-production"
MIN_PRODUCTION_JWT_SECRET_LENGTH = 32
MIN_PRODUCTION_MODEL_CONFIG_SECRET_LENGTH = 32

install_legacy_env_aliases(
    [
        "TIANSHU_ENV",
        "TIANSHU_JWT_SECRET",
        "TIANSHU_JWT_LIFETIME_SECONDS",
        "TIANSHU_FIRST_USER_IS_SUPERUSER",
        "TIANSHU_DATABASE_URL",
        "TIANSHU_DATABASE_POOL_SIZE",
        "TIANSHU_DATABASE_MAX_OVERFLOW",
        "TIANSHU_DATABASE_POOL_TIMEOUT_SECONDS",
        "TIANSHU_DATABASE_POOL_RECYCLE_SECONDS",
        "TIANSHU_SKILLS_DIR",
        "TIANSHU_CORS_ORIGINS",
        "TIANSHU_LLM_MODEL",
        "TIANSHU_LLM_API_KEY",
        "TIANSHU_LLM_BASE_URL",
        "TIANSHU_ALLOW_PRIVATE_MODEL_BASE_URLS",
        "TIANSHU_EXTERNAL_MCP_SERVERS",
        "TIANSHU_MODEL_CONFIG_SECRET",
        "TIANSHU_MCP_HTTP_DEV_USER_ID",
        "TIANSHU_MCP_USER_ID",
    ]
)


def parse_cors_origins(raw: str) -> list[str]:
    """Parse and validate comma-separated CORS origins.

    CORS is an API trust boundary. Keep it explicit: wildcard origins are
    rejected because the backend accepts authenticated browser requests.
    """
    origins: list[str] = []
    seen: set[str] = set()
    for part in raw.split(","):
        origin = part.strip().rstrip("/")
        if not origin:
            continue
        if origin == "*":
            raise ValueError("TIANSHU_CORS_ORIGINS must list explicit origins, not '*'")
        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"invalid CORS origin: {origin!r}")
        if parsed.path or parsed.params or parsed.query or parsed.fragment:
            raise ValueError(f"CORS origin must not include path/query: {origin!r}")
        if origin not in seen:
            seen.add(origin)
            origins.append(origin)
    return origins


class Settings(BaseSettings):
    # Runtime environment. Production enables fail-fast safety checks for
    # settings that are convenient in dev but dangerous for shared deployments.
    env: Literal["development", "test", "production"] = Field(
        default="development",
        description="Runtime environment name.",
    )

    # SQLite DB path lives under /app/server/data which is volume-mounted in
    # docker-compose so user data survives container rebuilds.
    database_url: str = Field(
        default=DEFAULT_DATABASE_URL,
        description="Async SQLAlchemy DSN. SQLite for dev, PostgreSQL in prod.",
    )
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)
    database_pool_timeout_seconds: int = Field(default=30, ge=1)
    database_pool_recycle_seconds: int = Field(default=1800, ge=1)
    skills_dir: str = Field(
        default=DEFAULT_SKILLS_DIR,
        description=(
            "Folder-backed custom AI skills store. Keep this writable for "
            "desktop/exe packaging and Docker volume deployments."
        ),
    )

    # JWT signing secret. MUST be overridden in production via env var.
    jwt_secret: str = Field(
        default=DEFAULT_JWT_SECRET,
        description="Secret used to sign JWT tokens. Override via env in prod.",
    )
    jwt_lifetime_seconds: int = Field(default=60 * 60 * 24 * 7)  # 7d

    # Explicit browser origins allowed to call the API. Production deployments
    # should set this to their real HTTPS origin(s); keep empty to disable
    # cross-origin browser access when the frontend is served same-origin.
    cors_origins: str = Field(
        default=DEFAULT_CORS_ORIGINS,
        description="Comma-separated HTTP(S) origins allowed by CORS.",
    )

    # First user auto-becomes superuser; useful in dev. Disable in shared envs.
    first_user_is_superuser: bool = Field(default=True)

    # ── S4: Pydantic AI agent ─────────────────────────────────────────────────
    # Format: "<provider>:<model-name>", e.g. "openai:gpt-4o" or
    # "anthropic:claude-3-5-sonnet-20241022". Empty string disables the LLM
    # agent and falls back to the built-in regex planner.
    llm_model: str = Field(default="", description="Pydantic-AI model ID.")
    llm_api_key: str = Field(default="", description="API key for the LLM provider.")
    llm_base_url: str = Field(default="", description="Optional custom base URL (proxy / local LLM).")
    allow_private_model_base_urls: bool = Field(
        default=False,
        description=(
            "Allow user-configured LLM Base URLs to target private/local networks. "
            "Development and test environments allow this automatically; production "
            "must opt in explicitly."
        ),
    )
    external_mcp_servers: str = Field(
        default="",
        description=(
            "JSON array of operator-configured external MCP servers that the "
            "LLM agent may list and call."
        ),
    )
    mcp_http_dev_user_id: str = Field(
        default="",
        description="Dev-only HTTP MCP auth bypass user id.",
    )
    mcp_user_id: str = Field(
        default="",
        description="Dev-only stdio MCP auth bypass user id.",
    )
    model_config_secret: str = Field(
        default="",
        description=(
            "Secret used to encrypt per-user model provider API keys. "
            "Defaults to TIANSHU_JWT_SECRET in development only."
        ),
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="TIANSHU_",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return parse_cors_origins(self.cors_origins)

    @property
    def private_model_base_urls_allowed(self) -> bool:
        if self.env in {"development", "test"}:
            return True
        return self.allow_private_model_base_urls


def validate_production_settings(settings: Settings) -> None:
    """Fail fast on dev-only settings when running in production."""
    if settings.env != "production":
        return

    errors: list[str] = []
    jwt_secret = settings.jwt_secret.strip()
    if jwt_secret == DEFAULT_JWT_SECRET:
        errors.append("TIANSHU_JWT_SECRET must override the development default")
    if len(jwt_secret) < MIN_PRODUCTION_JWT_SECRET_LENGTH:
        errors.append(
            "TIANSHU_JWT_SECRET must be at least "
            f"{MIN_PRODUCTION_JWT_SECRET_LENGTH} characters"
        )
    if settings.first_user_is_superuser:
        errors.append("TIANSHU_FIRST_USER_IS_SUPERUSER must be false in production")
    if settings.database_url.strip().startswith("sqlite"):
        errors.append("TIANSHU_DATABASE_URL must use PostgreSQL in production")
    if settings.mcp_http_dev_user_id.strip():
        errors.append("TIANSHU_MCP_HTTP_DEV_USER_ID must be unset in production")
    if settings.mcp_user_id.strip():
        errors.append("TIANSHU_MCP_USER_ID must be unset in production")
    model_secret = settings.model_config_secret.strip()
    if len(model_secret) < MIN_PRODUCTION_MODEL_CONFIG_SECRET_LENGTH:
        errors.append(
            "TIANSHU_MODEL_CONFIG_SECRET must be at least "
            f"{MIN_PRODUCTION_MODEL_CONFIG_SECRET_LENGTH} characters"
        )
    if model_secret == jwt_secret:
        errors.append("TIANSHU_MODEL_CONFIG_SECRET must be distinct from TIANSHU_JWT_SECRET")

    if errors:
        raise RuntimeError("Unsafe production settings: " + "; ".join(errors))


@lru_cache
def get_settings() -> Settings:
    return Settings()
