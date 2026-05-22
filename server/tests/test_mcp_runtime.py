"""Runtime MCP tool wrapper-level tests.

We do **not** boot a real AICCRuntime here (blade.Game init is slow
and tied to the SCS template). Instead we fake a tiny scenario-shaped object
and call the pure-Python helpers (_runtime_status_payload /
_runtime_outcome_payload) that every runtime tool eventually funnels into.

Lifespan smoke (real engine, real SCS.json) was validated separately and
reported in the README. This pytest layer is here so service-layer breakage
of the runtime DTOs is caught in CI.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.mcp.server import (
    _get_runtime,
    _runtime_outcome_payload,
    _runtime_side_stats,
    _runtime_status_payload,
    _runtime_unit_counts,
    reset_request_user,
    set_request_user,
    set_shared_runtime_provider,
)
from app.mcp.schemas import RuntimeOutcome, RuntimeStatus


def _make_unit(side_id: str) -> SimpleNamespace:
    return SimpleNamespace(side_id=side_id)


def _make_side(side_id: str, name: str, color: str = "blue") -> SimpleNamespace:
    return SimpleNamespace(id=side_id, name=name, color=color, total_score=0)


def _make_runtime(
    *,
    sides: list[SimpleNamespace],
    aircraft: list[SimpleNamespace] | None = None,
    ships: list[SimpleNamespace] | None = None,
    facilities: list[SimpleNamespace] | None = None,
    airbases: list[SimpleNamespace] | None = None,
    weapons: list[SimpleNamespace] | None = None,
    reference_points: list[SimpleNamespace] | None = None,
    start_time: int = 1000,
    duration: int = 600,
    current_time: int | None = None,
    paused: bool = True,
    game_outcome: dict | None = None,
) -> SimpleNamespace:
    """Build the minimum object graph that ``_runtime_*`` helpers walk."""
    scenario = SimpleNamespace(
        id="s1",
        name="unit-test",
        start_time=start_time,
        duration=duration,
        current_time=current_time if current_time is not None else start_time,
        sides=sides,
        aircraft=aircraft or [],
        ships=ships or [],
        facilities=facilities or [],
        airbases=airbases or [],
        weapons=weapons or [],
        reference_points=reference_points or [],
    )
    game = SimpleNamespace(
        current_scenario=scenario,
        scenario_paused=paused,
        game_outcome=game_outcome
        or {"ended": False, "winner_side_id": "", "reason": "", "ended_at": 0},
    )
    return SimpleNamespace(game=game)


# ---------- counts -----------------------------------------------------------


def test_unit_counts_aggregate_all_buckets():
    runtime = _make_runtime(
        sides=[_make_side("blue", "BLUE")],
        aircraft=[_make_unit("blue"), _make_unit("blue")],
        ships=[_make_unit("blue")],
        weapons=[_make_unit("blue"), _make_unit("blue"), _make_unit("blue")],
    )
    counts = _runtime_unit_counts(runtime)
    assert counts == {
        "aircraft": 2,
        "ship": 1,
        "facility": 0,
        "airbase": 0,
        "weapon": 3,
        "referencePoint": 0,
    }


def test_side_stats_validates_against_schema():
    runtime = _make_runtime(
        sides=[
            _make_side("blue", "BLUE", color="blue"),
            _make_side("red", "RED", color="red"),
        ]
    )
    stats = _runtime_side_stats(runtime)
    assert len(stats) == 2
    assert stats[0].id == "blue"
    assert stats[1].name == "RED"


# ---------- status -----------------------------------------------------------


def test_status_payload_computes_elapsed_and_duration_left():
    runtime = _make_runtime(
        sides=[_make_side("blue", "BLUE")],
        aircraft=[_make_unit("blue")],
        start_time=100,
        duration=500,
        current_time=350,
        paused=False,
    )
    payload = _runtime_status_payload(runtime)
    # Round-trip through schema to catch any drift.
    parsed = RuntimeStatus.model_validate(payload)
    assert parsed.current_time == 350
    assert parsed.elapsed == 250
    assert parsed.duration_left == 250
    assert parsed.paused is False
    assert parsed.counts["aircraft"] == 1


def test_status_payload_handles_missing_current_time():
    runtime = _make_runtime(
        sides=[_make_side("blue", "BLUE")], start_time=42, current_time=None
    )
    payload = _runtime_status_payload(runtime)
    # ``current_time=None`` in SimpleNamespace passes through to helper which
    # should fall back to start_time.
    assert payload["current_time"] == 42
    assert payload["elapsed"] == 0


# ---------- outcome ----------------------------------------------------------


def test_outcome_detects_time_up():
    runtime = _make_runtime(
        sides=[_make_side("blue", "BLUE"), _make_side("red", "RED")],
        aircraft=[_make_unit("blue"), _make_unit("red")],
        start_time=0,
        duration=100,
        current_time=100,
    )
    payload = _runtime_outcome_payload(runtime)
    parsed = RuntimeOutcome.model_validate(payload)
    assert parsed.time_up is True
    assert parsed.duration_left == 0
    # Both sides alive: no inferred winner.
    assert parsed.inferred_winner_side_id is None
    assert sorted(parsed.surviving_side_ids) == ["blue", "red"]


def test_outcome_reports_annihilation_without_declaring_winner():
    runtime = _make_runtime(
        sides=[_make_side("blue", "BLUE"), _make_side("red", "RED")],
        aircraft=[_make_unit("blue")],  # RED has no combat units left
        ships=[],
        start_time=0,
        duration=600,
        current_time=300,
    )
    payload = _runtime_outcome_payload(runtime)
    parsed = RuntimeOutcome.model_validate(payload)
    assert parsed.time_up is False
    assert parsed.annihilated_side_ids == ["red"]
    assert parsed.surviving_side_ids == ["blue"]
    assert parsed.ended is False
    assert parsed.inferred_winner_side_id is None


def test_outcome_uses_runtime_game_outcome_for_winner():
    runtime = _make_runtime(
        sides=[_make_side("blue", "BLUE"), _make_side("red", "RED")],
        aircraft=[_make_unit("blue"), _make_unit("red")],
        start_time=0,
        duration=600,
        current_time=42,
        game_outcome={
            "ended": True,
            "winner_side_id": "blue",
            "reason": "KEY_UNIT_DESTROYED",
            "ended_at": 42,
        },
    )
    payload = _runtime_outcome_payload(runtime)
    parsed = RuntimeOutcome.model_validate(payload)
    assert parsed.ended is True
    assert parsed.winner_side_id == "blue"
    assert parsed.inferred_winner_side_id == "blue"
    assert parsed.reason == "KEY_UNIT_DESTROYED"
    assert parsed.ended_at == 42


def test_outcome_no_winner_when_all_annihilated():
    runtime = _make_runtime(
        sides=[_make_side("blue", "BLUE"), _make_side("red", "RED")],
        # Empty buckets entirely.
        start_time=0,
        duration=600,
        current_time=300,
    )
    payload = _runtime_outcome_payload(runtime)
    parsed = RuntimeOutcome.model_validate(payload)
    assert parsed.annihilated_side_ids == ["blue", "red"]
    assert parsed.surviving_side_ids == []
    assert parsed.inferred_winner_side_id is None


def test_outcome_no_inferred_winner_when_single_side():
    """Single-side scenarios shouldn't auto-declare a winner just because
    that side is the only survivor: there's no opponent to beat."""
    runtime = _make_runtime(
        sides=[_make_side("blue", "BLUE")],
        aircraft=[_make_unit("blue")],
        start_time=0,
        duration=600,
        current_time=300,
    )
    payload = _runtime_outcome_payload(runtime)
    parsed = RuntimeOutcome.model_validate(payload)
    assert parsed.inferred_winner_side_id is None


