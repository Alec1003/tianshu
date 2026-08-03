from __future__ import annotations

import re

from app.agent_runtime.memory.models import MemoryItem
from app.agent_runtime.memory.retrieval.base import MemoryRetrievalResult


class KeywordRetriever:
    """Simple lexical retriever used until embeddings are configured."""

    def retrieve(
        self,
        query: str,
        items: list[MemoryItem],
        *,
        limit: int = 10,
    ) -> list[MemoryRetrievalResult]:
        terms = _terms(query)
        results: list[MemoryRetrievalResult] = []
        for item in items:
            relevance = self._score(terms, item)
            if terms and relevance <= 0:
                continue
            results.append(MemoryRetrievalResult(item=item, relevance=relevance))
        return sorted(
            results,
            key=lambda result: (
                result.relevance,
                result.item.importance,
                result.item.confidence,
                result.item.updated_at,
            ),
            reverse=True,
        )[:limit]

    @staticmethod
    def _score(terms: list[str], item: MemoryItem) -> float:
        if not terms:
            return 0.0
        haystack = " ".join(
            [
                item.content,
                " ".join(item.tags),
                " ".join(str(value) for value in item.metadata.values()),
            ]
        ).lower()
        matches = sum(1 for term in terms if term in haystack)
        return matches / max(1, len(terms))


def _terms(query: str) -> list[str]:
    return [term for term in re.split(r"\W+", query.lower()) if term]
