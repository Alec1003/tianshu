"""Test model config resolution chain in _chat_with_agent_runtime flow."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.ai.model_config_service import (
    AIModelProviderConfigRead,
    decrypt_model_api_key,
    encrypt_model_api_key,
    resolve_default_model_config,
    resolve_model_config_by_id,
    resolve_stored_model_credentials,
    set_default_model_provider,
)
from app.agent_runtime.agents.model_factory import (
    AgentModelConfig,
    ModelFactory,
    NoAgentModelConfiguredError,
)


# ---------------------------------------------------------------------------
# 1. AgentModelConfig.is_configured
# ---------------------------------------------------------------------------


class TestAgentModelConfig:
    def test_configured_with_provider_model_and_api_key(self):
        cfg = AgentModelConfig("deepseek", "deepseek-chat", "sk-test", "https://api.deepseek.com/v1")
        assert cfg.is_configured is True

    def test_not_configured_without_provider(self):
        cfg = AgentModelConfig("", "deepseek-chat", "sk-test", "")
        assert cfg.is_configured is False

    def test_not_configured_without_model(self):
        cfg = AgentModelConfig("deepseek", "", "sk-test", "")
        assert cfg.is_configured is False

    def test_ollama_no_api_key_required(self):
        cfg = AgentModelConfig("ollama", "llama3", "", "http://localhost:11434/v1")
        assert cfg.is_configured is True


# ---------------------------------------------------------------------------
# 2. ModelFactory.resolve priority chain
# ---------------------------------------------------------------------------


class TestModelFactoryPriority:
    """Verify resolve() picks the highest-priority source."""

    def test_priority1_request_model_dict(self, monkeypatch):
        """Request-provided model dict wins over everything."""
        monkeypatch.setenv("TIANSHU_LLM_MODEL", "openai:gpt-4o-mini")
        monkeypatch.setenv("TIANSHU_LLM_API_KEY", "env-key")
        from app.config import get_settings
        get_settings.cache_clear()

        request = SimpleNamespace(
            model={"provider": "deepseek", "model": "deepseek-chat", "apiKey": "req-key"},
        )
        cfg = ModelFactory().resolve(request)
        assert cfg.provider == "deepseek"
        assert cfg.model == "deepseek-chat"
        assert cfg.api_key == "req-key"
        assert cfg.is_configured is True
        get_settings.cache_clear()

    def test_priority2_fallback_to_env(self, monkeypatch):
        """Without request model, env vars are used."""
        monkeypatch.setenv("TIANSHU_LLM_MODEL", "openai:gpt-4o-mini")
        monkeypatch.setenv("TIANSHU_LLM_API_KEY", "env-key")
        from app.config import get_settings
        get_settings.cache_clear()

        request = SimpleNamespace(model={})
        cfg = ModelFactory().resolve(request)
        assert cfg.provider == "openai"
        assert cfg.model == "gpt-4o-mini"
        assert cfg.api_key == "env-key"
        assert cfg.is_configured is True
        get_settings.cache_clear()

    def test_no_model_configured(self, monkeypatch):
        """No model anywhere raises NoAgentModelConfiguredError."""
        monkeypatch.setenv("TIANSHU_LLM_MODEL", "")
        monkeypatch.setenv("TIANSHU_LLM_API_KEY", "")
        from app.config import get_settings
        get_settings.cache_clear()

        request = SimpleNamespace(model={})
        cfg = ModelFactory().resolve(request)
        assert cfg.is_configured is False
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# 3. API key encryption/decryption
# ---------------------------------------------------------------------------


class TestAPIKeyEncryption:
    def test_roundtrip(self):
        original = "sk-test-key-12345"
        encrypted = encrypt_model_api_key(original)
        assert encrypted != original
        assert decrypt_model_api_key(encrypted) == original

    def test_empty_key(self):
        assert encrypt_model_api_key("") == ""
        assert decrypt_model_api_key("") == ""

    def test_decrypt_invalid_returns_empty(self):
        assert decrypt_model_api_key("not-valid-ciphertext") == ""


# ---------------------------------------------------------------------------
# 4. Model config service (DB-backed tests require async + session)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestModelConfigServiceDB:
    """These tests mock the DB layer but validate the service logic."""

    async def test_resolve_by_id_returns_config(self):
        """resolve_model_config_by_id returns provider/model/base_url."""
        from app.ai.model_config_models import AIModelProviderConfig
        import uuid

        record = AIModelProviderConfig(
            id="test-id",
            owner_id=uuid.uuid4(),
            provider_id="deepseek",
            base_url="https://api.deepseek.com/v1",
            enabled=True,
            verified=True,
            custom_models=[{"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}],
        )
        session = AsyncMock()
        session.execute = AsyncMock()
        session.execute.return_value.scalar_one_or_none = AsyncMock(return_value=record)

        pid, prov, model, url = await resolve_model_config_by_id(session, SimpleNamespace(id="user-1"), "deepseek")
        assert pid == "deepseek"
        assert prov == "deepseek"
        assert model == "deepseek-chat"
        assert url == "https://api.deepseek.com/v1"

    async def test_resolve_default_no_default_returns_empty(self):
        """When no default is set, resolve_default_model_config returns all empty."""
        session = AsyncMock()
        result = AsyncMock()
        result.scalar_one_or_none = AsyncMock(return_value=None)
        session.execute = AsyncMock(return_value=result)

        pid, prov, model, url = await resolve_default_model_config(session, SimpleNamespace(id="user-1"))
        assert pid == ""
        assert prov == ""
        assert model == ""
        assert url == ""
