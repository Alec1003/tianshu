from __future__ import annotations

import re
from typing import Any, Iterable

AIRCRAFT_CLASS_ALIASES: dict[str, str] = {
    "f16": "F-16C",
    "f22": "F-22 Raptor",
}

SIDE_REFERENCE_ALIASES: dict[str, set[str]] = {
    "blue": {"blue", "bluefor", "blufor", "蓝方", "蓝军", "友军"},
    "red": {"red", "redfor", "opfor", "红方", "红军"},
    "ally": {"ally", "allied", "friendly", "green", "友方", "盟友", "绿方"},
}

SIDE_COLOR_ALIASES: dict[str, set[str]] = {
    "blue": {"blue", "skyblue", "darkblue", "dodgerblue"},
    "red": {"red", "darkred", "orangered", "crimson"},
    "ally": {"green", "darkgreen", "forestgreen", "limegreen", "olive"},
}

_SEPARATOR_RE = re.compile(r"[\s_\-]+")


def normalize_lookup_token(value: str) -> str:
    return _SEPARATOR_RE.sub("", value.strip()).casefold()


def canonical_aircraft_class_name(class_name: str) -> str:
    normalized = normalize_lookup_token(class_name)
    return AIRCRAFT_CLASS_ALIASES.get(normalized, class_name.strip())


def resolve_side_id(sides: Iterable[Any], side_ref: str | None) -> str | None:
    if not side_ref or not str(side_ref).strip():
        return None

    reference_tokens = _side_reference_tokens(str(side_ref))
    for side in sides:
        if _side_descriptor_tokens(side) & reference_tokens:
            return str(side.id)
    return None


def _side_reference_tokens(side_ref: str) -> set[str]:
    normalized = normalize_lookup_token(side_ref)
    tokens = {normalized}
    for canonical, aliases in SIDE_REFERENCE_ALIASES.items():
        if normalized == canonical or normalized in _normalized_values(aliases):
            tokens.add(canonical)
    return tokens


def _side_descriptor_tokens(side: Any) -> set[str]:
    raw_tokens = {
        _normalize_optional(getattr(side, "id", None)),
        _normalize_optional(getattr(side, "name", None)),
        _normalize_optional(getattr(getattr(side, "color", None), "value", None)),
        _normalize_optional(getattr(side, "color", None)),
    }
    tokens = {token for token in raw_tokens if token}
    for canonical, aliases in SIDE_REFERENCE_ALIASES.items():
        normalized_aliases = _normalized_values(aliases)
        if canonical in tokens or tokens & normalized_aliases:
            tokens.add(canonical)
    for canonical, aliases in SIDE_COLOR_ALIASES.items():
        if tokens & _normalized_values(aliases):
            tokens.add(canonical)
    return tokens


def _normalize_optional(value: Any) -> str:
    if value is None:
        return ""
    return normalize_lookup_token(str(value))


def _normalized_values(values: Iterable[str]) -> set[str]:
    return {normalize_lookup_token(value) for value in values}
