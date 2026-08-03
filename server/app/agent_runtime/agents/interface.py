from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any

from app.agent_runtime.events import AgentEvent


class BaseAgent(ABC):
    """Common Agent interface reserved for future multi-agent implementations."""

    @abstractmethod
    async def initialize(self) -> None:
        """Prepare the agent instance before execution."""

    @abstractmethod
    async def run(self, messages: list[dict[str, Any]]) -> AsyncGenerator[AgentEvent, None]:
        """Run the agent for one turn."""

    @abstractmethod
    async def close(self) -> None:
        """Release resources held by the agent instance."""


__all__ = ["BaseAgent"]
