from __future__ import annotations

from app.ai import model_checker, model_endpoint_policy as endpoint_policy
from app.ai.model_checker import _ProbeResult, check_model_connectivity
from app.ai.models import ModelCheckRequest
from app.config import Settings


def test_model_checker_blocks_custom_private_base_url_when_disabled(monkeypatch):
    monkeypatch.setattr(
        endpoint_policy,
        "get_settings",
        lambda: Settings(env="production", allow_private_model_base_urls=False),
    )

    result = check_model_connectivity(
        ModelCheckRequest(
            provider="custom",
            baseUrl="http://127.0.0.1:8000/v1",
            apiKey="sk-test",
            model="local-model",
        )
    )

    assert result.status == "error"
    assert result.message.startswith("Base URL blocked:")


def test_model_checker_allows_custom_private_base_url_when_enabled(monkeypatch):
    monkeypatch.setattr(
        endpoint_policy,
        "get_settings",
        lambda: Settings(env="production", allow_private_model_base_urls=True),
    )
    captured = {}

    def fake_probe(endpoint: str, api_key: str, *, allow_private_network: bool):
        captured["endpoint"] = endpoint
        captured["api_key"] = api_key
        captured["allow_private_network"] = allow_private_network
        return _ProbeResult(
            endpoint=endpoint,
            http_status=200,
            payload={"data": [{"id": "local-model"}]},
            error_message=None,
            reachable=True,
        )

    monkeypatch.setattr(model_checker, "_probe_models_endpoint", fake_probe)

    result = check_model_connectivity(
        ModelCheckRequest(
            provider="custom",
            baseUrl="http://127.0.0.1:8000/v1",
            apiKey="sk-test",
            model="local-model",
        )
    )

    assert result.status == "ok"
    assert result.checked_model_exists is True
    assert captured == {
        "endpoint": "http://127.0.0.1:8000/v1/models",
        "api_key": "sk-test",
        "allow_private_network": True,
    }
