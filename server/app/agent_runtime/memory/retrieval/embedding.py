from __future__ import annotations

from app.agent_runtime.memory.models import MemoryItem
from app.agent_runtime.memory.retrieval.base import MemoryRetrievalResult


class EmbeddingRetriever:
    """Placeholder interface for future semantic retrieval backends."""

    def retrieve(
        self,
        query: str,
        items: list[MemoryItem],
        *,
        limit: int = 10,
    ) -> list[MemoryRetrievalResult]:
        raise NotImplementedError("Embedding retrieval is not configured in Phase 5.5.")
