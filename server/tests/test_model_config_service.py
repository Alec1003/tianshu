from __future__ import annotations

import pytest

from app.ai.model_config_service import (
    AIModelProviderConfigUpdate,
    list_model_provider_configs,
    resolve_stored_model_credentials,
    upsert_model_provider_config,
)
from app.ai.models import ModelCheckRequest, ModelCheckResponse
from app.api import ai as ai_api


@pytest.mark.asyncio
async def test_model_provider_config_encrypts_and_resolves_api_key(db_session, user):
    saved = await upsert_model_provider_config(
        db_session,
        user,
        "openai",
        AIModelProviderConfigUpdate(
            displayName="OpenAI",
            baseUrl="https://api.openai.com/v1",
            apiKey="sk-test",
            enabled=True,
            verified=True,
        ),
    )

    assert saved.apiKeySet is True
    assert saved.baseUrl == "https://api.openai.com/v1"
    providers = await list_model_provider_configs(db_session, user)
    assert providers[0].apiKeySet is True
    api_key, base_url = await resolve_stored_model_credentials(
        db_session,
        user,
        provider_id="openai",
        provider="openai",
        base_url="",
    )
    assert api_key == "sk-test"
    assert base_url == "https://api.openai.com/v1"


@pytest.mark.asyncio
async def test_model_provider_config_preserves_api_key_when_update_omits_it(
    db_session,
    user,
):
    await upsert_model_provider_config(
        db_session,
        user,
        "openai",
        AIModelProviderConfigUpdate(
            displayName="OpenAI",
            baseUrl="https://api.openai.com/v1",
            apiKey="sk-original",
            enabled=True,
            verified=True,
        ),
    )

    saved = await upsert_model_provider_config(
        db_session,
        user,
        "openai",
        AIModelProviderConfigUpdate(
            displayName="OpenAI",
            baseUrl="https://gateway.example.com/v1",
            enabled=True,
            verified=False,
        ),
    )

    assert saved.apiKeySet is True
    api_key, base_url = await resolve_stored_model_credentials(
        db_session,
        user,
        provider_id="openai",
        provider="openai",
        base_url="",
    )
    assert api_key == "sk-original"
    assert base_url == "https://gateway.example.com/v1"


@pytest.mark.asyncio
async def test_model_check_uses_stored_user_credentials_when_api_key_is_blank(
    db_session,
    user,
    monkeypatch,
):
    await upsert_model_provider_config(
        db_session,
        user,
        "openai",
        AIModelProviderConfigUpdate(
            displayName="OpenAI",
            baseUrl="https://api.openai.com/v1",
            apiKey="sk-stored",
            enabled=True,
            verified=True,
        ),
    )
    captured = {}

    def fake_check(payload: ModelCheckRequest) -> ModelCheckResponse:
        captured["providerId"] = payload.providerId
        captured["provider"] = payload.provider
        captured["baseUrl"] = payload.baseUrl
        captured["apiKey"] = payload.apiKey
        return ModelCheckResponse(
            status="ok",
            message="ok",
            provider=payload.provider,
            endpoint=f"{payload.baseUrl}/models",
            auth_ok=True,
            models_listed=True,
        )

    monkeypatch.setattr(ai_api, "check_model_connectivity", fake_check)

    result = await ai_api.check_model(
        ModelCheckRequest(
            providerId="openai",
            provider="openai",
            baseUrl="https://api.openai.com/v1",
            apiKey="",
            model="gpt-4o-mini",
        ),
        session=db_session,
        user=user,
    )

    assert result.status == "ok"
    assert captured == {
        "providerId": "openai",
        "provider": "openai",
        "baseUrl": "https://api.openai.com/v1",
        "apiKey": "sk-stored",
    }
