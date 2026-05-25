from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[2]
GYM_DIR = ROOT_DIR / "gym"
if str(GYM_DIR) not in sys.path:
    sys.path.insert(0, str(GYM_DIR))

from blade.Game import Game  # noqa: E402
from blade.Scenario import Scenario  # noqa: E402
from blade.Side import Side  # noqa: E402
from blade.units.Aircraft import Aircraft  # noqa: E402


def _game_with_aircraft() -> Game:
    scenario = Scenario(
        id="safe-actions",
        name="Safe Actions",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[Side(id="blue", name="BLUE", color="blue")],
        aircraft=[
            Aircraft(
                id="aircraft-1",
                name="Blue Aircraft",
                side_id="blue",
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
            )
        ],
    )
    game = Game(current_scenario=scenario)
    game.current_side_id = "blue"
    return game


def test_handle_action_allows_only_whitelisted_literal_method_calls() -> None:
    game = _game_with_aircraft()

    game.handle_action("move_aircraft('aircraft-1', [[1.0, 2.0], [3.0, 4.0]])")
    game.handle_action("self.aircraft_return_to_base('aircraft-1')")

    aircraft = game.current_scenario.get_aircraft("aircraft-1")
    assert aircraft is not None
    assert aircraft.route == [[1.0, 2.0], [3.0, 4.0]]
    assert aircraft.rtb is True


def test_handle_action_rejects_non_call_code_without_mutating_state() -> None:
    game = _game_with_aircraft()

    with pytest.raises(ValueError):
        game.handle_action("self.current_scenario.name = 'modified-by-script'")

    assert game.current_scenario.name == "Safe Actions"


def test_handle_action_rejects_attribute_chains_and_dynamic_arguments() -> None:
    game = _game_with_aircraft()

    with pytest.raises(ValueError):
        game.handle_action("self.current_scenario.get_aircraft('aircraft-1')")
    with pytest.raises(ValueError):
        game.handle_action("move_aircraft('aircraft-1', __import__('os'))")

    aircraft = game.current_scenario.get_aircraft("aircraft-1")
    assert aircraft is not None
    assert aircraft.route == []
