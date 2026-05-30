"""Policy helpers for user-configured LLM provider endpoints."""

from __future__ import annotations

from app.config import Settings, get_settings
from app.security.url_guard import normalize_and_validate_base_url

_LOCAL_MODEL_PROVIDERS = {"ollama"}


def allows_private_model_network(provider: str, settings: Settings | None = None) -> bool:
    provider_name = provider.strip().lower()
    if provider_name in _LOCAL_MODEL_PROVIDERS:
        return True
    active_settings = settings or get_settings()
    return active_settings.private_model_base_urls_allowed


def normalize_model_base_url(
    provider: str,
    base_url: str,
    settings: Settings | None = None,
) -> str:
    return normalize_and_validate_base_url(
        base_url,
        allow_private_network=allows_private_model_network(provider, settings),
    )
