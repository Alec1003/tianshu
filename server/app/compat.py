from __future__ import annotations

import os
from collections.abc import Iterable

CURRENT_ENV_PREFIX = "TIANSHU_"
LEGACY_ENV_PREFIX = "AI" + "CC_"


def legacy_env_name(name: str) -> str:
    if name.startswith(CURRENT_ENV_PREFIX):
        return LEGACY_ENV_PREFIX + name[len(CURRENT_ENV_PREFIX) :]
    return LEGACY_ENV_PREFIX + name


def get_env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is not None:
        return value
    return os.environ.get(legacy_env_name(name), default)


def install_legacy_env_aliases(names: Iterable[str]) -> None:
    for name in names:
        if name in os.environ:
            continue
        legacy_name = legacy_env_name(name)
        legacy_value = os.environ.get(legacy_name)
        if legacy_value is not None:
            os.environ[name] = legacy_value
