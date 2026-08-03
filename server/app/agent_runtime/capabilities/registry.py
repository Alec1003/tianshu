from __future__ import annotations

from typing import Any

from app.agent_runtime.capabilities.adapters import (
    DriverCapabilityAdapter,
    SkillCapabilityAdapter,
)
from app.agent_runtime.capabilities.models import Capability
from app.agent_runtime.tools.base import ToolContext


class CapabilityRegistry:
    """Workspace-scoped unified discovery and execution layer."""

    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = {}
        self._adapters: dict[str, Any] = {}
        self._discovered = False

    def register(self, capability: Capability, adapter: Any | None = None) -> None:
        if capability.name in self._capabilities:
            raise ValueError(f"Capability already registered: {capability.name}")
        self._capabilities[capability.name] = capability
        if adapter is not None:
            self._adapters[capability.name] = adapter

    def get(self, name: str) -> Capability:
        try:
            return self._capabilities[name]
        except KeyError as exc:
            raise ValueError(f"Capability not registered: {name}") from exc

    def capabilities(self) -> list[Capability]:
        return list(self._capabilities.values())

    def schemas(self) -> list[dict[str, Any]]:
        return [capability.schema() for capability in self.capabilities()]

    async def discover(self) -> list[Capability]:
        return self.capabilities()

    def discover_sync(self) -> list[Capability]:
        """Synchronous discovery for ToolRegistry initialization."""
        return self.capabilities()

    async def load_from_workspace(self, workspace: Any) -> None:
        if self._discovered:
            return
        skill_registry = getattr(workspace, "skill_registry", None)
        if skill_registry is not None:
            await self._load_adapter(SkillCapabilityAdapter(skill_registry))
        driver_registry = getattr(workspace, "driver_registry", None)
        if driver_registry is not None:
            await self._load_adapter(DriverCapabilityAdapter(driver_registry))
        self._discovered = True

    async def _load_adapter(self, adapter: Any) -> None:
        for capability in await adapter.discover():
            if capability.name not in self._capabilities:
                self.register(capability, adapter)

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        capability = self.get(name)
        adapter = self._adapters.get(name)
        if adapter is None:
            raise ValueError(f"No adapter registered for capability: {name}")
        return await adapter.execute(capability, arguments, context)

    @classmethod
    def from_workspace(cls, workspace: Any) -> "CapabilityRegistry":
        existing = getattr(workspace, "capability_registry", None)
        if isinstance(existing, cls):
            return existing
        registry = cls()
        setattr(workspace, "capability_registry", registry)
        return registry


__all__ = ["CapabilityRegistry"]
