"""Doctrine 默认值与 scenario JSON 规范化。

抽到独立模块的原因：
1. ``runtime.py`` 顶层会 import ``blade.Game``（依赖 gymnasium 等重型库），
   测试场景下不便加载；本模块只处理 dict / json，无重依赖。
2. 客户端 ``Scenario`` 构造函数对 ``doctrine`` 字段的判定是
   ``parameters.doctrine ?? getDefaultDoctrine()``——空 ``{}`` 是 truthy
   不会走默认，必须 server 端给到非空且按 sides 索引的 doctrine 字典，
   否则 ``checkSideDoctrine`` 全部判 false，红蓝静止不交战。

新增字符串必须与 ``client/src/game/Doctrine.ts`` 的 ``DoctrineType`` 严格
一致（区分大小写）。
"""

from __future__ import annotations

import json
from typing import Any


_DEFAULT_SIDE_DOCTRINE: dict[str, bool] = {
    "Aircraft attack hostile aircraft": True,
    "Aircraft chase hostile aircraft": True,
    "Aircraft RTB when out of range of homebase": False,
    "Aircraft RTB when strike mission complete": False,
    "SAMs attack hostile aircraft": True,
    "Ships attack hostile aircraft": True,
}


def default_doctrine_for_sides(sides: Any) -> dict[str, dict[str, bool]]:
    """按 sides 列表给每个 side 生成一份默认条令。

    sides 必须形如 ``[{"id": "...", "name": "...", ...}, ...]``；
    任何不符合的元素都会被忽略而不会抛错（保持容错以匹配前端宽松解析）。
    """

    out: dict[str, dict[str, bool]] = {}
    if not isinstance(sides, list):
        return out
    for side in sides:
        if not isinstance(side, dict):
            continue
        side_id = side.get("id")
        if isinstance(side_id, str) and side_id:
            out[side_id] = dict(_DEFAULT_SIDE_DOCTRINE)
    return out


def normalize_scenario_payload(scenario_json: str) -> str:
    """前端期望 ``currentScenario.doctrine`` 是按 sideId 索引的非空字典。

    缺字段 / 不是 dict / 是空 ``{}`` 三种情况都按 sides 回填默认条令；
    已存在且非空时保持不变（用户自定义优先）。

    JSON 不合法 / payload 不是 dict 时返回原串，保持调用方语义稳定。
    """

    try:
        payload = json.loads(scenario_json)
    except json.JSONDecodeError:
        return scenario_json

    if not isinstance(payload, dict):
        return scenario_json

    current = payload.get("currentScenario")
    if not isinstance(current, dict):
        return json.dumps(payload)

    existing = current.get("doctrine")
    needs_default = (
        "doctrine" not in current
        or not isinstance(existing, dict)
        or len(existing) == 0
    )
    if needs_default:
        current["doctrine"] = default_doctrine_for_sides(current.get("sides"))

    return json.dumps(payload)
