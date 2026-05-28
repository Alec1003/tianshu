from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.aicc_runtime.persistence import (
    ensure_runtime_state_loaded,
    load_runtime_state,
    restore_runtime_state,
    save_runtime_state,
)


class _FakeRuntime:
    def __init__(self, scenario_id: str = "runtime-1") -> None:
        self.scenario = {
            "currentScenario": {"id": scenario_id},
            "currentSideId": "blue",
            "mapView": {},
        }
        self.runtime_metadata = {
            "paused": False,
            "currentSideId": "blue",
            "gameOutcome": {
                "ended": True,
                "winner_side_id": "blue",
                "reason": "test",
                "ended_at": 123,
            },
            "script": {
                "steps": ["step-one"],
                "cursor": 1,
                "paused": True,
            },
        }
        self.loaded: tuple[dict, dict] | None = None
        self.load_count = 0

    def export_runtime_state(self) -> dict:
        return {
            "scenario": self.scenario,
            "runtime_metadata": self.runtime_metadata,
        }

    def load_runtime_state(
        self,
        scenario: dict,
        runtime_metadata: dict,
    ) -> dict:
        self.loaded = (scenario, runtime_metadata)
        self.scenario = scenario
        self.runtime_metadata = runtime_metadata
        self.load_count += 1
        return {"loaded": True}


@pytest.mark.anyio
async def test_runtime_state_save_updates_one_user_snapshot(db_session, user) -> None:
    runtime = _FakeRuntime()

    first = await save_runtime_state(db_session, user, runtime)
    assert first is not None
    assert first.version == 1
    assert first.scenario["currentScenario"]["id"] == "runtime-1"
    assert first.runtime_metadata["paused"] is False

    runtime.scenario = {
        "currentScenario": {"id": "runtime-2"},
        "currentSideId": "red",
        "mapView": {},
    }
    runtime.runtime_metadata = {
        **runtime.runtime_metadata,
        "paused": True,
        "currentSideId": "red",
    }
    second = await save_runtime_state(db_session, user, runtime)
    assert second is not None
    assert second.id == first.id
    assert second.version == 2

    loaded = await load_runtime_state(db_session, user)
    assert loaded is not None
    assert loaded.scenario["currentScenario"]["id"] == "runtime-2"
    assert loaded.runtime_metadata["paused"] is True
    assert loaded.runtime_metadata["currentSideId"] == "red"


@pytest.mark.anyio
async def test_runtime_state_is_scoped_by_scenario_context(db_session, user) -> None:
    first = await save_runtime_state(
        db_session,
        user,
        _FakeRuntime("runtime-alpha"),
        scenario_id="scenario-alpha",
    )
    second = await save_runtime_state(
        db_session,
        user,
        _FakeRuntime("runtime-bravo"),
        scenario_id="scenario-bravo",
    )

    assert first is not None
    assert second is not None
    assert first.id != second.id

    loaded_alpha = await load_runtime_state(
        db_session,
        user,
        scenario_id="scenario-alpha",
    )
    loaded_bravo = await load_runtime_state(
        db_session,
        user,
        scenario_id="scenario-bravo",
    )

    assert loaded_alpha is not None
    assert loaded_bravo is not None
    assert loaded_alpha.scenario["currentScenario"]["id"] == "runtime-alpha"
    assert loaded_bravo.scenario["currentScenario"]["id"] == "runtime-bravo"


@pytest.mark.anyio
async def test_runtime_state_restore_and_ensure_are_per_runtime_once(
    db_session,
    user,
) -> None:
    await save_runtime_state(db_session, user, _FakeRuntime("persisted"))

    runtime = _FakeRuntime("fresh")
    restored = await restore_runtime_state(db_session, user, runtime)
    assert restored is not None
    assert runtime.loaded is not None
    assert runtime.scenario["currentScenario"]["id"] == "persisted"
    assert runtime.runtime_metadata["gameOutcome"]["reason"] == "test"

    runtime_once = _FakeRuntime("once")
    await ensure_runtime_state_loaded(db_session, user, runtime_once)
    await ensure_runtime_state_loaded(db_session, user, runtime_once)
    assert runtime_once.load_count == 1


@pytest.mark.anyio
async def test_runtime_state_skips_non_uuid_test_users(db_session) -> None:
    runtime = _FakeRuntime("not-persisted")
    user = SimpleNamespace(id="user-1")

    saved = await save_runtime_state(db_session, user, runtime)

    assert saved is None
