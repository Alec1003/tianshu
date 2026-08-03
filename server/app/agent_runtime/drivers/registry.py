from __future__ import annotations

from typing import Any

from app.agent_runtime.drivers.base import DriverBase
from app.agent_runtime.drivers.models import Capability


class DriverRegistry:
    """Workspace-scoped registry for external capability drivers."""

    def __init__(self) -> None:
        self._drivers: dict[str, DriverBase] = {}
        self._initialized = False

    def register(self, driver: DriverBase) -> None:
        if driver.name in self._drivers:
            raise ValueError(f"Driver already registered: {driver.name}")
        self._drivers[driver.name] = driver

    def get(self, name: str) -> DriverBase:
        try:
            return self._drivers[name]
        except KeyError as exc:
            raise ValueError(f"Driver not registered: {name}") from exc

    def drivers(self) -> list[DriverBase]:
        return list(self._drivers.values())

    async def initialize(self) -> None:
        if self._initialized:
            return
        for driver in self.drivers():
            await driver.initialize()
        self._initialized = True

    async def capabilities(self) -> list[Capability]:
        await self.initialize()
        items: list[Capability] = []
        for driver in self.drivers():
            items.extend(await driver.capabilities())
        return items

    async def execute(
        self,
        driver_name: str,
        capability: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        await self.initialize()
        return await self.get(driver_name).execute(capability, arguments or {})

    async def close(self) -> None:
        for driver in self.drivers():
            await driver.close()
        self._initialized = False

    @classmethod
    def from_workspace(cls, workspace: Any) -> "DriverRegistry":
        existing = getattr(workspace, "driver_registry", None)
        if isinstance(existing, cls):
            return existing

        from app.agent_runtime.drivers.mcp_driver import MCPDriver

        registry = cls()
        mcp_client = getattr(workspace, "mcp_client", None)
        if mcp_client is not None:
            registry.register(MCPDriver(client=mcp_client))
        setattr(workspace, "driver_registry", registry)
        return registry
