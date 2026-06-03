from __future__ import annotations

import pytest

from app.config import (
    DEFAULT_CORS_ORIGINS,
    DEFAULT_DATABASE_URL,
    DEFAULT_JWT_SECRET,
    DEFAULT_SKILLS_DIR,
    MIN_PRODUCTION_MODEL_CONFIG_SECRET_LENGTH,
    MIN_PRODUCTION_JWT_SECRET_LENGTH,
    Settings,
    parse_cors_origins,
    validate_production_settings,
)


def test_default_cors_origins_are_explicit_local_frontends() -> None:
    settings = Settings()

    assert settings.cors_origin_list == parse_cors_origins(DEFAULT_CORS_ORIGINS)
    assert "*" not in settings.cors_origin_list


def test_default_skills_dir_points_to_server_data_folder() -> None:
    assert Settings().skills_dir == DEFAULT_SKILLS_DIR
    assert DEFAULT_SKILLS_DIR == "./data/skills"


def test_parse_cors_origins_trims_deduplicates_and_strips_trailing_slash() -> None:
    assert parse_cors_origins(
        " http://localhost:3000/ , https://app.example.com, http://localhost:3000 "
    ) == ["http://localhost:3000", "https://app.example.com"]


@pytest.mark.parametrize(
    "raw",
    [
        "*",
        "https://app.example.com,*",
        "localhost:3000",
        "https://app.example.com/path",
        "https://app.example.com?x=1",
    ],
)
def test_parse_cors_origins_rejects_wildcard_and_non_origin_values(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_cors_origins(raw)


def test_production_rejects_default_jwt_secret() -> None:
    settings = Settings(
        env="production",
        database_url="postgresql+asyncpg://tianshu:secret@db/tianshu",
        jwt_secret=DEFAULT_JWT_SECRET,
        first_user_is_superuser=False,
    )

    with pytest.raises(RuntimeError, match="TIANSHU_JWT_SECRET"):
        validate_production_settings(settings)


def test_production_rejects_short_jwt_secret() -> None:
    settings = Settings(
        env="production",
        database_url="postgresql+asyncpg://tianshu:secret@db/tianshu",
        jwt_secret="short-secret",
        first_user_is_superuser=False,
    )

    with pytest.raises(RuntimeError, match="at least"):
        validate_production_settings(settings)


def test_production_rejects_first_user_superuser_bootstrap() -> None:
    settings = Settings(
        env="production",
        database_url="postgresql+asyncpg://tianshu:secret@db/tianshu",
        jwt_secret="x" * MIN_PRODUCTION_JWT_SECRET_LENGTH,
        first_user_is_superuser=True,
    )

    with pytest.raises(RuntimeError, match="TIANSHU_FIRST_USER_IS_SUPERUSER"):
        validate_production_settings(settings)


def test_production_rejects_sqlite_database() -> None:
    settings = Settings(
        env="production",
        database_url=DEFAULT_DATABASE_URL,
        jwt_secret="x" * MIN_PRODUCTION_JWT_SECRET_LENGTH,
        first_user_is_superuser=False,
    )

    with pytest.raises(RuntimeError, match="TIANSHU_DATABASE_URL"):
        validate_production_settings(settings)


def test_production_accepts_hardened_settings() -> None:
    settings = Settings(
        env="production",
        database_url="postgresql+asyncpg://tianshu:secret@db/tianshu",
        jwt_secret="x" * MIN_PRODUCTION_JWT_SECRET_LENGTH,
        model_config_secret="m" * MIN_PRODUCTION_MODEL_CONFIG_SECRET_LENGTH,
        first_user_is_superuser=False,
    )

    validate_production_settings(settings)


def test_development_allows_dev_defaults() -> None:
    settings = Settings(env="development")

    validate_production_settings(settings)


def test_private_model_base_urls_are_dev_default_and_prod_opt_in() -> None:
    assert Settings(env="development").private_model_base_urls_allowed is True
    assert Settings(env="test").private_model_base_urls_allowed is True
    assert Settings(env="production").private_model_base_urls_allowed is False
    assert (
        Settings(
            env="production",
            allow_private_model_base_urls=True,
        ).private_model_base_urls_allowed
        is True
    )
