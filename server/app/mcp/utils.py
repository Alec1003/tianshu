"""Scenario data inspection helpers used by MCP tools/resources.

前端把整个工作区 JSON（含 ``currentScenario``、``currentSideId``、
``mapView``）作为 ``Scenario.data`` 存进 DB。MCP tools 需要从这个 dict
中读取战场 entities，因此这里集中提供："给一个 scenario.data dict，
帮我拿到 sides/units/missions/threats"。

为什么独立成文件：保持 ``server.py`` 只关心 FastMCP 装饰器编排，业务
判断（"unit 属于哪个 side"、"什么算威胁"）独立可测。
"""

from __future__ import annotations

from typing import Any, Iterable, Literal

UnitType = Literal[
    "aircraft",
    "ship",
    "facility",
    "airbase",
    "weapon",
    "referencePoint",
    "obstacle",
]
UNIT_TYPES: tuple[UnitType, ...] = (
    "aircraft",
    "ship",
    "facility",
    "airbase",
    "weapon",
    "referencePoint",
    "obstacle",
)

# Frontend ``Scenario.ts`` 使用的 JSON 键名。aircraft 是不可数名词（直接复
# 数仍是 aircraft），所以不能用 ``f"{ut}s"`` 通用化，必须硬编码。
_BUCKET_KEY: dict[UnitType, str] = {
    "aircraft": "aircraft",
    "ship": "ships",
    "facility": "facilities",
    "airbase": "airbases",
    "weapon": "weapons",
    "referencePoint": "referencePoints",
    "obstacle": "obstacles",
}


def get_current_scenario(data: dict[str, Any]) -> dict[str, Any]:
    """Return the inner ``currentScenario`` dict.

    Frontend exports may either dump ``{ currentScenario, currentSideId, ...}``
    (most common, see ``blank_scenario.json``) or just the scenario itself
    (advanced manual dump). We accept both shapes so MCP tools survive both.
    """
    if not isinstance(data, dict):
        return {}
    inner = data.get("currentScenario")
    if isinstance(inner, dict):
        return inner
    # Treat the top-level dict as the scenario if it has scenario-shaped keys.
    if any(k in data for k in ("sides", "aircraft", "ships", "facilities")):
        return data
    return {}


def get_sides(data: dict[str, Any]) -> list[dict[str, Any]]:
    sides = get_current_scenario(data).get("sides", [])
    return [s for s in sides if isinstance(s, dict)]


def iter_units(
    data: dict[str, Any],
    *,
    types: Iterable[UnitType] | None = None,
) -> list[dict[str, Any]]:
    """Flatten aircraft/ship/facility/airbase/weapon/referencePoint/obstacle into one
    list, each item gets an injected ``_unit_type`` for downstream filtering."""
    scenario = get_current_scenario(data)
    wanted = tuple(types) if types else UNIT_TYPES
    out: list[dict[str, Any]] = []
    for ut in wanted:
        key = _BUCKET_KEY.get(ut)
        if key is None:
            continue
        bucket = scenario.get(key, [])
        if not isinstance(bucket, list):
            continue
        for u in bucket:
            if not isinstance(u, dict):
                continue
            row = dict(u)
            row["_unit_type"] = ut
            out.append(row)
    return out


def find_unit(data: dict[str, Any], unit_id: str) -> dict[str, Any] | None:
    for u in iter_units(data):
        if u.get("id") == unit_id:
            return u
    return None


def get_side(data: dict[str, Any], side_id: str) -> dict[str, Any] | None:
    for s in get_sides(data):
        if s.get("id") == side_id:
            return s
    return None


def hostile_side_ids(data: dict[str, Any], side_id: str) -> set[str]:
    """Side ids the given side considers hostile, per ``relationships``."""
    rel = get_current_scenario(data).get("relationships", {})
    if not isinstance(rel, dict):
        return set()
    hostiles = rel.get("hostiles", {})
    if not isinstance(hostiles, dict):
        return set()
    raw = hostiles.get(side_id, [])
    return {x for x in raw if isinstance(x, str)}


def unit_brief(unit: dict[str, Any]) -> dict[str, Any]:
    """Strip a unit to the LLM-relevant projection.

    We keep this lean (no weapons inventory, no doctrine) so that
    ``list_units`` responses don't blow up the model context. Detailed view
    goes through ``get_unit_detail``.
    """
    return {
        "id": unit.get("id"),
        "name": unit.get("name"),
        "type": unit.get("_unit_type"),
        "side_id": unit.get("sideId"),
        "class_name": unit.get("className"),
        "latitude": unit.get("latitude"),
        "longitude": unit.get("longitude"),
        "altitude": unit.get("altitude"),
        "heading": unit.get("heading"),
        "speed": unit.get("speed"),
        "current_fuel": unit.get("currentFuel"),
        "max_fuel": unit.get("maxFuel"),
        "is_objective": unit.get("isObjective"),
    }
