from __future__ import annotations

import json
import sys
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4


ROOT_DIR = Path(__file__).resolve().parents[3]
GYM_DIR = ROOT_DIR / "gym"

if str(GYM_DIR) not in sys.path:
    sys.path.insert(0, str(GYM_DIR))

from blade.Game import Game  # type: ignore  # noqa: E402
from blade.Scenario import Scenario  # type: ignore  # noqa: E402
from blade.db.UnitDb import AirbaseDb, AircraftDb, FacilityDb, ShipDb  # type: ignore  # noqa: E402
from blade.units.Airbase import Airbase  # type: ignore  # noqa: E402
from blade.units.Aircraft import Aircraft  # type: ignore  # noqa: E402
from blade.units.Facility import Facility  # type: ignore  # noqa: E402
from blade.units.ReferencePoint import ReferencePoint  # type: ignore  # noqa: E402
from blade.units.Ship import Ship  # type: ignore  # noqa: E402

from app.panopticon._doctrine import (  # noqa: E402
    _DEFAULT_SIDE_DOCTRINE,
    default_doctrine_for_sides as _default_doctrine_for_sides,
    normalize_scenario_payload as _normalize_scenario_payload_impl,
)


class PanopticonRuntime:
    """Low-intrusion runtime wrapper around Panopticon native simulation engine."""

    def __init__(self, scenario_path: Path) -> None:
        self._lock = RLock()
        self._scenario_path = scenario_path
        self._script_steps: list[str] = []
        self._script_cursor: int = 0
        self._script_paused: bool = True
        self.game = Game(current_scenario=Scenario())
        self._bootstrap()

    def _bootstrap(self) -> None:
        with self._lock:
            self.load_scenario_from_file(self._scenario_path)

    @staticmethod
    def _enum_to_value(value: Any) -> Any:
        return getattr(value, "value", value)

    @staticmethod
    def _to_float(value: Any, default: float) -> float:
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_int(value: Any, default: int) -> int:
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _normalize_scenario_payload(scenario_json: str) -> str:
        """委托给 ``app.panopticon._doctrine.normalize_scenario_payload``。

        逻辑见该模块文档；保留这个 staticmethod 是因为现有调用方都通过
        ``PanopticonRuntime._normalize_scenario_payload`` 访问。
        """
        return _normalize_scenario_payload_impl(scenario_json)

    def _resolve_side_id(self, side_ref: str | None) -> str:
        if side_ref:
            for side in self.game.current_scenario.sides:
                if side.id == side_ref or side.name.lower() == side_ref.lower():
                    return side.id
        if self.game.current_side_id:
            return self.game.current_side_id
        if self.game.current_scenario.sides:
            return self.game.current_scenario.sides[0].id
        raise ValueError("No side available in current scenario")

    def _side_color(self, side_id: str) -> Any:
        side = self.game.current_scenario.get_side(side_id)
        if side is None:
            return "black"
        return self._enum_to_value(side.color)

    @staticmethod
    def _find_db_row(rows: list[dict[str, Any]], key: str, value: str) -> dict[str, Any]:
        for row in rows:
            if str(row.get(key, "")).lower() == value.lower():
                return row
        return rows[0] if rows else {}

    # ----------------------------- simulation lifecycle -----------------------------
    def start_simulation(self) -> dict[str, Any]:
        with self._lock:
            self.game.scenario_paused = False
            return {"running": True}

    def pause_simulation(self) -> dict[str, Any]:
        with self._lock:
            self.game.scenario_paused = True
            return {"running": False}

    def stop_simulation(self) -> dict[str, Any]:
        with self._lock:
            self.game.scenario_paused = True
            self.game.reset()
            return {"stopped": True}

    def reset_simulation(self) -> dict[str, Any]:
        with self._lock:
            self.game.reset()
            return {"reset": True}

    def step_simulation(self, steps: int = 1) -> dict[str, Any]:
        with self._lock:
            steps = max(1, steps)
            for _ in range(steps):
                self.game.step("")
            return {"steps": steps, "currentTime": self.game.current_scenario.current_time}

    # ----------------------------- scenario / script control -----------------------------
    def load_scenario_from_file(self, scenario_path: Path | str) -> dict[str, Any]:
        with self._lock:
            path = Path(scenario_path)
            if not path.is_absolute():
                path = ROOT_DIR / path
            scenario_text = self._normalize_scenario_payload(
                path.read_text(encoding="utf-8")
            )
            self.game.load_scenario(scenario_text)
            return {"scenarioPath": str(path)}

    def load_scenario_from_json(self, scenario_json: str) -> dict[str, Any]:
        with self._lock:
            self.game.load_scenario(self._normalize_scenario_payload(scenario_json))
            return {"loaded": True}

    def load_script(self, script: list[str] | str) -> dict[str, Any]:
        with self._lock:
            if isinstance(script, str):
                parsed = json.loads(script)
                if not isinstance(parsed, list):
                    raise ValueError("Script must be a JSON array of action strings")
                script_steps = [str(item) for item in parsed]
            else:
                script_steps = [str(item) for item in script]
            self._script_steps = script_steps
            self._script_cursor = 0
            self._script_paused = True
            return {"scriptSteps": len(self._script_steps)}

    def execute_script_step(self) -> dict[str, Any]:
        with self._lock:
            if self._script_cursor >= len(self._script_steps):
                return {"done": True, "cursor": self._script_cursor}
            action = self._script_steps[self._script_cursor]
            self.game.handle_action(action)
            self.game.step("")
            self._script_cursor += 1
            return {"done": self._script_cursor >= len(self._script_steps), "cursor": self._script_cursor}

    def control_script_flow(self, action: str) -> dict[str, Any]:
        with self._lock:
            normalized = action.lower().strip()
            if normalized == "pause":
                self._script_paused = True
            elif normalized == "resume":
                self._script_paused = False
            elif normalized == "reset":
                self._script_cursor = 0
                self._script_paused = True
            return {
                "action": normalized,
                "paused": self._script_paused,
                "cursor": self._script_cursor,
                "total": len(self._script_steps),
            }

    # ----------------------------- unit control -----------------------------
    def deploy_aircraft(
        self,
        class_name: str,
        latitude: float,
        longitude: float,
        side: str | None = None,
        name: str | None = None,
        altitude: float = 10000.0,
    ) -> dict[str, Any]:
        with self._lock:
            side_id = self._resolve_side_id(side)
            side_color = self._side_color(side_id)
            row = self._find_db_row(AircraftDb, "class_name", class_name)
            aircraft = Aircraft(
                id=str(uuid4()),
                name=name or f"{class_name} #{len(self.game.current_scenario.aircraft) + 1}",
                side_id=side_id,
                class_name=class_name,
                latitude=latitude,
                longitude=longitude,
                altitude=altitude,
                heading=90.0,
                speed=self._to_float(row.get("speed"), 350.0),
                current_fuel=self._to_float(row.get("max_fuel"), 100000.0),
                max_fuel=self._to_float(row.get("max_fuel"), 100000.0),
                fuel_rate=self._to_float(row.get("fuel_rate"), 1000.0),
                range=self._to_float(row.get("range"), 100.0),
                side_color=side_color,
                weapons=[],
            )
            self.game.current_scenario.aircraft.append(aircraft)
            return {"unitType": "aircraft", "unitId": aircraft.id, "name": aircraft.name}

    def deploy_ship(
        self,
        class_name: str,
        latitude: float,
        longitude: float,
        side: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            side_id = self._resolve_side_id(side)
            side_color = self._side_color(side_id)
            row = self._find_db_row(ShipDb, "class_name", class_name)
            ship = Ship(
                id=str(uuid4()),
                name=name or f"{class_name} #{len(self.game.current_scenario.ships) + 1}",
                side_id=side_id,
                class_name=class_name,
                latitude=latitude,
                longitude=longitude,
                altitude=0.0,
                heading=90.0,
                speed=self._to_float(row.get("speed"), 30.0),
                current_fuel=self._to_float(row.get("max_fuel"), 1000000.0),
                max_fuel=self._to_float(row.get("max_fuel"), 1000000.0),
                fuel_rate=self._to_float(row.get("fuel_rate"), 10000.0),
                range=self._to_float(row.get("range"), 1000.0),
                side_color=side_color,
                weapons=[],
                aircraft=[],
            )
            self.game.current_scenario.ships.append(ship)
            return {"unitType": "ship", "unitId": ship.id, "name": ship.name}

    def deploy_facility(
        self,
        class_name: str,
        latitude: float,
        longitude: float,
        side: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            side_id = self._resolve_side_id(side)
            side_color = self._side_color(side_id)
            row = self._find_db_row(FacilityDb, "class_name", class_name)
            facility = Facility(
                id=str(uuid4()),
                name=name or f"{class_name} #{len(self.game.current_scenario.facilities) + 1}",
                side_id=side_id,
                class_name=class_name,
                latitude=latitude,
                longitude=longitude,
                altitude=0.0,
                range=self._to_float(row.get("range"), 50.0),
                side_color=side_color,
                weapons=[],
            )
            self.game.current_scenario.facilities.append(facility)
            return {"unitType": "facility", "unitId": facility.id, "name": facility.name}

    def deploy_airbase(
        self,
        class_name: str,
        latitude: float,
        longitude: float,
        side: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            side_id = self._resolve_side_id(side)
            side_color = self._side_color(side_id)
            _row = self._find_db_row(AirbaseDb, "name", class_name)
            airbase = Airbase(
                id=str(uuid4()),
                name=name or class_name,
                side_id=side_id,
                class_name=class_name,
                latitude=latitude,
                longitude=longitude,
                altitude=0.0,
                side_color=side_color,
                aircraft=[],
            )
            self.game.current_scenario.airbases.append(airbase)
            return {"unitType": "airbase", "unitId": airbase.id, "name": airbase.name}

    def deploy_reference_point(
        self, name: str, latitude: float, longitude: float, side: str | None = None
    ) -> dict[str, Any]:
        with self._lock:
            side_id = self._resolve_side_id(side)
            self.game.current_side_id = side_id
            point = self.game.add_reference_point(name, latitude, longitude)
            if point is None:
                raise ValueError("Failed to create reference point")
            return {"unitType": "reference_point", "unitId": point.id, "name": point.name}

    def delete_unit(self, unit_type: str, unit_id: str) -> dict[str, Any]:
        with self._lock:
            unit_type = unit_type.lower().strip()
            if unit_type == "aircraft":
                self.game.current_scenario.aircraft = [
                    item for item in self.game.current_scenario.aircraft if item.id != unit_id
                ]
            elif unit_type == "ship":
                self.game.current_scenario.ships = [
                    item for item in self.game.current_scenario.ships if item.id != unit_id
                ]
            elif unit_type == "facility":
                self.game.current_scenario.facilities = [
                    item for item in self.game.current_scenario.facilities if item.id != unit_id
                ]
            elif unit_type == "airbase":
                self.game.current_scenario.airbases = [
                    item for item in self.game.current_scenario.airbases if item.id != unit_id
                ]
            elif unit_type in {"reference_point", "referencepoint"}:
                self.game.current_scenario.reference_points = [
                    item
                    for item in self.game.current_scenario.reference_points
                    if item.id != unit_id
                ]
            else:
                raise ValueError(f"Unsupported unit type for delete: {unit_type}")
            return {"deleted": True, "unitType": unit_type, "unitId": unit_id}

    def move_unit(
        self, unit_type: str, unit_id: str, route: list[list[float]]
    ) -> dict[str, Any]:
        with self._lock:
            unit_type = unit_type.lower().strip()
            if unit_type == "aircraft":
                self.game.move_aircraft(unit_id, route)
            elif unit_type == "ship":
                self.game.move_ship(unit_id, route)
            else:
                raise ValueError("move_unit only supports aircraft and ship")
            return {"moved": True, "unitType": unit_type, "unitId": unit_id}

    def update_unit_state(
        self, unit_type: str, unit_id: str, patch: dict[str, Any]
    ) -> dict[str, Any]:
        with self._lock:
            unit_type = unit_type.lower().strip()
            if unit_type == "aircraft":
                aircraft = self.game.current_scenario.get_aircraft(unit_id)
                if aircraft is None:
                    raise ValueError("Aircraft not found")
                self.game.current_scenario.update_aircraft(
                    aircraft_id=unit_id,
                    aircraft_name=str(patch.get("name", aircraft.name)),
                    aircraft_class_name=str(patch.get("class_name", aircraft.class_name)),
                    aircraft_speed=self._to_float(patch.get("speed"), aircraft.speed),
                    aircraft_current_fuel=self._to_float(
                        patch.get("current_fuel"), aircraft.current_fuel
                    ),
                    aircraft_fuel_rate=self._to_float(
                        patch.get("fuel_rate"), aircraft.fuel_rate
                    ),
                )
            elif unit_type == "ship":
                ship = self.game.current_scenario.get_ship(unit_id)
                if ship is None:
                    raise ValueError("Ship not found")
                self.game.current_scenario.update_ship(
                    ship_id=unit_id,
                    ship_name=str(patch.get("name", ship.name)),
                    ship_class_name=str(patch.get("class_name", ship.class_name)),
                    ship_speed=self._to_float(patch.get("speed"), ship.speed),
                    ship_current_fuel=self._to_float(
                        patch.get("current_fuel"), ship.current_fuel
                    ),
                    ship_fuel_rate=self._to_float(patch.get("fuel_rate"), ship.fuel_rate),
                    ship_range=self._to_float(patch.get("range"), ship.range),
                )
            elif unit_type == "facility":
                facility = self.game.current_scenario.get_facility(unit_id)
                if facility is None:
                    raise ValueError("Facility not found")
                self.game.current_scenario.update_facility(
                    facility_id=unit_id,
                    facility_name=str(patch.get("name", facility.name)),
                    facility_class_name=str(patch.get("class_name", facility.class_name)),
                    facility_range=self._to_float(patch.get("range"), facility.range),
                )
            elif unit_type == "airbase":
                airbase = self.game.current_scenario.get_airbase(unit_id)
                if airbase is None:
                    raise ValueError("Airbase not found")
                self.game.current_scenario.update_airbase(
                    airbase_id=unit_id,
                    airbase_name=str(patch.get("name", airbase.name)),
                )
            elif unit_type in {"reference_point", "referencepoint"}:
                point = self.game.current_scenario.get_reference_point(unit_id)
                if point is None:
                    raise ValueError("Reference point not found")
                self.game.current_scenario.update_reference_point(
                    reference_point_id=unit_id,
                    reference_point_name=str(patch.get("name", point.name)),
                )
            else:
                raise ValueError(f"Unsupported unit type for update: {unit_type}")
            return {"updated": True, "unitType": unit_type, "unitId": unit_id}

    # ----------------------------- situation / event control -----------------------------
    def trigger_tactical_event(
        self, event_name: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        with self._lock:
            payload = payload or {}
            if event_name == "custom_action":
                action = payload.get("action", "")
                self.game.handle_action(action)
            elif event_name == "set_relationship":
                side_id = self._resolve_side_id(payload.get("side"))
                hostiles = list(payload.get("hostiles", []))
                allies = list(payload.get("allies", []))
                self.game.current_scenario.relationships.update_relationship(
                    side_id, hostiles, allies
                )
            elif event_name == "set_current_side":
                side_id = self._resolve_side_id(payload.get("side"))
                self.game.current_side_id = side_id
            return {"event": event_name, "payload": payload}

    def update_situation_layer(
        self, layer_name: str, operation: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        with self._lock:
            payload = payload or {}
            layer_name = layer_name.lower().strip()
            operation = operation.lower().strip()
            if layer_name == "reference_points":
                if operation == "add":
                    return self.deploy_reference_point(
                        name=str(payload.get("name", f"RP-{uuid4().hex[:6]}")),
                        latitude=self._to_float(payload.get("latitude"), 0.0),
                        longitude=self._to_float(payload.get("longitude"), 0.0),
                        side=payload.get("side"),
                    )
                if operation == "remove":
                    return self.delete_unit(
                        unit_type="reference_point",
                        unit_id=str(payload.get("id", "")),
                    )
            return {"layer": layer_name, "operation": operation, "payload": payload}

    def get_exported_scenario(self) -> dict[str, Any]:
        with self._lock:
            return self.game.export_scenario()
