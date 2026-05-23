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
from blade.units.Aircraft import Aircraft  # noqa: E402


def _aircraft(
    aircraft_id: str,
    *,
    current_fuel: float,
    is_tanker: bool = False,
    latitude: float = 0.0,
    longitude: float = 0.0,
) -> Aircraft:
    return Aircraft(
        id=aircraft_id,
        name=aircraft_id,
        side_id="blue",
        class_name="KC-135R Stratotanker" if is_tanker else "F-16 Fighting Falcon",
        latitude=latitude,
        longitude=longitude,
        altitude=10000.0,
        heading=90.0,
        speed=300.0,
        current_fuel=current_fuel,
        max_fuel=200000.0 if is_tanker else 10000.0,
        fuel_rate=0.0,
        range=100.0,
        is_tanker=is_tanker,
        fuel_offload_capacity=1000.0 if is_tanker else 0.0,
        fuel_transfer_rate=250.0 if is_tanker else 0.0,
        refuel_range=2.0 if is_tanker else 0.0,
    )


def test_aerial_refueling_transfers_fuel_to_same_side_receiver_in_range() -> None:
    tanker = _aircraft("tanker", current_fuel=50000.0, is_tanker=True)
    receiver = _aircraft("receiver", current_fuel=1000.0)
    scenario = Scenario(
        id="s1",
        name="Aerial refueling",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[Side(id="blue", name="BLUE", color="blue")],
        aircraft=[tanker, receiver],
    )
    game = Game(current_scenario=scenario)

    events = game.aerial_refueling()

    assert events == [
        {
            "refueled": True,
            "receiverId": "receiver",
            "tankerId": "tanker",
            "fuelTransferred": 250.0,
            "receiverFuel": 1250.0,
            "tankerFuel": 49750.0,
            "tankerOffloadRemaining": 750.0,
        }
    ]
    assert receiver.current_fuel == 1250.0
    assert tanker.current_fuel == 49750.0
    assert tanker.fuel_offload_capacity == 750.0


def test_aerial_refueling_ignores_receivers_outside_tanker_range() -> None:
    tanker = _aircraft("tanker", current_fuel=50000.0, is_tanker=True)
    receiver = _aircraft("receiver", current_fuel=1000.0, latitude=1.0)
    scenario = Scenario(
        id="s2",
        name="Aerial refueling out of range",
        start_time=0,
        current_time=0,
        duration=600,
        sides=[Side(id="blue", name="BLUE", color="blue")],
        aircraft=[tanker, receiver],
    )
    game = Game(current_scenario=scenario)

    events = game.aerial_refueling()

    assert events == []
    assert receiver.current_fuel == 1000.0
    assert tanker.current_fuel == 50000.0
