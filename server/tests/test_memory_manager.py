from __future__ import annotations

import pytest

from app.agent_runtime.memory.manager import MemoryManager, MemoryWriteDeniedError
from app.agent_runtime.memory.storage import JsonMemoryStorage


def _manager(tmp_path):
    return MemoryManager(JsonMemoryStorage(tmp_path / "memory.json"))


def test_memory_store_requires_confirmation(tmp_path):
    manager = _manager(tmp_path)

    with pytest.raises(MemoryWriteDeniedError):
        manager.store(
            content="unconfirmed plan",
            workspace_id="workspace-a",
            memory_type="workspace",
        )


def test_memory_store_and_retrieve_workspace_memory(tmp_path):
    manager = _manager(tmp_path)

    item = manager.store(
        content="Use conservative fuel margins.",
        workspace_id="workspace-a",
        memory_type="workspace",
        confirmed=True,
    )

    retrieved = manager.retrieve(workspace_id="workspace-a")
    assert retrieved == [item]


def test_workspace_memory_is_isolated(tmp_path):
    manager = _manager(tmp_path)
    manager.store(
        content="workspace a",
        workspace_id="workspace-a",
        memory_type="workspace",
        confirmed=True,
    )

    assert manager.retrieve(workspace_id="workspace-b") == []


def test_scenario_memory_is_isolated(tmp_path):
    manager = _manager(tmp_path)
    manager.store(
        content="scenario alpha note",
        workspace_id="workspace-a",
        scenario_id="alpha",
        memory_type="scenario",
        confirmed=True,
    )

    assert manager.retrieve(workspace_id="workspace-a", scenario_id="alpha")
    assert manager.retrieve(workspace_id="workspace-a", scenario_id="bravo") == []


def test_global_memory_is_shared(tmp_path):
    manager = _manager(tmp_path)
    manager.store(
        content="Global doctrine note",
        workspace_id="workspace-a",
        memory_type="global",
        system_marked=True,
    )

    assert manager.retrieve(workspace_id="workspace-b")[0].content == "Global doctrine note"


def test_memory_search_update_and_delete(tmp_path):
    manager = _manager(tmp_path)
    item = manager.store(
        content="Searchable tanker note",
        workspace_id="workspace-a",
        memory_type="workspace",
        confirmed=True,
    )

    assert manager.search("tanker", workspace_id="workspace-a") == [item]
    updated = manager.update(
        item.id,
        content="Updated tanker note",
        confirmed=True,
    )
    assert updated.content == "Updated tanker note"
    assert manager.delete(item.id) is True
    assert manager.retrieve(workspace_id="workspace-a") == []
