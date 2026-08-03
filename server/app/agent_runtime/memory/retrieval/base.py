from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.agent_runtime.memory.models import MemoryItem


@dataclass(frozen=True)
class MemoryRetrievalResult:
    item: MemoryItem
    relevance: float = 0.0


class MemoryRetriever(Protocol):
    def retrieve(
        self,
        query: str,
        items: list[MemoryItem],
        *,
        limit: int = 10,
    ) -> list[MemoryRetrievalResult]:
        """Return ranked retrieval results."""
