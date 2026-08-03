from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.agent_runtime.memory.lifecycle import can_activate, initial_status, is_active
from app.agent_runtime.memory.models import MemoryItem, MemoryStatus, MemoryType, utc_now
from app.agent_runtime.memory.retrieval.base import MemoryRetrievalResult, MemoryRetriever
from app.agent_runtime.memory.retrieval.keyword import KeywordRetriever
from app.agent_runtime.memory.base import MemoryBackend
from app.agent_runtime.memory.storage import JsonMemoryStorage


class MemoryWriteDeniedError(PermissionError):
    """Raised when an unsafe automatic memory write is attempted."""


class MemoryManager:
    """Framework-neutral manager for global/workspace/scenario memory."""

    def __init__(
        self,
        storage: MemoryBackend | None = None,
        retriever: MemoryRetriever | None = None,
    ) -> None:
        self.storage = storage or JsonMemoryStorage()
        self.retriever = retriever or KeywordRetriever()

    def store(
        self,
        *,
        content: str,
        workspace_id: str,
        scenario_id: str = "",
        memory_type: MemoryType = "workspace",
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
        confidence: float = 1.0,
        source: str = "user",
        status: MemoryStatus | None = None,
        tags: list[str] | None = None,
        expires_at: str | None = None,
        confirmed: bool = False,
        system_marked: bool = False,
    ) -> MemoryItem:
        desired_status = status or initial_status(
            confirmed=confirmed,
            system_marked=system_marked,
        )
        if status is None and desired_status == "candidate":
            raise MemoryWriteDeniedError(
                "Long-term memory writes require user confirmation or an explicit system marker."
            )
        if desired_status in {"confirmed", "active"} and not can_activate(
            confirmed=confirmed,
            system_marked=system_marked,
        ):
            raise MemoryWriteDeniedError(
                "Long-term memory writes require user confirmation or an explicit system marker."
            )
        item = MemoryItem.create(
            workspace_id=workspace_id,
            scenario_id=scenario_id,
            memory_type=memory_type,
            content=content,
            metadata=metadata,
            importance=importance,
            confidence=confidence,
            source=source,  # type: ignore[arg-type]
            status=desired_status,
            tags=tags,
            expires_at=expires_at,
        )
        items = self.storage.list_items()
        items.append(item)
        self.storage.save_items(items)
        return item

    def retrieve(
        self,
        *,
        workspace_id: str,
        scenario_id: str = "",
        include_global: bool = True,
        query: str = "",
        limit: int | None = None,
        include_inactive: bool = False,
        update_access: bool = True,
    ) -> list[MemoryItem]:
        visible = [
            item
            for item in self.storage.list_items()
            if self._visible_to(
                item,
                workspace_id=workspace_id,
                scenario_id=scenario_id,
                include_global=include_global,
            )
            and (include_inactive or is_active(item))
        ]
        ranked = self.rank(
            query,
            visible,
            limit=limit or len(visible),
        )
        items = [result.item for result in ranked]
        if update_access and items:
            self._touch([item.id for item in items])
        return items

    def search(
        self,
        query: str,
        *,
        workspace_id: str,
        scenario_id: str = "",
        include_global: bool = True,
        limit: int = 10,
    ) -> list[MemoryItem]:
        return self.retrieve(
            workspace_id=workspace_id,
            scenario_id=scenario_id,
            include_global=include_global,
            query=query,
            limit=limit,
        )

    def rank(
        self,
        query: str,
        items: list[MemoryItem],
        *,
        limit: int = 10,
    ) -> list[MemoryRetrievalResult]:
        if query.strip():
            results = self.retriever.retrieve(query, items, limit=max(limit, 1))
        else:
            results = [
                MemoryRetrievalResult(item=item, relevance=0.0)
                for item in items
            ]
        return sorted(
            results,
            key=lambda result: (
                result.item.importance,
                result.item.confidence,
                result.relevance,
                result.item.updated_at,
            ),
            reverse=True,
        )[:limit]

    def update(
        self,
        memory_id: str,
        *,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
        importance: float | None = None,
        confidence: float | None = None,
        status: MemoryStatus | None = None,
        tags: list[str] | None = None,
        expires_at: str | None = None,
        confirmed: bool = False,
        system_marked: bool = False,
    ) -> MemoryItem:
        if status in {"confirmed", "active"} and not can_activate(
            confirmed=confirmed,
            system_marked=system_marked,
        ):
            raise MemoryWriteDeniedError(
                "Long-term memory updates require user confirmation or an explicit system marker."
            )
        items = self.storage.list_items()
        for index, item in enumerate(items):
            if item.id == memory_id:
                updated = replace(
                    item,
                    content=item.content if content is None else content,
                    metadata=item.metadata if metadata is None else metadata,
                    importance=item.importance if importance is None else max(0.0, min(1.0, importance)),
                    confidence=item.confidence if confidence is None else max(0.0, min(1.0, confidence)),
                    status=item.status if status is None else status,
                    tags=item.tags if tags is None else tags,
                    expires_at=item.expires_at if expires_at is None else expires_at,
                    updated_at=utc_now(),
                )
                items[index] = updated
                self.storage.save_items(items)
                return updated
        raise ValueError(f"Memory item not found: {memory_id}")

    def delete(self, memory_id: str) -> bool:
        items = self.storage.list_items()
        remaining = [item for item in items if item.id != memory_id]
        if len(remaining) == len(items):
            return False
        self.storage.save_items(remaining)
        return True

    def retrieve_for_agent(
        self,
        *,
        workspace_id: str,
        scenario_id: str = "",
        agent_name: str = "default",
        query: str = "",
        limit: int = 12,
    ) -> list[MemoryItem]:
        """Retrieve memories scoped to a specific agent."""
        items = self.retrieve(
            workspace_id=workspace_id,
            scenario_id=scenario_id,
            query=query,
            limit=limit,
        )
        if not agent_name:
            return items
        return [
            item for item in items
            if (item.metadata or {}).get("agent_name") in (agent_name, None, "")
        ]

    def store_interaction(
        self,
        *,
        workspace_id: str,
        scenario_id: str = "",
        agent_name: str = "default",
        user_query: str,
        agent_response: str,
        importance: float = 0.3,
    ) -> MemoryItem:
        """Store a user-agent interaction as workspace memory."""
        content = "User: " + user_query[:500] + " | Agent: " + agent_response[:500]
        return self.store(
            content=content,
            workspace_id=workspace_id,
            scenario_id=scenario_id,
            memory_type="workspace",
            metadata={"agent_name": agent_name},
            importance=importance,
            source="agent",
            confirmed=True,
            system_marked=True,
        )

    @staticmethod
    def _visible_to(
        item: MemoryItem,
        *,
        workspace_id: str,
        scenario_id: str,
        include_global: bool,
    ) -> bool:
        if item.memory_type == "global":
            return include_global
        if item.memory_type == "workspace":
            return item.workspace_id == workspace_id
        if item.memory_type == "scenario":
            return item.workspace_id == workspace_id and item.scenario_id == scenario_id
        return False

    def _touch(self, memory_ids: list[str]) -> None:
        ids = set(memory_ids)
        items = self.storage.list_items()
        changed = False
        for index, item in enumerate(items):
            if item.id in ids:
                items[index] = replace(
                    item,
                    access_count=item.access_count + 1,
                    last_accessed=utc_now(),
                )
                changed = True
        if changed:
            self.storage.save_items(items)
