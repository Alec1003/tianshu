from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
GYM_DIR = ROOT_DIR / "gym"
if str(GYM_DIR) not in sys.path:
    sys.path.insert(0, str(GYM_DIR))

from blade.Game import Game  # noqa: E402
from blade.Scenario import Scenario  # noqa: E402
from blade.Side import Side  # noqa: E402
from blade.engine.weaponEngagement import on_unit_destroyed  # noqa: E402
from blade.units.Aircraft import Aircraft  # noqa: E402


def _side(side_id: str, score: int = 0) -> Side:
    return Side(id=side_id, name=side_id.upper(), total_score=score, color="blue")


def _aircraft(unit_id: str, side_id: str, is_objective: bool = False) -> Aircraft:
    return Aircraft(
        id=unit_id,
        name=unit_id,
        side_id=side_id,
        class_name="Test Aircraft",
        latitude=0.0,
        longitude=0.0,
        altitude=1000.0,
        heading=0.0,
        speed=300.0,
        current_fuel=1000.0,
        max_fuel=1000.0,
        fuel_rate=100.0,
        range=100.0,
        is_objective=is_objective,
    )


def _game(scenario: Scenario) -> Game:
    game = Game(current_scenario=scenario)
    game.current_side_id = scenario.sides[0].id
    return game


def test_key_unit_destroyed_sets_score_event_and_winner() -> None:
    blue = _side("blue")
    red = _side("red")
    scenario = Scenario(
        id="s1",
        name="Victory",
        start_time=0,
        current_time=12,
        duration=600,
        sides=[blue, red],
    )
    vip = _aircraft("vip-red", "red", is_objective=True)

    on_unit_destroyed(scenario, "blue", vip)
    game = _game(scenario)

    assert blue.total_score == 210
    assert scenario.last_objective_destroyed == {
        "attacker_side_id": "blue",
        "victim_side_id": "red",
        "unit_id": "vip-red",
        "unit_name": "vip-red",
        "unit_type": "aircraft",
        "destroyed_at": 12,
    }
    assert game.check_game_ended() is True
    assert game.game_outcome == {
        "ended": True,
        "winner_side_id": "blue",
        "reason": "KEY_UNIT_DESTROYED",
        "ended_at": 12,
    }


def test_annihilation_does_not_end_game() -> None:
    scenario = Scenario(
        id="s1",
        name="No annihilation victory",
        start_time=0,
        current_time=10,
        duration=600,
        sides=[_side("blue"), _side("red")],
        aircraft=[_aircraft("a1", "blue")],
    )
    game = _game(scenario)

    assert game.check_game_ended() is False
    assert game.game_outcome["ended"] is False


def test_timeout_uses_highest_score_side() -> None:
    scenario = Scenario(
        id="s1",
        name="Timeout",
        start_time=0,
        current_time=60,
        duration=60,
        sides=[_side("blue", score=50), _side("red", score=30)],
    )
    game = _game(scenario)

    assert game.check_game_ended() is True
    assert game.game_outcome == {
        "ended": True,
        "winner_side_id": "blue",
        "reason": "TIMEOUT",
        "ended_at": 60,
    }
