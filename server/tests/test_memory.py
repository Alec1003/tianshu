from __future__ import annotations

import pytest

from app.agent_runtime.memory import MemoryBackend, MemoryManager, MemoryRetriever
from app.agent_runtime.memory.manager import MemoryWriteDeniedError
from app.agent_runtime.memory.models import MemoryItem


class InMemoryBackend(MemoryBackend):
    def __init__(self) -> None:
        self.items: list[MemoryItem] = []

    def list_items(self) -> list[MemoryItem]:
        return list(self.items)

    def save_items(self, items: list[MemoryItem]) -> None:
        self.items = list(items)


def test_memory_requires_confirmed_or_system_marked_write():
    manager = MemoryManager(storage=InMemoryBackend())

    with pytest.raises(MemoryWriteDeniedError):
        manager.store(content="unsafe", workspace_id="w-1")


def test_memory_supports_global_workspace_and_scenario_retrieval():
    backend = InMemoryBackend()
    manager = MemoryManager(storage=backend)
    manager.store(
        content="global doctrine",
        workspace_id="global",
        memory_type="global",
        system_marked=True,
    )
    manager.store(
        content="workspace note",
        workspace_id="w-1",
        memory_type="workspace",
        confirmed=True,
    )
    manager.store(
        content="scenario note",
        workspace_id="w-1",
        scenario_id="s-1",
        memory_type="scenario",
        confirmed=True,
    )
    manager.store(
        content="other scenario",
        workspace_id="w-1",
        scenario_id="s-2",
        memory_type="scenario",
        confirmed=True,
    )

    memories = manager.retrieve(workspace_id="w-1", scenario_id="s-1")

    contents = {memory.content for memory in memories}
    assert {"global doctrine", "workspace note", "scenario note"} <= contents
    assert "other scenario" not in contents


def test_memory_retriever_protocol_is_exported():
    assert MemoryRetriever is not None
