from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agent_runtime.agents.profile import AgentProfile
from app.config import get_settings


_OPENAI_COMPAT_DEFAULT_BASE_URL: dict[str, str] = {
    "deepseek": "https://api.deepseek.com/v1",
    "glm": "https://open.bigmodel.cn/api/paas/v4",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "minimax": "https://api.minimax.chat/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": "http://localhost:11434/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai",
}
_NO_API_KEY_PROVIDERS = {"ollama", "custom"}


@dataclass(frozen=True)
class AgentModelConfig:
    provider: str
    model: str
    api_key: str = ""
    base_url: str = ""

    @property
    def is_configured(self) -> bool:
        if not self.provider or not self.model:
            return False
        if self.provider == "custom":
            return bool(self.effective_base_url)
        return bool(self.api_key or self.provider in _NO_API_KEY_PROVIDERS)

    @property
    def effective_base_url(self) -> str:
        return self.base_url or _OPENAI_COMPAT_DEFAULT_BASE_URL.get(self.provider, "")


class NoAgentModelConfiguredError(RuntimeError):
    """Raised when neither request nor environment contains a usable model."""


class ModelFactory:
    """Resolve per-request or environment model configuration."""

    def resolve(self, request: Any, profile: AgentProfile | None = None) -> AgentModelConfig:
        override = getattr(request, "model", None) or {}
        if isinstance(override, dict):
            provider = str(override.get("provider") or "").strip().lower()
            model = str(override.get("model") or "").strip()
            api_key = str(override.get("apiKey") or override.get("api_key") or "").strip()
            base_url = str(override.get("baseUrl") or override.get("base_url") or "").strip()
            if provider and model and (
                api_key or provider == "ollama" or (provider == "custom" and base_url)
            ):
                return AgentModelConfig(provider, model, api_key, base_url)

        if profile is not None and profile.model_config is not None:
            if isinstance(profile.model_config, AgentModelConfig):
                return profile.model_config
            if isinstance(profile.model_config, dict):
                provider = str(profile.model_config.get("provider") or "").strip().lower()
                model = str(profile.model_config.get("model") or "").strip()
                api_key = str(
                    profile.model_config.get("apiKey")
                    or profile.model_config.get("api_key")
                    or ""
                ).strip()
                base_url = str(
                    profile.model_config.get("baseUrl")
                    or profile.model_config.get("base_url")
                    or ""
                ).strip()
                if provider and model:
                    return AgentModelConfig(provider, model, api_key, base_url)

        settings = get_settings()
        provider, _, model = settings.llm_model.partition(":")
        return AgentModelConfig(
            provider=provider.strip().lower(),
            model=(model or settings.llm_model).strip(),
            api_key=settings.llm_api_key.strip(),
            base_url=settings.llm_base_url.strip(),
        )


__all__ = ["AgentModelConfig", "ModelFactory", "NoAgentModelConfiguredError"]
