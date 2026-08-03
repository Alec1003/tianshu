from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.agent_runtime.memory.lifecycle import initial_status, is_active, is_expired
from app.agent_runtime.memory.manager import MemoryManager, MemoryWriteDeniedError
from app.agent_runtime.memory.models import MemoryItem
from app.agent_runtime.memory.storage import JsonMemoryStorage


def _manager(tmp_path):
    return MemoryManager(JsonMemoryStorage(tmp_path / "memory.json"))


def test_lifecycle_initial_status_rules():
    assert initial_status(confirmed=False, system_marked=False) == "candidate"
    assert initial_status(confirmed=True, system_marked=False) == "active"
    assert initial_status(confirmed=False, system_marked=True) == "active"


def test_candidate_memory_can_be_stored_but_not_retrieved_by_default(tmp_path):
    manager = _manager(tmp_path)
    item = manager.store(
        content="candidate",
        workspace_id="w",
        memory_type="workspace",
        status="candidate",
    )

    assert item.status == "candidate"
    assert manager.retrieve(workspace_id="w") == []
    assert manager.retrieve(workspace_id="w", include_inactive=True)[0].content == "candidate"


def test_active_status_requires_confirmation(tmp_path):
    manager = _manager(tmp_path)

    with pytest.raises(MemoryWriteDeniedError):
        manager.store(
            content="unsafe active",
            workspace_id="w",
            memory_type="workspace",
            status="active",
        )


def test_confirming_candidate_activates_memory(tmp_path):
    manager = _manager(tmp_path)
    item = manager.store(
        content="candidate",
        workspace_id="w",
        memory_type="workspace",
        status="candidate",
    )

    updated = manager.update(item.id, status="confirmed", confirmed=True)

    assert updated.status == "confirmed"
    assert manager.retrieve(workspace_id="w")[0].id == item.id


def test_archived_memory_is_filtered(tmp_path):
    manager = _manager(tmp_path)
    manager.store(
        content="archived",
        workspace_id="w",
        memory_type="workspace",
        status="archived",
        system_marked=True,
    )

    assert manager.retrieve(workspace_id="w") == []


def test_lifecycle_expiration_helpers():
    item = MemoryItem.create(
        workspace_id="w",
        memory_type="workspace",
        content="expires",
        expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
    )

    assert is_expired(item)
    assert not is_active(item)
