from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from app.platform.paths import (
    gym_dir,
    resolve_resource_path,
    resource_root,
    unit_assets_file,
)

ROOT_DIR = resource_root()
GYM_DIR = gym_dir()

if str(GYM_DIR) not in sys.path:
    sys.path.insert(0, str(GYM_DIR))

from blade.Game import Game  # type: ignore  # noqa: E402
from blade.Scenario import Scenario  # type: ignore  # noqa: E402
from blade.db.UnitDb import AirbaseDb, AircraftDb, FacilityDb, ShipDb  # type: ignore  # noqa: E402
from blade.Side import Side  # type: ignore  # noqa: E402
from blade.units.Airbase import Airbase  # type: ignore  # noqa: E402
from blade.units.Aircraft import Aircraft  # type: ignore  # noqa: E402
from blade.units.Facility import Facility  # type: ignore  # noqa: E402
from blade.units.Obstacle import Obstacle  # type: ignore  # noqa: E402
from blade.units.ReferencePoint import ReferencePoint  # type: ignore  # noqa: E402
from blade.units.Ship import Ship  # type: ignore  # noqa: E402
from blade.units.Weapon import Weapon  # type: ignore  # noqa: E402

from app.tianshu_runtime._doctrine import (  # noqa: E402
    _DEFAULT_SIDE_DOCTRINE,
    default_doctrine_for_sides as _default_doctrine_for_sides,
    normalize_scenario_payload as _normalize_scenario_payload_impl,
)


DEFAULT_AIRCRAFT_WEAPON_KEYS = {
    "AIM-120 AMRAAM": 4,
    "AIM-9 Sidewinder": 2,
    "AGM-65 Maverick": 2,
}
DEFAULT_FACILITY_WEAPON_KEYS = {
    "48N6 (S-400 Triumf)": 8,
    "9M96 (S-300V4)": 12,
    "57E6E (Pantsir-S1)": 16,
}
DEFAULT_SHIP_WEAPON_KEYS = {
    "RIM-174 Standard SM-6": 96,
    "RIM-116 RAM": 42,
    "RGM-84 Harpoon": 8,
}
FALLBACK_WEAPON_TEMPLATES = {
    "AIM-120 AMRAAM": {
        "speed": 2600.0,
        "max_fuel": 480.0,
        "fuel_rate": 350.0,
        "range": 86.0,
        "lethality": 0.65,
        "target_types": ["aircraft"],
    },
    "AIM-9 Sidewinder": {
        "speed": 1500.0,
        "max_fuel": 100.0,
        "fuel_rate": 80.0,
        "range": 15.6,
        "lethality": 0.60,
        "target_types": ["aircraft"],
    },
    "AGM-65 Maverick": {
        "speed": 600.0,
        "max_fuel": 200.0,
        "fuel_rate": 120.0,
        "range": 12.0,
        "lethality": 0.70,
        "target_types": ["facility", "airbase", "ship"],
    },
    "48N6 (S-400 Triumf)": {
        "speed": 3966.0,
        "max_fuel": 1543.0,
        "fuel_rate": 300.0,
        "range": 135.0,
        "lethality": 0.90,
        "target_types": ["aircraft", "weapon"],
    },
    "9M96 (S-300V4)": {
        "speed": 2644.0,
        "max_fuel": 1000.0,
        "fuel_rate": 200.0,
        "range": 65.0,
        "lethality": 0.85,
        "target_types": ["aircraft", "weapon"],
    },
    "57E6E (Pantsir-S1)": {
        "speed": 2313.0,
        "max_fuel": 250.0,
        "fuel_rate": 80.0,
        "range": 10.8,
        "lethality": 0.70,
        "target_types": ["aircraft", "weapon"],
    },
    "RIM-174 Standard SM-6": {
        "speed": 2313.0,
        "max_fuel": 1100.0,
        "fuel_rate": 300.0,
        "range": 130.0,
        "lethality": 0.90,
        "target_types": ["aircraft", "weapon", "ship"],
    },
    "RIM-116 RAM": {
        "speed": 1653.0,
        "max_fuel": 250.0,
        "fuel_rate": 100.0,
        "range": 5.5,
        "lethality": 0.80,
        "target_types": ["aircraft", "weapon"],
    },
    "RGM-84 Harpoon": {
        "speed": 475.0,
        "max_fuel": 700.0,
        "fuel_rate": 150.0,
        "range": 67.0,
        "lethality": 0.80,
        "target_types": ["ship"],
    },
}


