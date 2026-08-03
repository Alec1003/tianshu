from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.agent_runtime.runtime.phases import Phase


@dataclass
class HookContext:
    """Per-request lifecycle context shared with runtime hooks."""

    request: Any
    phase: Phase | None = None
    agent: Any | None = None
    error: BaseException | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeHook(Protocol):
    """Lifecycle hook contract.

    Hooks are intentionally runtime-neutral. They do not know about FastAPI,
    tools, memory, or concrete agent implementations.
    """

    async def before(self, context: HookContext) -> None:
        """Run before the phase's fixed runtime work."""

    async def after(self, context: HookContext) -> None:
        """Run after the phase's fixed runtime work."""

    async def on_error(self, context: HookContext) -> None:
        """Run when the runtime enters ON_ERROR."""


class BaseRuntimeHook:
    """No-op base hook for tests and future runtime extensions."""

    async def before(self, context: HookContext) -> None:
        return None

    async def after(self, context: HookContext) -> None:
        return None

    async def on_error(self, context: HookContext) -> None:
        return None


async def maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = ["BaseRuntimeHook", "HookContext", "RuntimeHook", "maybe_await"]
