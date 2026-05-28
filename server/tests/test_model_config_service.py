from __future__ import annotations

import pytest

from app.ai.model_config_service import (
    list_model_provider_configs,
    resolve_stored_model_credentials,
    upsert_model_provider_config,
    AIModelProviderConfigUpdate,
)


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
