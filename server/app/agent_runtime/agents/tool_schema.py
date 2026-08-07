from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)

ToolCallSource = Literal["native", "json"]


@dataclass
class ToolCall:
    """Unified internal tool-call representation."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str = ""
    source: ToolCallSource = "native"

    @classmethod
    def from_openai(cls, tool_call: dict[str, Any]) -> "ToolCall":
        fn = tool_call.get("function", {})
        return cls(
            name=str(fn.get("name", "")),
            arguments=_safe_json_parse(fn.get("arguments", "{}")),
            call_id=str(tool_call.get("id", "")),
            source="native",
        )


def _safe_json_parse(text: str) -> dict[str, Any]:
    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


# ------------------------------------------------------------------
# JSON tool patterns
# ------------------------------------------------------------------

_JSON_TOOL_KEY_PATTERNS: list[tuple[str, str]] = [
    # (tool_name_key, arguments_key)
    ("tool", "arguments"),
    ("tool_name", "arguments"),
    ("tool_name", "parameters"),
    ("tool_name", "args"),
    ("name", "arguments"),
    ("name", "args"),
    ("function", "arguments"),
    ("function", "args"),
]


def _extract_json_tool_calls(text: str) -> list[ToolCall]:
    """Extract tool calls from LLM text using JSON parsing."""
    stripped = text.strip()

    # 1) Full-text JSON parse
    try:
        obj = json.loads(stripped)
        tc = _json_dict_to_tool_call(obj)
        if tc is not None:
            return [tc]
    except json.JSONDecodeError:
        pass

    # 2) Regex extraction
    _JSON_RE = re.compile(
        r'\{\s*"(?:tool|tool_name|name|function)"\s*:\s*"[^"]+"\s*[,}].*?\}',
        re.DOTALL,
    )
    results: list[ToolCall] = []
    for match in _JSON_RE.finditer(text):
        try:
            obj = json.loads(match.group())
            tc = _json_dict_to_tool_call(obj)
            if tc is not None:
                results.append(tc)
        except json.JSONDecodeError:
            continue

    if results:
        return results

    # 3) Line-by-line fallback
    for line in text.split("\n"):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
            tc = _json_dict_to_tool_call(obj)
            if tc is not None:
                results.append(tc)
        except json.JSONDecodeError:
            continue

    return results


def _json_dict_to_tool_call(obj: dict[str, Any]) -> ToolCall | None:
    if not isinstance(obj, dict):
        return None
    for name_key, args_key in _JSON_TOOL_KEY_PATTERNS:
        name = obj.get(name_key)
        args = obj.get(args_key)
        if isinstance(name, str) and name.strip():
            if isinstance(args, dict):
                return ToolCall(
                    name=name.strip(),
                    arguments=args,
                    call_id="",
                    source="json",
                )
    # No valid (name, args-dict) pair found
    return None


# ------------------------------------------------------------------
# OpenAI native tool_calls extraction
# ------------------------------------------------------------------


def _extract_native_tool_calls(
    raw_tool_calls: list[dict[str, Any]],
) -> list[ToolCall]:
    results: list[ToolCall] = []
    for tc in raw_tool_calls:
        fn = tc.get("function", {})
        name = str(fn.get("name", ""))
        if not name.strip():
            continue
        results.append(ToolCall.from_openai(tc))
    return results


# ------------------------------------------------------------------
# Unified normalizer entry
# ------------------------------------------------------------------


class ToolCallNormalizer:
    """Unified entry point for extracting ToolCall objects from any source.

    Priority:
    1. OpenAI native tool_calls (already structured)
    2. JSON tool extraction from text
    """

    @staticmethod
    def from_native(
        tool_calls: list[dict[str, Any]] | None,
    ) -> list[ToolCall]:
        if not tool_calls:
            return []
        return _extract_native_tool_calls(tool_calls)

    @staticmethod
    def from_text(text: str) -> list[ToolCall]:
        if not text or not text.strip():
            return []
        return _extract_json_tool_calls(text)

    @staticmethod
    def from_response(
        tool_calls: list[dict[str, Any]] | None,
        text: str | None,
    ) -> list[ToolCall]:
        # Native first
        native = ToolCallNormalizer.from_native(tool_calls)
        if native:
            return native
        # JSON text fallback
        return ToolCallNormalizer.from_text(text or "")


__all__ = [
    "ToolCall",
    "ToolCallNormalizer",
    "ToolCallSource",
    "_extract_json_tool_calls",
]