# ---------- runtime_provider helper -----------------------------------------


@pytest.mark.asyncio
async def test_run_in_runtime_delegates_to_thread():
    """``run_in_runtime`` must invoke the callable in a worker thread to keep
    the event loop unblocked when wrapping sync runtime methods."""
    import threading

    from app.mcp.runtime_provider import run_in_runtime

    # Read main loop thread name **directly** (not via to_thread) so we have
    # a stable reference; if the wrapper is correctly using to_thread, the
    # worker name should differ.
    main_loop_thread = threading.current_thread().name

    def _identity(value: int) -> tuple[int, str]:
        return value, threading.current_thread().name

    result_value, worker_thread = await run_in_runtime(_identity, 42)
    assert result_value == 42
    assert worker_thread != main_loop_thread


def test_get_runtime_uses_per_request_user_provider():
    user = SimpleNamespace(id="user-a")
    runtime = _make_runtime(sides=[_make_side("blue", "BLUE")])
    ctx = SimpleNamespace(
        request_context=SimpleNamespace(
            lifespan_context=SimpleNamespace(user=None, runtime=None)
        )
    )

    token = set_request_user(user)
    set_shared_runtime_provider(lambda current_user: runtime if current_user.id == user.id else None)
    try:
        assert _get_runtime(ctx) is runtime
    finally:
        reset_request_user(token)
        set_shared_runtime_provider(None)
