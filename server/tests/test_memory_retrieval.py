from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.agent_runtime.context.manager import ContextManager
from app.agent_runtime.memory.manager import MemoryManager
from app.agent_runtime.memory.storage import JsonMemoryStorage


def _manager(tmp_path):
    return MemoryManager(JsonMemoryStorage(tmp_path / "memory.json"))


def test_importance_sorting_without_query(tmp_path):
    manager = _manager(tmp_path)
    manager.store(
        content="low",
        workspace_id="w",
        memory_type="workspace",
        importance=0.1,
        confirmed=True,
    )
    manager.store(
        content="high",
        workspace_id="w",
        memory_type="workspace",
        importance=0.9,
        confirmed=True,
    )

    assert [item.content for item in manager.retrieve(workspace_id="w")] == [
        "high",
        "low",
    ]


def test_keyword_retrieval_ranks_matching_memory(tmp_path):
    manager = _manager(tmp_path)
    manager.store(
        content="carrier air patrol",
        workspace_id="w",
        memory_type="workspace",
        importance=0.2,
        tags=["cap"],
        confirmed=True,
    )
    manager.store(
        content="fuel reserve",
        workspace_id="w",
        memory_type="workspace",
        importance=0.9,
        confirmed=True,
    )

    results = manager.search("carrier patrol", workspace_id="w")

    assert [item.content for item in results] == ["carrier air patrol"]


def test_access_stats_update_on_retrieve(tmp_path):
    manager = _manager(tmp_path)
    item = manager.store(
        content="tracked",
        workspace_id="w",
        memory_type="workspace",
        confirmed=True,
    )

    manager.retrieve(workspace_id="w")
    touched = manager.retrieve(workspace_id="w", update_access=False)[0]

    assert touched.id == item.id
    assert touched.access_count == 1
    assert touched.last_accessed


def test_workspace_and_scenario_isolation_in_ranked_retrieve(tmp_path):
    manager = _manager(tmp_path)
    manager.store(
        content="alpha",
        workspace_id="w1",
        scenario_id="alpha",
        memory_type="scenario",
        confirmed=True,
    )
    manager.store(
        content="other workspace",
        workspace_id="w2",
        scenario_id="alpha",
        memory_type="scenario",
        confirmed=True,
    )

    assert [item.content for item in manager.retrieve(workspace_id="w1", scenario_id="alpha")] == ["alpha"]
    assert manager.retrieve(workspace_id="w1", scenario_id="bravo") == []


def test_context_memory_summary_uses_ranked_memories(tmp_path):
    manager = _manager(tmp_path)
    manager.store(
        content="low priority note",
        workspace_id="w",
        memory_type="workspace",
        importance=0.1,
        confirmed=True,
    )
    manager.store(
        content="high priority note",
        workspace_id="w",
        memory_type="workspace",
        importance=0.9,
        confirmed=True,
    )

    summary = ContextManager(memory_manager=manager)._memory_summary(
        manager.retrieve(workspace_id="w")
    )

    assert summary.index("high priority note") < summary.index("low priority note")
    assert "importance=0.90" in summary


def test_expired_memory_is_filtered(tmp_path):
    manager = _manager(tmp_path)
    manager.store(
        content="expired",
        workspace_id="w",
        memory_type="workspace",
        expires_at=(datetime.now(UTC) - timedelta(days=1)).isoformat(),
        confirmed=True,
    )

    assert manager.retrieve(workspace_id="w") == []
