from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent_runtime.drivers.models import Capability
from app.agent_runtime.drivers.registry import DriverRegistry


class FakeDriver:
    name = "fake"

    def __init__(self) -> None:
        self.initialized = 0
        self.closed = 0
        self.executed = []

    async def initialize(self) -> None:
        self.initialized += 1

    async def capabilities(self):
        return [
            Capability(
                name="fake_read",
                description="Read",
                input_schema={"type": "object", "properties": {}},
                provider=self.name,
                permission="read",
            )
        ]

    async def execute(self, capability: str, arguments: dict | None = None):
        self.executed.append((capability, arguments or {}))
        return {"ok": True, "capability": capability}

    async def close(self) -> None:
        self.closed += 1


def test_driver_registry_can_register_driver():
    registry = DriverRegistry()
    driver = FakeDriver()

    registry.register(driver)

    assert registry.get("fake") is driver


@pytest.mark.asyncio
async def test_driver_registry_discovers_and_executes_capabilities():
    registry = DriverRegistry()
    driver = FakeDriver()
    registry.register(driver)

    capabilities = await registry.capabilities()
    result = await registry.execute("fake", "fake_read", {"q": "x"})

    assert capabilities[0].name == "fake_read"
    assert result == {"ok": True, "capability": "fake_read"}
    assert driver.initialized == 1
    assert driver.executed == [("fake_read", {"q": "x"})]


def test_workspace_shares_driver_registry_instance():
    workspace = SimpleNamespace(mcp_client=None)

    first = DriverRegistry.from_workspace(workspace)
    second = DriverRegistry.from_workspace(workspace)

    assert first is second


@pytest.mark.asyncio
async def test_close_workspace_releases_drivers():
    registry = DriverRegistry()
    driver = FakeDriver()
    registry.register(driver)

    await registry.initialize()
    await registry.close()

    assert driver.closed == 1
