"""共享工具：deep_merge 和默认配置加载."""

from __future__ import annotations

from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent.parent

_WTA_DEFAULTS_PATH = BASE_DIR / "src" / "wta" / "input" / "_defaults.yaml"
_ROUTE_DEFAULTS_PATH = BASE_DIR / "src" / "route_plan" / "input" / "_defaults.yaml"

import yaml as _yaml

WTA_DEFAULTS = (
    _yaml.safe_load(_WTA_DEFAULTS_PATH.read_text(encoding="utf-8"))
    if _WTA_DEFAULTS_PATH.exists()
    else {}
)
ROUTE_DEFAULTS = (
    _yaml.safe_load(_ROUTE_DEFAULTS_PATH.read_text(encoding="utf-8"))
    if _ROUTE_DEFAULTS_PATH.exists()
    else {}
)


def deep_merge(dest: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
    result = dict(dest)
    for key, value in src.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result
