"""Service layer for user-owned AI model provider configuration."""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.model_config_models import AIModelProviderConfig
from app.auth.models import User
from app.config import get_settings


class AIModelProviderConfigRead(BaseModel):
    providerId: str
    displayName: str = ""
    baseUrl: str = ""
    enabled: bool = False
    verified: bool = False
    isDefault: bool = False
    lastCheckedAt: str | None = None
    customModels: list[dict[str, Any]] = Field(default_factory=list)
    apiKeySet: bool = False


class AIModelProviderConfigList(BaseModel):
    providers: list[AIModelProviderConfigRead]


class AIModelProviderConfigUpdate(BaseModel):
    displayName: str = ""
    baseUrl: str = ""
    apiKey: str | None = None
    clearApiKey: bool = False
    enabled: bool = False
    verified: bool = False
    lastCheckedAt: str | None = None
    customModels: list[dict[str, Any]] = Field(default_factory=list)


@lru_cache(maxsize=1)
def _secret_box() -> Fernet:
    settings = get_settings()
    material = (settings.model_config_secret or settings.jwt_secret).encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(material).digest())
    return Fernet(key)


def encrypt_model_api_key(api_key: str) -> str:
    value = api_key.strip()
    if not value:
        return ""
    return _secret_box().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_model_api_key(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _secret_box().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


def _owner_id(user: User) -> Any:
    return user.id


def _record_to_read(record: AIModelProviderConfig) -> AIModelProviderConfigRead:
    return AIModelProviderConfigRead(
        providerId=record.provider_id,
        displayName=record.display_name,
        baseUrl=record.base_url,
        enabled=record.enabled,
        verified=record.verified,
        isDefault=record.is_default,
        lastCheckedAt=record.last_checked_at,
        customModels=list(record.custom_models or []),
        apiKeySet=bool(record.api_key_ciphertext),
    )


async def list_model_provider_configs(
    session: AsyncSession,
    user: User,
) -> list[AIModelProviderConfigRead]:
    result = await session.execute(
        select(AIModelProviderConfig)
        .where(AIModelProviderConfig.owner_id == _owner_id(user))
        .order_by(AIModelProviderConfig.provider_id)
    )
    return [_record_to_read(record) for record in result.scalars().all()]


async def get_model_provider_record(
    session: AsyncSession,
    user: User,
    provider_id: str,
) -> AIModelProviderConfig | None:
    result = await session.execute(
        select(AIModelProviderConfig).where(
            AIModelProviderConfig.owner_id == _owner_id(user),
            AIModelProviderConfig.provider_id == provider_id.strip(),
        )
    )
    return result.scalar_one_or_none()


async def upsert_model_provider_config(
    session: AsyncSession,
    user: User,
    provider_id: str,
    payload: AIModelProviderConfigUpdate,
) -> AIModelProviderConfigRead:
    normalized_provider_id = provider_id.strip()
    record = await get_model_provider_record(session, user, normalized_provider_id)
    if record is None:
        record = AIModelProviderConfig(
            owner_id=_owner_id(user),
            provider_id=normalized_provider_id,
        )
        session.add(record)

    record.display_name = payload.displayName.strip()
    record.base_url = payload.baseUrl.strip()
    record.enabled = payload.enabled
    record.verified = payload.verified
    record.last_checked_at = payload.lastCheckedAt
    record.custom_models = payload.customModels
    if payload.clearApiKey:
        record.api_key_ciphertext = ""
    elif payload.apiKey is not None and payload.apiKey.strip():
        record.api_key_ciphertext = encrypt_model_api_key(payload.apiKey)

    await session.commit()
    await session.refresh(record)
    return _record_to_read(record)


async def resolve_stored_model_credentials(
    session: AsyncSession,
    user: User,
    *,
    provider_id: str,
    provider: str,
    base_url: str,
) -> tuple[str, str]:
    """Return stored ``(api_key, base_url)`` for a request override.

    ``provider_id`` is the UI identity (for custom profiles); ``provider`` is
    the runtime provider passed to pydantic-ai. We accept either so older
    clients that only send the runtime provider can still resolve built-ins.
    """

    candidates = [provider_id.strip(), provider.strip()]
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        record = await get_model_provider_record(session, user, candidate)
        if record is None:
            continue
        return (
            decrypt_model_api_key(record.api_key_ciphertext),
            base_url.strip() or record.base_url,
        )
    return "", base_url.strip()


async def set_default_model_provider(
    session: AsyncSession,
    user: User,
    provider_id: str,
) -> AIModelProviderConfigRead | None:
    """Set *provider_id* as the sole default, unsetting any prior default."""
    normalized = provider_id.strip()

    # Unset any existing default for this user
    result = await session.execute(
        select(AIModelProviderConfig).where(
            AIModelProviderConfig.owner_id == _owner_id(user),
            AIModelProviderConfig.is_default.is_(True),
        )
    )
    for record in result.scalars().all():
        record.is_default = False

    # Set the requested one as default
    target = await get_model_provider_record(session, user, normalized)
    if target is None:
        return None
    target.is_default = True
    await session.commit()
    await session.refresh(target)
    return _record_to_read(target)


async def resolve_default_model_config(
    session: AsyncSession,
    user: User,
) -> tuple[str, str, str, str]:
    """Resolve the default model configuration.

    Returns ``(provider_id, provider, model_name, base_url)`` from the
    user's default provider config. If no default is set, returns empty
    strings — callers should fall back to env vars or raise.
    """
    result = await session.execute(
        select(AIModelProviderConfig).where(
            AIModelProviderConfig.owner_id == _owner_id(user),
            AIModelProviderConfig.is_default.is_(True),
            AIModelProviderConfig.enabled.is_(True),
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        return "", "", "", ""

    # Pick the first verified custom model, or any model
    model_name = ""
    for m in record.custom_models or []:
        model_name = str(m.get("id", "") or "").strip()
        if model_name:
            break

    return (
        record.provider_id,
        record.provider_id,
        model_name,
        record.base_url,
    )


async def resolve_model_config_by_id(
    session: AsyncSession,
    user: User,
    provider_id: str,
) -> tuple[str, str, str, str]:
    """Resolve a model config by explicit provider_id.

    Returns ``(provider_id, provider, model_name, base_url)`` plus the
    decrypted api_key is returned separately for security.
    """
    record = await get_model_provider_record(session, user, provider_id.strip())
    if record is None:
        return "", "", "", ""

    model_name = ""
    for m in record.custom_models or []:
        model_name = str(m.get("id", "") or "").strip()
        if model_name:
            break

    return (
        record.provider_id,
        record.provider_id,
        model_name,
        record.base_url,
    )
