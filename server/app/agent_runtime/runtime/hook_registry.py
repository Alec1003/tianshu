from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.agent_runtime.runtime.hooks import HookContext, maybe_await
from app.agent_runtime.runtime.phases import Phase


_AFTER_PHASES = {
    Phase.POST_DISPATCH,
    Phase.POST_AGENT_BUILD,
    Phase.POST_RESPONSE,
    Phase.FINALLY,
}


class HookRegistry:
    """Registry and dispatcher for runtime lifecycle hooks."""

    def __init__(self) -> None:
        self._hooks: dict[Phase, list[Any]] = defaultdict(list)

    def register(self, phase: Phase, hook: Any) -> None:
        if hook not in self._hooks[phase]:
            self._hooks[phase].append(hook)

    def unregister(self, phase: Phase, hook: Any) -> None:
        if hook in self._hooks.get(phase, []):
            self._hooks[phase].remove(hook)

    def hooks_for(self, phase: Phase) -> list[Any]:
        return list(self._hooks.get(phase, []))

    async def execute(self, phase: Phase, context: HookContext) -> None:
        context.phase = phase
        for hook in self.hooks_for(phase):
            if phase == Phase.ON_ERROR:
                callback = getattr(hook, "on_error", None)
            elif phase in _AFTER_PHASES:
                callback = getattr(hook, "after", None)
            else:
                callback = getattr(hook, "before", None)
            if callback is not None:
                await maybe_await(callback(context))


__all__ = ["HookRegistry"]
