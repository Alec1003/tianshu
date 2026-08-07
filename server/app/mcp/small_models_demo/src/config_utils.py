"""Deep merge utility — recursively merges src dict into dest dict.

Values in src overwrite dest at leaf nodes. Lists are replaced, not merged.
"""

from __future__ import annotations

from typing import Any


def deep_merge(dest: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge src into dest. Returns a new dict.

    - Nested dicts are merged recursively
    - Lists and scalars are overwritten by src
    - Keys only in src are added
    - Keys only in dest are preserved
    """
    result = dict(dest)
    for key, value in src.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result
