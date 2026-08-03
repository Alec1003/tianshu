from __future__ import annotations

from typing import Any, Protocol

from app.agent_runtime.drivers.models import Capability


class DriverBase(Protocol):
    name: str

    async def initialize(self) -> None:
        """Prepare the driver for discovery or execution."""

    async def capabilities(self) -> list[Capability]:
        """Return capabilities currently exposed by the driver."""

    async def execute(
        self,
        capability: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a capability and return a JSON-serializable result."""

    async def close(self) -> None:
        """Release driver resources."""
