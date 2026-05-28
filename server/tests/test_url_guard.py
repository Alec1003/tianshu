import pytest

from app.ai.pydantic_agent import resolve_model
from app.security.url_guard import UnsafeBaseUrlError, normalize_and_validate_base_url


def test_url_guard_blocks_private_networks_for_generic_providers():
    with pytest.raises(UnsafeBaseUrlError):
        normalize_and_validate_base_url("http://127.0.0.1:8000/v1")

    with pytest.raises(UnsafeBaseUrlError):
        normalize_and_validate_base_url("http://169.254.169.254/latest/meta-data")


def test_url_guard_allows_private_networks_only_when_explicitly_requested():
    assert (
        normalize_and_validate_base_url(
            "http://localhost:11434/v1",
            allow_private_network=True,
        )
        == "http://localhost:11434/v1"
    )


def test_url_guard_allows_known_public_provider_hosts():
    assert (
        normalize_and_validate_base_url("https://api.openai.com/v1")
        == "https://api.openai.com/v1"
    )


def test_agent_model_override_blocks_private_base_url():
    with pytest.raises(UnsafeBaseUrlError):
        resolve_model("openai:gpt-4o-mini", "sk-test", "http://127.0.0.1:8000/v1")


def test_agent_model_override_allows_local_ollama():
    model = resolve_model("ollama:llama3.1", "", "http://localhost:11434/v1")

    assert model is not None
