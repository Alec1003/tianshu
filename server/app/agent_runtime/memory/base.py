from __future__ import annotations

from typing import Protocol

from app.agent_runtime.memory.models import MemoryItem, MemoryType


class MemoryBackend(Protocol):
    def list_items(self) -> list[MemoryItem]:
        """Return all stored memory items."""

    def save_items(self, items: list[MemoryItem]) -> None:
        """Persist all memory items."""


class MemoryManagerProtocol(Protocol):
    def store(
        self,
        *,
        content: str,
        workspace_id: str,
        scenario_id: str = "",
        memory_type: MemoryType = "workspace",
        confirmed: bool = False,
        system_marked: bool = False,
    ) -> MemoryItem:
        """Store a long-term memory item."""


MemoryStore = MemoryBackend


__all__ = ["MemoryBackend", "MemoryManagerProtocol", "MemoryStore"]
