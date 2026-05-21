"""Regression：``app.aicc_runtime._doctrine.normalize_scenario_payload``。

前史 bug：缺 ``doctrine`` 字段时回填空 ``{}``，导致前端 ``Scenario`` 构造
``parameters.doctrine ?? getDefaultDoctrine()`` 不触发（``{}`` truthy），
``checkSideDoctrine`` 全 false，红蓝静止不交战。本测试锁定按 sides 生成
全开默认条令的语义。

只 import 纯函数模块，不引导 AICCRuntime（避免 blade/gymnasium 依赖）。
"""

from __future__ import annotations

import json

from app.aicc_runtime._doctrine import (
    _DEFAULT_SIDE_DOCTRINE,
    default_doctrine_for_sides,
    normalize_scenario_payload,
)


SIDES = [
    {"id": "blue-1", "name": "BLUE", "color": "blue"},
    {"id": "red-1", "name": "RED", "color": "red"},
]


def _scenario(**extra: object) -> str:
    current: dict[str, object] = {
        "id": "s1",
        "name": "Test",
        "sides": SIDES,
    }
    current.update(extra)
    return json.dumps({"currentScenario": current})


def test_backfills_default_doctrine_when_field_missing() -> None:
    out = json.loads(normalize_scenario_payload(_scenario()))
    doctrine = out["currentScenario"]["doctrine"]

    assert set(doctrine.keys()) == {"blue-1", "red-1"}
    for side_id in ("blue-1", "red-1"):
        assert doctrine[side_id] == _DEFAULT_SIDE_DOCTRINE


def test_backfills_default_doctrine_when_field_empty_dict() -> None:
    out = json.loads(normalize_scenario_payload(_scenario(doctrine={})))
    doctrine = out["currentScenario"]["doctrine"]

    assert set(doctrine.keys()) == {"blue-1", "red-1"}
    assert doctrine["blue-1"]["Aircraft attack hostile aircraft"] is True
    assert doctrine["blue-1"]["SAMs attack hostile aircraft"] is True
    assert doctrine["blue-1"]["Ships attack hostile aircraft"] is True


def test_backfills_default_doctrine_when_field_not_dict() -> None:
    out = json.loads(normalize_scenario_payload(_scenario(doctrine="oops")))
    doctrine = out["currentScenario"]["doctrine"]

    assert set(doctrine.keys()) == {"blue-1", "red-1"}


def test_preserves_existing_non_empty_doctrine() -> None:
    custom = {
        "blue-1": dict(_DEFAULT_SIDE_DOCTRINE),
    }
    custom["blue-1"]["Aircraft attack hostile aircraft"] = False
    out = json.loads(normalize_scenario_payload(_scenario(doctrine=custom)))

    assert out["currentScenario"]["doctrine"] == custom


def test_default_doctrine_keys_match_client_doctrine_type() -> None:
    """枚举字符串必须与 client/src/game/Doctrine.ts DoctrineType 严格一致。"""
    expected = {
        "Aircraft attack hostile aircraft",
        "Aircraft chase hostile aircraft",
        "Aircraft RTB when out of range of homebase",
        "Aircraft RTB when strike mission complete",
        "SAMs attack hostile aircraft",
        "Ships attack hostile aircraft",
    }
    assert set(_DEFAULT_SIDE_DOCTRINE.keys()) == expected


def test_default_doctrine_engagement_flags_all_enabled_by_default() -> None:
    assert _DEFAULT_SIDE_DOCTRINE["Aircraft attack hostile aircraft"] is True
    assert _DEFAULT_SIDE_DOCTRINE["Aircraft chase hostile aircraft"] is True
    assert _DEFAULT_SIDE_DOCTRINE["SAMs attack hostile aircraft"] is True
    assert _DEFAULT_SIDE_DOCTRINE["Ships attack hostile aircraft"] is True


def test_helper_returns_empty_when_sides_not_a_list() -> None:
    assert default_doctrine_for_sides(None) == {}
    assert default_doctrine_for_sides("blue") == {}
    assert default_doctrine_for_sides({"id": "x"}) == {}


def test_invalid_json_returned_unchanged() -> None:
    assert normalize_scenario_payload("not json") == "not json"


def test_payload_without_currentScenario_unchanged_keys() -> None:
    raw = json.dumps({"foo": "bar"})
    out = json.loads(normalize_scenario_payload(raw))
    assert "doctrine" not in out
    assert out == {"foo": "bar"}