def _template_target_types(row: dict[str, Any]) -> list[str]:
    for key in (
        "targetTypes",
        "target_types",
        "allowedTargetTypes",
        "allowed_target_types",
        "targetDomains",
        "target_domains",
    ):
        value = row.get(key)
        if isinstance(value, list):
            return [str(item).strip().lower() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [item.strip().lower() for item in value.split(",") if item.strip()]
    return []


def _load_weapon_templates() -> dict[str, dict[str, Any]]:
    templates = dict(FALLBACK_WEAPON_TEMPLATES)
    source = unit_assets_file()
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return templates

    for row in data.get("weaponDb", []):
        class_name = row.get("className") or row.get("class_name")
        if not class_name:
            continue
        fallback = templates.get(str(class_name), {})
        target_types = _template_target_types(row) or list(
            fallback.get("target_types", [])
        )
        templates[str(class_name)] = {
            "speed": float(row.get("speed", 0.0) or 0.0),
            "max_fuel": float(row.get("maxFuel", row.get("max_fuel", 0.0)) or 0.0),
            "fuel_rate": float(row.get("fuelRate", row.get("fuel_rate", 1.0)) or 1.0),
            "range": float(row.get("range", 0.0) or 0.0),
            "lethality": float(row.get("lethality", 0.0) or 0.0),
            "target_types": target_types,
        }
    return templates


WEAPON_TEMPLATES = _load_weapon_templates()


class TianShuRuntime:
    """Low-intrusion runtime wrapper around TianShu native simulation engine."""

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

    @classmethod
    def _normalize_route(cls, route: list[list[float]]) -> list[list[float]]:
        if len(route) > 32:
            raise ValueError("Route supports at most 32 waypoints")
        normalized_route: list[list[float]] = []
        for index, point in enumerate(route):
            if not isinstance(point, list | tuple) or len(point) != 2:
                raise ValueError(f"Route point {index} must be [latitude, longitude]")
            try:
                latitude = float(point[0])
                longitude = float(point[1])
            except (TypeError, ValueError):
                raise ValueError(f"Route point {index} must contain numeric coordinates") from None
            if not math.isfinite(latitude) or not math.isfinite(longitude):
                raise ValueError(f"Route point {index} must contain finite coordinates")
            if latitude < -90 or latitude > 90:
                raise ValueError(f"Route point {index} latitude out of range")
            if longitude < -180 or longitude > 180:
                raise ValueError(f"Route point {index} longitude out of range")
            normalized_route.append([latitude, longitude])
        return normalized_route

    @staticmethod
    def _normalize_scenario_payload(scenario_json: str) -> str:
        """委托给 ``app.tianshu_runtime._doctrine.normalize_scenario_payload``。

        逻辑见该模块文档；保留这个 staticmethod 是因为现有调用方都通过
        ``TianShuRuntime._normalize_scenario_payload`` 访问。
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

    @staticmethod
    def _find_exact_db_row(
        rows: list[dict[str, Any]], key: str, value: str
    ) -> dict[str, Any] | None:
        normalized_value = value.strip().lower()
        for row in rows:
            if str(row.get(key, "")).strip().lower() == normalized_value:
                return row
        return None

    @classmethod
    def is_known_aircraft_class(cls, class_name: str) -> bool:
        return cls._find_exact_db_row(AircraftDb, "class_name", class_name) is not None

    @classmethod
    def is_known_ship_class(cls, class_name: str) -> bool:
        return cls._find_exact_db_row(ShipDb, "class_name", class_name) is not None

    @classmethod
    def is_known_facility_class(cls, class_name: str) -> bool:
        return cls._find_exact_db_row(FacilityDb, "class_name", class_name) is not None

    @classmethod
    def is_known_airbase_class(cls, class_name: str) -> bool:
        return cls._find_exact_db_row(AirbaseDb, "name", class_name) is not None

    @staticmethod
    def _row_value(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
        for key in keys:
            if key in row and row[key] is not None:
                return row[key]
        return default

    @classmethod
    def _row_bool(
        cls, row: dict[str, Any], *keys: str, default: bool = False
    ) -> bool:
        value = cls._row_value(row, *keys, default=default)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
        return bool(value)

    @classmethod
    def _row_list(cls, row: dict[str, Any], *keys: str) -> list[str]:
        value = cls._row_value(row, *keys, default=[])
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return []

    def _make_weapon(
        self,
        class_name: str,
        quantity: int,
        side_id: str,
        side_color: Any,
        *,
        latitude: float = 0.0,
        longitude: float = 0.0,
        altitude: float = 10000.0,
    ) -> Weapon:
        template = WEAPON_TEMPLATES.get(class_name)
        if template is None:
            raise ValueError(f"Unsupported weapon class: {class_name}")
        return Weapon(
            id=str(uuid4()),
            name=class_name,
            side_id=side_id,
            class_name=class_name,
            latitude=latitude,
            longitude=longitude,
            altitude=altitude,
            heading=90.0,
            speed=self._to_float(template.get("speed"), 0.0),
            current_fuel=self._to_float(template.get("max_fuel"), 0.0),
            max_fuel=self._to_float(template.get("max_fuel"), 0.0),
            fuel_rate=self._to_float(template.get("fuel_rate"), 1.0),
            range=self._to_float(template.get("range"), 0.0),
            side_color=side_color,
            target_id="",
            lethality=self._to_float(template.get("lethality"), 0.0),
            max_quantity=quantity,
            current_quantity=quantity,
            target_types=list(template.get("target_types", [])),
        )

    def _default_weapons(
        self,
        weapon_keys: dict[str, int],
        side_id: str,
        side_color: Any,
        *,
        latitude: float = 0.0,
        longitude: float = 0.0,
        altitude: float = 10000.0,
    ) -> list[Weapon]:
        weapons: list[Weapon] = []
        for class_name, quantity in weapon_keys.items():
            weapons.append(
                self._make_weapon(
                    class_name,
                    quantity,
                    side_id,
                    side_color,
                    latitude=latitude,
                    longitude=longitude,
                    altitude=altitude,
                )
            )
        return weapons

    def _get_unit(self, unit_type: str, unit_id: str) -> Any:
        scenario = self.game.current_scenario
        normalized = unit_type.lower().strip()
        if normalized == "aircraft":
            return scenario.get_aircraft(unit_id)
        if normalized == "ship":
            return scenario.get_ship(unit_id)
        if normalized == "facility":
            return scenario.get_facility(unit_id)
        if normalized == "airbase":
            return scenario.get_airbase(unit_id)
        if normalized in {"reference_point", "referencepoint"}:
            return scenario.get_reference_point(unit_id)
        if normalized == "obstacle":
            return scenario.get_obstacle(unit_id)
        if normalized == "weapon":
            return scenario.get_weapon(unit_id)
        raise ValueError(f"Unsupported unit type: {unit_type}")

    @staticmethod
    def _unique_side_refs(refs: list[str] | None, side_id: str) -> list[str]:
        out: list[str] = []
        for ref in refs or []:
            if ref and ref != side_id and ref not in out:
                out.append(ref)
        return out

    def _sync_side_color(self, side_id: str, color: Any) -> None:
        scenario = self.game.current_scenario
        for airbase in scenario.airbases:
            if airbase.side_id != side_id:
                continue
            airbase.side_color = color
            for aircraft in airbase.aircraft:
                aircraft.side_color = color
                for weapon in aircraft.weapons:
                    weapon.side_color = color
        for ship in scenario.ships:
            if ship.side_id != side_id:
                continue
            ship.side_color = color
            for aircraft in ship.aircraft:
                aircraft.side_color = color
                for weapon in aircraft.weapons:
                    weapon.side_color = color
            for weapon in ship.weapons:
                weapon.side_color = color
        for facility in scenario.facilities:
            if facility.side_id != side_id:
                continue
            facility.side_color = color
            for weapon in facility.weapons:
                weapon.side_color = color
        for aircraft in scenario.aircraft:
            if aircraft.side_id != side_id:
                continue
            aircraft.side_color = color
            for weapon in aircraft.weapons:
                weapon.side_color = color
        for weapon in scenario.weapons:
            if weapon.side_id == side_id:
                weapon.side_color = color
        for point in scenario.reference_points:
            if point.side_id == side_id:
                point.side_color = color
        for obstacle in scenario.obstacles:
            if getattr(obstacle, "side_id", "") == side_id:
                obstacle.side_color = color
        for mission in scenario.missions:
            assigned_area = getattr(mission, "assigned_area", None)
            if assigned_area:
                for point in assigned_area:
                    if point.side_id == side_id:
                        point.side_color = color

    def _remove_unit_references(self, unit_id: str) -> None:
        scenario = self.game.current_scenario
        for aircraft in scenario.aircraft:
            if aircraft.home_base_id == unit_id:
                aircraft.home_base_id = ""
                aircraft.rtb = False
                aircraft.route = []
            if aircraft.target_id == unit_id:
                aircraft.target_id = ""
        for mission in scenario.missions:
            if hasattr(mission, "assigned_unit_ids"):
                mission.assigned_unit_ids = [
                    item for item in mission.assigned_unit_ids if item != unit_id
                ]
            if hasattr(mission, "assigned_target_ids"):
                mission.assigned_target_ids = [
                    item for item in mission.assigned_target_ids if item != unit_id
                ]
            assigned_area = getattr(mission, "assigned_area", None)
            if assigned_area:
                mission.assigned_area = [
                    point for point in assigned_area if point.id != unit_id
                ]
                update_geometry = getattr(mission, "update_patrol_area_geometry", None)
                if callable(update_geometry) and len(mission.assigned_area) >= 3:
                    update_geometry()

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
            requested_steps = int(steps)
            if requested_steps < 1 or requested_steps > 7200:
                raise ValueError("steps must be between 1 and 7200")
            executed_steps = 0
            refueling_events: list[dict[str, Any]] = []
            for _ in range(requested_steps):
                if self.game.check_game_ended():
                    break
                self.game.step("")
                refueling_events.extend(getattr(self.game, "last_refueling_events", []))
                executed_steps += 1
            return {
                "steps": executed_steps,
                "requestedSteps": requested_steps,
                "currentTime": self.game.current_scenario.current_time,
                "refuelingEvents": refueling_events,
            }

    def attack_unit(
        self,
        *,
        attacker_type: str,
        attacker_id: str,
        target_id: str,
        weapon_id: str = "",
        weapon_quantity: int = 1,
        auto: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            scenario = self.game.current_scenario
            attacker_type = attacker_type.lower().strip()
            target = scenario.get_target(target_id)
            if target is None:
                raise ValueError("Target not found")

            if attacker_type == "aircraft":
                attacker = scenario.get_aircraft(attacker_id)
                attack = self.game.handle_aircraft_attack
            elif attacker_type == "ship":
                attacker = scenario.get_ship(attacker_id)
                attack = self.game.handle_ship_attack
            else:
                raise ValueError(f"Unsupported attacker type: {attacker_type}")

            if attacker is None:
                raise ValueError(f"{attacker_type.title()} not found")

            self.game.update_onboard_weapon_positions()
            launched: list[dict[str, Any]] = []

            if auto:
                for weapon in list(attacker.weapons):
                    quantity = int(getattr(weapon, "current_quantity", 0) or 0)
                    if self.game.can_launch_at(attacker, target, weapon, quantity):
                        attack(attacker_id, target_id, weapon.id, quantity)
                        launched.append(
                            {
                                "weaponId": weapon.id,
                                "weaponName": getattr(weapon, "name", ""),
                                "quantity": quantity,
                            }
                        )
            else:
                if weapon_quantity <= 0:
                    return {
                        "attacked": False,
                        "reason": "weapon_quantity_required",
                        "attackerType": attacker_type,
                        "attackerId": attacker_id,
                        "targetId": target_id,
                    }
                weapon = attacker.get_weapon(weapon_id)
                if weapon is None:
                    raise ValueError("Weapon not found")
                if self.game.can_launch_at(attacker, target, weapon, weapon_quantity):
                    attack(attacker_id, target_id, weapon.id, weapon_quantity)
                    launched.append(
                        {
                            "weaponId": weapon.id,
                            "weaponName": getattr(weapon, "name", ""),
                            "quantity": weapon_quantity,
                        }
                    )

            return {
                "attacked": len(launched) > 0,
                "auto": auto,
                "attackerType": attacker_type,
                "attackerId": attacker_id,
                "targetId": target_id,
                "launched": launched,
                "weaponCount": len(scenario.weapons),
            }

    # ----------------------------- scenario / script control -----------------------------
    def load_scenario_from_file(self, scenario_path: Path | str) -> dict[str, Any]:
        with self._lock:
            path = Path(scenario_path)
            if not path.is_absolute():
                path = resolve_resource_path(path)
            scenario_text = self._normalize_scenario_payload(
                path.read_text(encoding="utf-8")
            )
            self.game.load_scenario(scenario_text)
            return {"scenarioPath": str(path)}

    def load_scenario_from_json(self, scenario_json: str) -> dict[str, Any]:
        with self._lock:
            self.game.load_scenario(self._normalize_scenario_payload(scenario_json))
            return {"loaded": True}

    def export_runtime_state(self) -> dict[str, Any]:
        """Return the DB-persistable authoritative runtime snapshot."""
        with self._lock:
            return {
                "scenario": self.game.export_scenario(),
                "runtime_metadata": {
                    "paused": bool(getattr(self.game, "scenario_paused", True)),
                    "currentSideId": getattr(self.game, "current_side_id", ""),
                    "gameOutcome": getattr(self.game, "game_outcome", {}) or {},
                    "script": {
                        "steps": list(self._script_steps),
                        "cursor": self._script_cursor,
                        "paused": self._script_paused,
                    },
                },
            }

    def load_runtime_state(
        self,
        scenario: dict[str, Any],
        runtime_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Restore a snapshot previously produced by ``export_runtime_state``."""
        with self._lock:
            self.game.load_scenario(
                self._normalize_scenario_payload(
                    json.dumps(scenario, ensure_ascii=False)
                )
            )
            metadata = runtime_metadata or {}
            self.game.scenario_paused = bool(metadata.get("paused", True))
            current_side_id = metadata.get("currentSideId") or scenario.get(
                "currentSideId"
            )
            if current_side_id:
                self.game.current_side_id = str(current_side_id)
            game_outcome = metadata.get("gameOutcome")
            if isinstance(game_outcome, dict):
                self.game.game_outcome = game_outcome
            script = metadata.get("script") if isinstance(metadata, dict) else None
            if isinstance(script, dict):
                steps = script.get("steps")
                self._script_steps = [str(item) for item in steps or []]
                self._script_cursor = max(0, self._to_int(script.get("cursor"), 0))
                self._script_paused = bool(script.get("paused", True))
            else:
                self._script_steps = []
                self._script_cursor = 0
                self._script_paused = True
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
        template: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            side_id = self._resolve_side_id(side)
            side_color = self._side_color(side_id)
            row = (
                template
                if template is not None
                else self._find_exact_db_row(AircraftDb, "class_name", class_name)
            )
            if row is None:
                raise ValueError(
                    f"Unknown aircraft class: {class_name}. Add it to the unit asset database before deployment."
                )
            is_tanker = self._row_bool(row, "is_tanker", "isTanker")
            is_electronic_warfare = self._row_bool(
                row, "is_electronic_warfare", "isElectronicWarfare"
            ) or any(
                token in class_name.lower()
                for token in (
                    "electronic",
                    "ewar",
                    "jammer",
                    "growler",
                    "prowler",
                    "raven",
                    "电子战",
                    "干扰",
                )
            )
            aircraft = Aircraft(
                id=str(uuid4()),
                name=name or f"{class_name} #{len(self.game.current_scenario.aircraft) + 1}",
                side_id=side_id,
                class_name=class_name,
                latitude=latitude,
                longitude=longitude,
                altitude=altitude,
                heading=90.0,
                speed=self._to_float(self._row_value(row, "speed"), 350.0),
                current_fuel=self._to_float(
                    self._row_value(row, "max_fuel", "maxFuel"), 100000.0
                ),
                max_fuel=self._to_float(
                    self._row_value(row, "max_fuel", "maxFuel"), 100000.0
                ),
                fuel_rate=self._to_float(
                    self._row_value(row, "fuel_rate", "fuelRate"), 1000.0
                ),
                range=self._to_float(self._row_value(row, "range"), 100.0),
                side_color=side_color,
                weapons=(
                    []
                    if is_tanker or is_electronic_warfare
                    else self._default_weapons(
                        DEFAULT_AIRCRAFT_WEAPON_KEYS,
                        side_id,
                        side_color,
                        latitude=latitude,
                        longitude=longitude,
                        altitude=altitude,
                    )
                ),
                is_tanker=is_tanker,
                fuel_offload_capacity=self._to_float(
                    self._row_value(
                        row, "fuel_offload_capacity", "fuelOffloadCapacity"
                    ),
                    0.0,
                ),
                fuel_transfer_rate=self._to_float(
                    self._row_value(row, "fuel_transfer_rate", "fuelTransferRate"),
                    0.0,
                ),
                refuel_range=self._to_float(
                    self._row_value(row, "refuel_range", "refuelRange"), 0.0
                ),
                is_electronic_warfare=is_electronic_warfare,
                jamming_range=self._to_float(
                    self._row_value(row, "jamming_range", "jammingRange"), 0.0
                ),
                jamming_strength=self._to_float(
                    self._row_value(row, "jamming_strength", "jammingStrength"),
                    0.0,
                ),
                jamming_modes=self._row_list(row, "jamming_modes", "jammingModes"),
                communication_disruption=self._to_float(
                    self._row_value(
                        row, "communication_disruption", "communicationDisruption"
                    ),
                    0.0,
                ),
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
        template: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            side_id = self._resolve_side_id(side)
            side_color = self._side_color(side_id)
            row = (
                template
                if template is not None
                else self._find_exact_db_row(ShipDb, "class_name", class_name)
            )
            if row is None:
                raise ValueError(
                    f"Unknown ship class: {class_name}. Add it to the unit asset database before deployment."
                )
            ship = Ship(
                id=str(uuid4()),
                name=name or f"{class_name} #{len(self.game.current_scenario.ships) + 1}",
                side_id=side_id,
                class_name=class_name,
                latitude=latitude,
                longitude=longitude,
                altitude=0.0,
                heading=90.0,
                speed=self._to_float(self._row_value(row, "speed"), 30.0),
                current_fuel=self._to_float(
                    self._row_value(row, "max_fuel", "maxFuel"), 1000000.0
                ),
                max_fuel=self._to_float(
                    self._row_value(row, "max_fuel", "maxFuel"), 1000000.0
                ),
                fuel_rate=self._to_float(
                    self._row_value(row, "fuel_rate", "fuelRate"), 10000.0
                ),
                range=self._to_float(self._row_value(row, "range"), 1000.0),
                side_color=side_color,
                weapons=self._default_weapons(
                    DEFAULT_SHIP_WEAPON_KEYS,
                    side_id,
                    side_color,
                    latitude=latitude,
                    longitude=longitude,
                    altitude=0.0,
                ),
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
        template: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            side_id = self._resolve_side_id(side)
            side_color = self._side_color(side_id)
            row = (
                template
                if template is not None
                else self._find_exact_db_row(FacilityDb, "class_name", class_name)
            )
            if row is None:
                raise ValueError(
                    f"Unknown facility class: {class_name}. Add it to the unit asset database before deployment."
                )
            facility = Facility(
                id=str(uuid4()),
                name=name or f"{class_name} #{len(self.game.current_scenario.facilities) + 1}",
                side_id=side_id,
                class_name=class_name,
                latitude=latitude,
                longitude=longitude,
                altitude=0.0,
                range=self._to_float(self._row_value(row, "range"), 50.0),
                side_color=side_color,
                weapons=self._default_weapons(
                    DEFAULT_FACILITY_WEAPON_KEYS,
                    side_id,
                    side_color,
                    latitude=latitude,
                    longitude=longitude,
                    altitude=10000.0,
                ),
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
        template: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            side_id = self._resolve_side_id(side)
            side_color = self._side_color(side_id)
            row = (
                template
                if template is not None
                else self._find_exact_db_row(AirbaseDb, "name", class_name)
            )
            if row is None:
                raise ValueError(
                    f"Unknown airbase class: {class_name}. Add it to the unit asset database before deployment."
                )
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

    def deploy_obstacle(
        self,
        class_name: str,
        latitude: float,
        longitude: float,
        *,
        name: str | None = None,
        side: str | None = None,
        radius_nm: float = 15.0,
        obstacle_type: str = "no_go",
        movement_penalty: float = 1.0,
        detection_penalty: float = 0.0,
        communication_penalty: float = 0.0,
        affected_domains: list[str] | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            side_id = self._resolve_side_id(side) if side else ""
            side_color = self._side_color(side_id) if side_id else "#38bdf8"
            obstacle = Obstacle(
                id=str(uuid4()),
                name=name or class_name,
                class_name=class_name,
                side_id=side_id,
                latitude=latitude,
                longitude=longitude,
                altitude=0.0,
                radius_nm=self._to_float(radius_nm, 15.0),
                obstacle_type=obstacle_type,
                side_color=side_color,
                active=True,
                movement_penalty=self._to_float(movement_penalty, 1.0),
                detection_penalty=self._to_float(detection_penalty, 0.0),
                communication_penalty=self._to_float(communication_penalty, 0.0),
                affected_domains=affected_domains or ["aircraft", "ship"],
                description=description,
            )
            self.game.current_scenario.obstacles.append(obstacle)
            return {
                "unitType": "obstacle",
                "unitId": obstacle.id,
                "name": obstacle.name,
            }

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
            elif unit_type == "obstacle":
                self.game.current_scenario.obstacles = [
                    item for item in self.game.current_scenario.obstacles if item.id != unit_id
                ]
            else:
                raise ValueError(f"Unsupported unit type for delete: {unit_type}")
            self._remove_unit_references(unit_id)
            return {"deleted": True, "unitType": unit_type, "unitId": unit_id}

    def move_unit(
        self, unit_type: str, unit_id: str, route: list[list[float]]
    ) -> dict[str, Any]:
        with self._lock:
            unit_type = unit_type.lower().strip()
            normalized_route = self._normalize_route(route)
            if unit_type == "aircraft":
                if self.game.current_scenario.get_aircraft(unit_id) is None:
                    raise ValueError("Aircraft not found")
                self.game.move_aircraft(unit_id, normalized_route)
            elif unit_type == "ship":
                if self.game.current_scenario.get_ship(unit_id) is None:
                    raise ValueError("Ship not found")
                self.game.move_ship(unit_id, normalized_route)
            else:
                raise ValueError("move_unit only supports aircraft and ship")
            return {"moved": True, "unitType": unit_type, "unitId": unit_id}

    def set_unit_position(
        self,
        unit_type: str,
        unit_id: str,
        latitude: float,
        longitude: float,
    ) -> dict[str, Any]:
        with self._lock:
            unit = self._get_unit(unit_type, unit_id)
            if unit is None:
                raise ValueError("Unit not found")
            unit.latitude = latitude
            unit.longitude = longitude

            normalized = unit_type.lower().strip()
            if normalized in {"airbase", "ship"}:
                for aircraft in getattr(unit, "aircraft", []):
                    aircraft.latitude = latitude - 0.5
                    aircraft.longitude = longitude - 0.5
            if normalized in {"reference_point", "referencepoint"}:
                scenario = self.game.current_scenario
                for mission in scenario.missions:
                    assigned_area = getattr(mission, "assigned_area", None)
                    if not assigned_area:
                        continue
                    mission.assigned_area = [
                        unit if point.id == unit.id else point for point in assigned_area
                    ]
                    update_geometry = getattr(mission, "update_patrol_area_geometry", None)
                    if callable(update_geometry):
                        update_geometry()

            return {
                "positioned": True,
                "unitType": normalized,
                "unitId": unit_id,
                "latitude": latitude,
                "longitude": longitude,
            }

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
                aircraft.is_objective = bool(
                    patch.get("is_objective", aircraft.is_objective)
                )
                if "latitude" in patch or "longitude" in patch:
                    aircraft.latitude = self._to_float(
                        patch.get("latitude"), aircraft.latitude
                    )
                    aircraft.longitude = self._to_float(
                        patch.get("longitude"), aircraft.longitude
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
                ship.is_objective = bool(patch.get("is_objective", ship.is_objective))
                if "latitude" in patch or "longitude" in patch:
                    self.set_unit_position(
                        "ship",
                        unit_id,
                        self._to_float(patch.get("latitude"), ship.latitude),
                        self._to_float(patch.get("longitude"), ship.longitude),
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
                facility.is_objective = bool(
                    patch.get("is_objective", facility.is_objective)
                )
                if "latitude" in patch or "longitude" in patch:
                    facility.latitude = self._to_float(
                        patch.get("latitude"), facility.latitude
                    )
                    facility.longitude = self._to_float(
                        patch.get("longitude"), facility.longitude
                    )
            elif unit_type == "airbase":
                airbase = self.game.current_scenario.get_airbase(unit_id)
                if airbase is None:
                    raise ValueError("Airbase not found")
                self.game.current_scenario.update_airbase(
                    airbase_id=unit_id,
                    airbase_name=str(patch.get("name", airbase.name)),
                )
                airbase.is_objective = bool(
                    patch.get("is_objective", airbase.is_objective)
                )
                if "latitude" in patch or "longitude" in patch:
                    self.set_unit_position(
                        "airbase",
                        unit_id,
                        self._to_float(patch.get("latitude"), airbase.latitude),
                        self._to_float(patch.get("longitude"), airbase.longitude),
                    )
            elif unit_type in {"reference_point", "referencepoint"}:
                point = self.game.current_scenario.get_reference_point(unit_id)
                if point is None:
                    raise ValueError("Reference point not found")
                self.game.current_scenario.update_reference_point(
                    reference_point_id=unit_id,
                    reference_point_name=str(patch.get("name", point.name)),
                )
                if "latitude" in patch or "longitude" in patch:
                    self.set_unit_position(
                        "reference_point",
                        unit_id,
                        self._to_float(patch.get("latitude"), point.latitude),
                        self._to_float(patch.get("longitude"), point.longitude),
                    )
            elif unit_type == "obstacle":
                obstacle = self.game.current_scenario.get_obstacle(unit_id)
                if obstacle is None:
                    raise ValueError("Obstacle not found")
                obstacle.name = str(patch.get("name", obstacle.name))
                obstacle.class_name = str(
                    patch.get("class_name", patch.get("className", obstacle.class_name))
                )
                obstacle.obstacle_type = str(
                    patch.get(
                        "obstacle_type",
                        patch.get("obstacleType", obstacle.obstacle_type),
                    )
                )
                obstacle.radius_nm = self._to_float(
                    patch.get("radius_nm", patch.get("radiusNm")), obstacle.radius_nm
                )
                obstacle.movement_penalty = self._to_float(
                    patch.get("movement_penalty", patch.get("movementPenalty")),
                    obstacle.movement_penalty,
                )
                obstacle.detection_penalty = self._to_float(
                    patch.get("detection_penalty", patch.get("detectionPenalty")),
                    obstacle.detection_penalty,
                )
                obstacle.communication_penalty = self._to_float(
                    patch.get(
                        "communication_penalty",
                        patch.get("communicationPenalty"),
                    ),
                    obstacle.communication_penalty,
                )
                if "active" in patch:
                    obstacle.active = bool(patch["active"])
                if "description" in patch:
                    obstacle.description = str(patch.get("description") or "")
                if "affected_domains" in patch or "affectedDomains" in patch:
                    raw_domains = patch.get("affected_domains", patch.get("affectedDomains"))
                    if isinstance(raw_domains, list):
                        obstacle.affected_domains = [str(item) for item in raw_domains]
                if "latitude" in patch or "longitude" in patch:
                    obstacle.latitude = self._to_float(
                        patch.get("latitude"), obstacle.latitude
                    )
                    obstacle.longitude = self._to_float(
                        patch.get("longitude"), obstacle.longitude
                    )
            else:
                raise ValueError(f"Unsupported unit type for update: {unit_type}")
            return {"updated": True, "unitType": unit_type, "unitId": unit_id}

    def set_current_side(self, side: str) -> dict[str, Any]:
        with self._lock:
            side_id = self._resolve_side_id(side)
            self.game.current_side_id = side_id
            return {"currentSideId": side_id}

    def add_side(
        self,
        name: str,
        color: str = "blue",
        hostiles: list[str] | None = None,
        allies: list[str] | None = None,
        doctrine: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            scenario = self.game.current_scenario
            side = Side(id=str(uuid4()), name=name, color=color)
            scenario.sides.append(side)
            hostiles = self._unique_side_refs(hostiles, side.id)
            allies = [
                item
                for item in self._unique_side_refs(allies, side.id)
                if item not in hostiles
            ]
            scenario.relationships.update_relationship(side.id, hostiles, allies)
            scenario.update_side_doctrine(
                side.id, doctrine or scenario.get_default_side_doctrine()
            )
            self.game.current_side_id = side.id
            return {"sideId": side.id, "name": side.name}

    def update_side(
        self,
        side_id: str,
        name: str,
        color: str,
        hostiles: list[str] | None = None,
        allies: list[str] | None = None,
        doctrine: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            scenario = self.game.current_scenario
            side = scenario.get_side(side_id)
            if side is None:
                raise ValueError("Side not found")
            side.name = name
            side.color = color
            self._sync_side_color(side_id, color)
            next_hostiles = self._unique_side_refs(hostiles, side_id)
            next_allies = [
                item
                for item in self._unique_side_refs(allies, side_id)
                if item not in next_hostiles
            ]
            scenario.relationships.update_relationship(
                side_id, next_hostiles, next_allies
            )
            scenario.update_side_doctrine(side_id, doctrine or {})
            return {"sideId": side.id, "name": side.name}

    def delete_side(self, side_id: str) -> dict[str, Any]:
        with self._lock:
            scenario = self.game.current_scenario
            if scenario.get_side(side_id) is None:
                raise ValueError("Side not found")
            scenario.sides = [side for side in scenario.sides if side.id != side_id]
            scenario.aircraft = [
                aircraft for aircraft in scenario.aircraft if aircraft.side_id != side_id
            ]
            scenario.airbases = [
                airbase for airbase in scenario.airbases if airbase.side_id != side_id
            ]
            scenario.facilities = [
                facility for facility in scenario.facilities if facility.side_id != side_id
            ]
            scenario.ships = [ship for ship in scenario.ships if ship.side_id != side_id]
            scenario.missions = [
                mission for mission in scenario.missions if mission.side_id != side_id
            ]
            scenario.weapons = [
                weapon for weapon in scenario.weapons if weapon.side_id != side_id
            ]
            scenario.reference_points = [
                point for point in scenario.reference_points if point.side_id != side_id
            ]
            scenario.obstacles = [
                obstacle
                for obstacle in scenario.obstacles
                if getattr(obstacle, "side_id", "") != side_id
            ]
            scenario.relationships.delete_side(side_id)
            scenario.remove_side_doctrine(side_id)
            if self.game.current_side_id == side_id:
                self.game.current_side_id = scenario.sides[0].id if scenario.sides else ""
            return {"deleted": True, "sideId": side_id}

    def delete_mission(self, mission_id: str) -> dict[str, Any]:
        with self._lock:
            before = len(self.game.current_scenario.missions)
            self.game.delete_mission(mission_id)
            return {
                "deleted": len(self.game.current_scenario.missions) < before,
                "missionId": mission_id,
            }

    def create_patrol_mission(
        self,
        name: str,
        assigned_unit_ids: list[str],
        reference_point_ids: list[str],
    ) -> dict[str, Any]:
        with self._lock:
            scenario = self.game.current_scenario
            area = [
                point
                for point_id in reference_point_ids
                if (point := scenario.get_reference_point(point_id)) is not None
            ]
            before = len(scenario.missions)
            self.game.create_patrol_mission(name, assigned_unit_ids, area)
            mission = scenario.missions[-1] if len(scenario.missions) > before else None
            return {
                "created": mission is not None,
                "missionId": getattr(mission, "id", ""),
                "type": "patrol",
            }

    def update_patrol_mission(
        self,
        mission_id: str,
        name: str,
        assigned_unit_ids: list[str],
        reference_point_ids: list[str],
    ) -> dict[str, Any]:
        with self._lock:
            scenario = self.game.current_scenario
            if scenario.get_patrol_mission(mission_id) is None:
                raise ValueError("Patrol mission not found")
            area = [
                point
                for point_id in reference_point_ids
                if (point := scenario.get_reference_point(point_id)) is not None
            ]
            self.game.update_patrol_mission(
                mission_id,
                name,
                assigned_unit_ids,
                area,
            )
            return {"updated": True, "missionId": mission_id, "type": "patrol"}

    def create_strike_mission(
        self,
        name: str,
        assigned_unit_ids: list[str],
        assigned_target_ids: list[str],
    ) -> dict[str, Any]:
        with self._lock:
            scenario = self.game.current_scenario
            before = len(scenario.missions)
            self.game.create_strike_mission(
                name,
                assigned_unit_ids,
                assigned_target_ids,
            )
            mission = scenario.missions[-1] if len(scenario.missions) > before else None
            return {
                "created": mission is not None,
                "missionId": getattr(mission, "id", ""),
                "type": "strike",
            }

    def update_strike_mission(
        self,
        mission_id: str,
        name: str,
        assigned_unit_ids: list[str],
        assigned_target_ids: list[str],
    ) -> dict[str, Any]:
        with self._lock:
            if self.game.current_scenario.get_strike_mission(mission_id) is None:
                raise ValueError("Strike mission not found")
            self.game.update_strike_mission(
                mission_id,
                name,
                assigned_unit_ids,
                assigned_target_ids,
            )
            return {"updated": True, "missionId": mission_id, "type": "strike"}

    def add_weapon_to_unit(
        self,
        unit_type: str,
        unit_id: str,
        class_name: str,
        speed: float,
        max_fuel: float,
        fuel_rate: float,
        range_nm: float,
        lethality: float,
        quantity: int = 1,
    ) -> dict[str, Any]:
        with self._lock:
            unit = self._get_unit(unit_type, unit_id)
            if unit is None or not hasattr(unit, "weapons"):
                raise ValueError("Weapon carrier not found")
            for weapon in unit.weapons:
                if weapon.class_name == class_name:
                    return {
                        "added": False,
                        "reason": "duplicate_weapon",
                        "unitType": unit_type,
                        "unitId": unit_id,
                        "weaponId": weapon.id,
                    }
            weapon = self._make_weapon(
                class_name,
                quantity,
                unit.side_id,
                unit.side_color,
                latitude=unit.latitude,
                longitude=unit.longitude,
                altitude=getattr(unit, "altitude", 10000.0) or 10000.0,
            )
            unit.weapons.append(weapon)
            return {
                "added": True,
                "unitType": unit_type,
                "unitId": unit_id,
                "weaponId": weapon.id,
            }

    def delete_weapon_from_unit(
        self,
        unit_type: str,
        unit_id: str,
        weapon_id: str,
    ) -> dict[str, Any]:
        with self._lock:
            unit = self._get_unit(unit_type, unit_id)
            if unit is None or not hasattr(unit, "weapons"):
                raise ValueError("Weapon carrier not found")
            before = len(unit.weapons)
            unit.weapons = [weapon for weapon in unit.weapons if weapon.id != weapon_id]
            return {
                "deleted": len(unit.weapons) < before,
                "unitType": unit_type,
                "unitId": unit_id,
                "weaponId": weapon_id,
            }

    def update_weapon_quantity(
        self,
        unit_type: str,
        unit_id: str,
        weapon_id: str,
        increment: int,
    ) -> dict[str, Any]:
        with self._lock:
            unit = self._get_unit(unit_type, unit_id)
            if unit is None or not hasattr(unit, "weapons"):
                raise ValueError("Weapon carrier not found")
            for weapon in unit.weapons:
                if weapon.id != weapon_id:
                    continue
                weapon.current_quantity = max(
                    0,
                    min(weapon.max_quantity, weapon.current_quantity + increment),
                )
                return {
                    "updated": True,
                    "unitType": unit_type,
                    "unitId": unit_id,
                    "weaponId": weapon_id,
                    "currentQuantity": weapon.current_quantity,
                }
            raise ValueError("Weapon not found")

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
            if layer_name == "obstacles":
                if operation == "add":
                    return self.deploy_obstacle(
                        class_name=str(payload.get("class_name", payload.get("className", "No-go zone"))),
                        name=str(payload.get("name", payload.get("class_name", "No-go zone"))),
                        latitude=self._to_float(payload.get("latitude"), 0.0),
                        longitude=self._to_float(payload.get("longitude"), 0.0),
                        side=payload.get("side"),
                        radius_nm=self._to_float(
                            payload.get("radius_nm", payload.get("radiusNm")), 15.0
                        ),
                        obstacle_type=str(
                            payload.get("obstacle_type", payload.get("obstacleType", "no_go"))
                        ),
                        movement_penalty=self._to_float(
                            payload.get("movement_penalty", payload.get("movementPenalty")),
                            1.0,
                        ),
                        detection_penalty=self._to_float(
                            payload.get("detection_penalty", payload.get("detectionPenalty")),
                            0.0,
                        ),
                        communication_penalty=self._to_float(
                            payload.get(
                                "communication_penalty",
                                payload.get("communicationPenalty"),
                            ),
                            0.0,
                        ),
                    )
                if operation == "remove":
                    return self.delete_unit(
                        unit_type="obstacle",
                        unit_id=str(payload.get("id", "")),
                    )
            return {"layer": layer_name, "operation": operation, "payload": payload}

    def get_exported_scenario(self) -> dict[str, Any]:
        with self._lock:
            return self.game.export_scenario()
