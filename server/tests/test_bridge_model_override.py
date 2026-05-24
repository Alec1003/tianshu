"""Regression：``AICCOpenClawBridge._resolve_agent_for_request``。

行为契约：
  1. ``context["model"]`` 包含 provider + model + apiKey 时，调用
     ``build_agent`` 构造 per-request agent 并返回。
  2. 缺关键字段（apiKey 空 / model 空 / context 空）时，返回
     ``self.pydantic_agent`` 作为兜底。
  3. ``build_agent`` 抛异常时，吞掉错误日志，返回
     ``self.pydantic_agent`` 兜底，绝不让用户请求整个失败。

不实例化真实 ``AICCOpenClawBridge``（避免拉 blade/gymnasium）；用
``types.SimpleNamespace`` 模拟出 ``pydantic_agent`` 属性，把
``_resolve_agent_for_request`` 当作 unbound 方法直接调用。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.ai import bridge as bridge_mod
from app.ai import pydantic_agent as pa_mod
from app.ai.bridge import AICCOpenClawBridge


SENTINEL_ENV_AGENT = object()
SENTINEL_PER_REQUEST_AGENT = object()


def _fake_self(env_agent: Any) -> SimpleNamespace:
    """A stand-in for ``self`` exposing just ``pydantic_agent``."""
    return SimpleNamespace(pydantic_agent=env_agent)


def _resolve(self_like: SimpleNamespace, context: dict[str, Any] | None) -> Any:
    return AICCOpenClawBridge._resolve_agent_for_request(self_like, context)


@pytest.fixture(autouse=True)
def _stub_build_agent(monkeypatch: pytest.MonkeyPatch):
    """Default: ``build_agent`` returns a distinguishable sentinel object."""
    calls: list[dict[str, Any]] = []

    def fake_build_agent(
        model_id: str, api_key: str = "", base_url: str = ""
    ) -> Any:
        calls.append({"model_id": model_id, "api_key": api_key, "base_url": base_url})
        return SENTINEL_PER_REQUEST_AGENT

    monkeypatch.setattr(pa_mod, "build_agent", fake_build_agent)
    return calls


def test_per_request_agent_built_when_model_apiKey_present(_stub_build_agent):
    self_like = _fake_self(SENTINEL_ENV_AGENT)
    ctx = {
        "model": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "apiKey": "sk-from-user",
            "baseUrl": "https://api.openai.com/v1",
        }
    }

    result = _resolve(self_like, ctx)

    assert result is SENTINEL_PER_REQUEST_AGENT
    assert _stub_build_agent == [
        {
            "model_id": "openai:gpt-4o-mini",
            "api_key": "sk-from-user",
            "base_url": "https://api.openai.com/v1",
        }
    ]


def test_fallback_to_env_agent_when_apiKey_missing(_stub_build_agent):
    self_like = _fake_self(SENTINEL_ENV_AGENT)
    ctx = {
        "model": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "apiKey": "",
            "baseUrl": "",
        }
    }

    result = _resolve(self_like, ctx)

    assert result is SENTINEL_ENV_AGENT
    assert _stub_build_agent == [], "must not call build_agent when apiKey empty"


def test_keyless_ollama_model_override_is_built(_stub_build_agent):
    self_like = _fake_self(SENTINEL_ENV_AGENT)
    ctx = {
        "model": {
            "provider": "ollama",
            "model": "llama3.1",
            "apiKey": "",
            "baseUrl": "http://localhost:11434/v1",
        }
    }

    result = _resolve(self_like, ctx)

    assert result is SENTINEL_PER_REQUEST_AGENT
    assert _stub_build_agent == [
        {
            "model_id": "ollama:llama3.1",
            "api_key": "",
            "base_url": "http://localhost:11434/v1",
        }
    ]


def test_keyless_custom_model_requires_base_url(_stub_build_agent):
    self_like = _fake_self(SENTINEL_ENV_AGENT)

    assert (
        _resolve(
            self_like,
            {
                "model": {
                    "provider": "custom",
                    "model": "local-model",
                    "apiKey": "",
                    "baseUrl": "",
                }
            },
        )
        is SENTINEL_ENV_AGENT
    )

    result = _resolve(
        self_like,
        {
            "model": {
                "provider": "custom",
                "model": "local-model",
                "apiKey": "",
                "baseUrl": "http://127.0.0.1:8001/v1",
            }
        },
    )

    assert result is SENTINEL_PER_REQUEST_AGENT
    assert _stub_build_agent == [
        {
            "model_id": "custom:local-model",
            "api_key": "",
            "base_url": "http://127.0.0.1:8001/v1",
        }
    ]


def test_fallback_to_env_agent_when_model_missing(_stub_build_agent):
    self_like = _fake_self(SENTINEL_ENV_AGENT)
    ctx = {
        "model": {
            "provider": "openai",
            "model": "",
            "apiKey": "sk-from-user",
        }
    }

    result = _resolve(self_like, ctx)

    assert result is SENTINEL_ENV_AGENT
    assert _stub_build_agent == []


def test_fallback_to_env_agent_when_context_empty(_stub_build_agent):
    self_like = _fake_self(SENTINEL_ENV_AGENT)

    assert _resolve(self_like, None) is SENTINEL_ENV_AGENT
    assert _resolve(self_like, {}) is SENTINEL_ENV_AGENT
    assert _resolve(self_like, {"model": None}) is SENTINEL_ENV_AGENT
    # non-dict model field is ignored, not crashed:
    assert _resolve(self_like, {"model": "not-a-dict"}) is SENTINEL_ENV_AGENT
    assert _stub_build_agent == []


def test_fallback_to_env_agent_when_build_raises(monkeypatch: pytest.MonkeyPatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("simulated provider misconfig")

    monkeypatch.setattr(pa_mod, "build_agent", boom)

    self_like = _fake_self(SENTINEL_ENV_AGENT)
    ctx = {
        "model": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "apiKey": "sk-from-user",
        }
    }

    # No exception leaks; fall back to the global env agent.
    assert _resolve(self_like, ctx) is SENTINEL_ENV_AGENT


def test_returns_none_when_no_agent_and_no_override(_stub_build_agent):
    """No env agent AND no usable model config → caller falls back to regex."""
    self_like = _fake_self(None)
    assert _resolve(self_like, None) is None
    assert _resolve(self_like, {"model": {"provider": "openai"}}) is None


def test_whitespace_in_model_fields_is_trimmed(_stub_build_agent):
    self_like = _fake_self(SENTINEL_ENV_AGENT)
    ctx = {
        "model": {
            "provider": "  anthropic  ",
            "model": " claude-3-5-sonnet ",
            "apiKey": "  sk-x  ",
            "baseUrl": "   ",
        }
    }

    result = _resolve(self_like, ctx)

    assert result is SENTINEL_PER_REQUEST_AGENT
    assert _stub_build_agent[0]["model_id"] == "anthropic:claude-3-5-sonnet"
    assert _stub_build_agent[0]["api_key"] == "sk-x"
    # whitespace-only baseUrl is treated as empty
    assert _stub_build_agent[0]["base_url"] == ""


# ─── resolve_model 扩展 provider 覆盖 (pure unit) ─────────────────────────────


def test_resolve_model_openai_compat_default_base_url():
    """deepseek 等 OpenAI-compatible provider 在未指定 base_url 时用默认端点。"""
    model = pa_mod.resolve_model("deepseek:deepseek-chat", api_key="sk", base_url="")
    # 应当是 OpenAIModel 实例（具体类型断言用 type-name 而非 isinstance，避免
    # 引入额外 import 路径不稳定）。
    assert type(model).__name__ == "OpenAIModel"


def test_resolve_model_openai_responses_provider():
    model = pa_mod.resolve_model(
        "openai-responses:gpt-5-mini",
        api_key="sk",
        base_url="https://api.openai.com/v1",
    )

    assert type(model).__name__ == "OpenAIResponsesModel"


def test_resolve_model_custom_without_base_url_falls_back_to_string():
    """custom + 空 base_url 无法用 → 返回原 string 让上层降级。"""
    out = pa_mod.resolve_model("custom:foo", api_key="sk", base_url="")
    assert out == "custom:foo"


def test_resolve_model_empty_returns_none():
    assert pa_mod.resolve_model("", "", "") is None
