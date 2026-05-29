"""AI-assisted unit asset generation.

The endpoint using this module is intentionally non-persistent: it only
suggests a unit payload. Users still review and save through the normal unit
asset CRUD path.
"""

from __future__ import annotations

import asyncio
import json
import re
import urllib.error
import urllib.request
from typing import Any, Literal

from app.security.url_guard import UnsafeBaseUrlError, normalize_and_validate_base_url
from app.unit_assets.schemas import UnitAssetType
from app.unit_assets.service import normalize_asset_data

_OPENAI_COMPAT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "openai-responses": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "glm": "https://open.bigmodel.cn/api/paas/v4",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "minimax": "https://api.minimax.chat/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai",
    "ollama": "http://localhost:11434/v1",
}

_NO_API_KEY_PROVIDERS = {"ollama", "custom"}


def _asset_display_name(asset_type: UnitAssetType, query: str) -> str:
    normalized = " ".join(query.strip().split())
    if not normalized:
        return {
            "aircraft": "AI Generated Aircraft",
            "ship": "AI Generated Ship",
            "facility": "AI Generated Facility",
            "airbase": "AI Generated Airbase",
            "weapon": "AI Generated Weapon",
        }[asset_type]
    return normalized[:160]


def _with_aircraft_units(data: dict[str, Any], source: str) -> dict[str, Any]:
    data.setdefault(
        "dataSource",
        {
            "speedSrc": source,
            "maxFuelSrc": source,
            "fuelRateSrc": source,
            "rangeSrc": source,
        },
    )
    data.setdefault(
        "units",
        {
            "speedUnit": "kts",
            "maxFuelUnit": "kg",
            "fuelRateUnit": "kg/h",
            "rangeUnit": "nm",
            "jammingRangeUnit": "nm",
        },
    )
    return data


def estimate_unit_asset(
    asset_type: UnitAssetType,
    query: str,
) -> tuple[dict[str, Any], float, list[str]]:
    name = _asset_display_name(asset_type, query)
    text = query.lower()
    source = "AI estimate; verify before operational use"
    warnings = ["AI 估算值仅用于快速建模，请在保存前按公开资料或机构数据复核。"]

    if asset_type == "aircraft":
        data: dict[str, Any] = {
            "className": name,
            "speed": 900,
            "maxFuel": 12000,
            "fuelRate": 3200,
            "range": 900,
            "isTanker": False,
            "fuelOffloadCapacity": 0,
            "fuelTransferRate": 0,
            "refuelRange": 0,
            "isElectronicWarfare": False,
            "jammingRange": 0,
            "jammingStrength": 0,
            "jammingModes": [],
            "communicationDisruption": 0,
        }
        if any(token in text for token in ["kc-", "tanker", "加油", "mrt", "il-78", "y-20u"]):
            data.update(
                {
                    "speed": 460,
                    "maxFuel": 90000,
                    "fuelRate": 6200,
                    "range": 4200,
                    "isTanker": True,
                    "fuelOffloadCapacity": 45000,
                    "fuelTransferRate": 1200,
                    "refuelRange": 1500,
                }
            )
        elif any(
            token in text
            for token in [
                "electronic warfare",
                "electronic attack",
                "ewar",
                "jammer",
                "jamming",
                "growler",
                "prowler",
                "raven",
                "ea-18",
                "ef-111",
                "电子战",
                "电子支援",
                "电子攻击",
                "干扰",
            ]
        ):
            data.update(
                {
                    "speed": 850,
                    "maxFuel": 16000,
                    "fuelRate": 5200,
                    "range": 900,
                    "isElectronicWarfare": True,
                    "jammingRange": 150,
                    "jammingStrength": 0.5,
                    "jammingModes": ["radar", "communications"],
                    "communicationDisruption": 0.3,
                }
            )
        elif any(token in text for token in ["b-2", "b-52", "b-1", "h-6", "轰炸"]):
            data.update({"speed": 520, "maxFuel": 135000, "fuelRate": 8200, "range": 4500})
        elif any(token in text for token in ["e-2", "e-3", "预警", "awacs", "kj-"]):
            data.update({"speed": 460, "maxFuel": 60000, "fuelRate": 5200, "range": 3200})
        elif any(token in text for token in ["f-22", "f-35", "j-20", "su-57", "五代"]):
            data.update({"speed": 1100, "maxFuel": 18000, "fuelRate": 4800, "range": 1200})
        return _with_aircraft_units(data, source), 0.58, warnings

    if asset_type == "ship":
        data = {
            "className": name,
            "speed": 28,
            "maxFuel": 600000,
            "fuelRate": 4800,
            "range": 4200,
            "dataSource": {
                "speedSrc": source,
                "maxFuelSrc": source,
                "fuelRateSrc": source,
                "rangeSrc": source,
            },
            "units": {
                "speedUnit": "kts",
                "maxFuelUnit": "kg",
                "fuelRateUnit": "kg/h",
                "rangeUnit": "nm",
            },
        }
        if any(token in text for token in ["carrier", "航母", "aircraft carrier"]):
            data.update({"speed": 30, "maxFuel": 8000000, "fuelRate": 45000, "range": 8000})
        elif any(token in text for token in ["destroyer", "驱逐", "frigate", "护卫"]):
            data.update({"speed": 31, "maxFuel": 900000, "fuelRate": 6500, "range": 4500})
        return data, 0.55, warnings

    if asset_type == "facility":
        radius = 120
        if any(token in text for token in ["s-400", "hq-9", "防空", "sam", "missile"]):
            radius = 250
        elif any(token in text for token in ["radar", "雷达", "预警"]):
            radius = 350
        elif any(token in text for token in ["command", "指挥"]):
            radius = 50
        return {"className": name, "range": radius}, 0.52, warnings

    if asset_type == "airbase":
        known_locations = {
            "andersen": ("Andersen Air Force Base", "US", 13.5839, 144.9290),
            "guam": ("Andersen Air Force Base", "US", 13.5839, 144.9290),
            "kadena": ("Kadena Air Base", "Japan", 26.3517, 127.7694),
            "fairford": ("RAF Fairford", "United Kingdom", 51.6822, -1.7900),
        }
        for token, values in known_locations.items():
            if token in text:
                base_name, country, lat, lon = values
                return (
                    {"name": base_name, "country": country, "latitude": lat, "longitude": lon},
                    0.64,
                    warnings,
                )
        return (
            {"name": name, "country": "Unknown", "latitude": 0, "longitude": 0},
            0.42,
            warnings + ["未能可靠推断机场坐标，已使用 0/0 占位，请手动修正。"],
        )

    data = {
        "className": name,
        "speed": 1800,
        "maxFuel": 220,
        "fuelRate": 60,
        "range": 80,
        "lethality": 0.72,
    }
    if any(token in text for token in ["aim-120", "amraam", "空空"]):
        data.update({"speed": 2300, "range": 90, "lethality": 0.78})
    elif any(token in text for token in ["巡航", "cruise", "tomahawk"]):
        data.update({"speed": 480, "maxFuel": 900, "fuelRate": 140, "range": 900, "lethality": 0.82})
    return data, 0.5, warnings


def _effective_base_url(provider: str, base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if normalized:
        return normalize_and_validate_base_url(
            normalized,
            allow_private_network=provider.strip().lower() == "ollama",
        )
    return _OPENAI_COMPAT_BASE_URLS.get(provider.strip().lower(), "")


def _provider_requires_api_key(provider: str) -> bool:
    return provider.strip().lower() not in _NO_API_KEY_PROVIDERS


def _auth_headers(api_key: str) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _can_call_llm_provider(
    *, provider: str, model: str, api_key: str, base_url: str
) -> bool:
    provider_name = provider.strip().lower()
    if not provider_name or not model.strip():
        return False
    if api_key.strip():
        return True
    if provider_name == "ollama":
        return True
    if provider_name == "custom" and base_url.strip():
        return True
    return False


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("AI response did not contain a JSON object")
    parsed = json.loads(cleaned[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("AI response JSON must be an object")
    return parsed


def _unit_asset_json_schema(asset_type: UnitAssetType) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["type", "data", "confidence", "warnings"],
        "properties": {
            "type": {"type": "string", "enum": [asset_type]},
            "data": {"type": "object", "additionalProperties": True},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "warnings": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 4,
            },
        },
    }


def _unit_asset_prompt(asset_type: UnitAssetType, query: str, context: str) -> str:
    return f"""
Generate a simulator unit asset for 天枢平台.

Requested type: {asset_type}
User query: {query}
Additional context: {context or "none"}

Return only JSON with:
{{
  "type": "{asset_type}",
  "data": {{ ... }},
  "confidence": 0.0,
  "warnings": ["..."]
}}

Use public, non-classified, approximate values when exact values are uncertain.
Required units:
- aircraft/ship/weapon speed: kts
- maxFuel: kg
- fuelRate: kg/h
- range: nm
- facility range: nm
- airbase latitude/longitude: decimal degrees
Required data fields:
- aircraft: className, speed, maxFuel, fuelRate, range, isTanker,
  fuelOffloadCapacity, fuelTransferRate, refuelRange, isElectronicWarfare,
  jammingRange, jammingStrength, jammingModes, communicationDisruption,
  dataSource, units
- ship: className, speed, maxFuel, fuelRate, range, dataSource, units
- facility: className, range
- airbase: name, country, latitude, longitude
- weapon: className, speed, maxFuel, fuelRate, range, lethality
""".strip()


def _response_text(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str):
        return output_text

    fragments: list[str] = []
    output = payload.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if isinstance(text, str):
                    fragments.append(text)
    if fragments:
        return "".join(fragments)
    raise ValueError("AI response did not contain output text")


def _chat_completion_json(
    *,
    provider: str,
    model: str,
    api_key: str,
    base_url: str,
    asset_type: UnitAssetType,
    query: str,
    context: str,
) -> dict[str, Any]:
    effective_base = _effective_base_url(provider, base_url)
    provider_name = provider.strip().lower()
    if not effective_base or not model:
        raise ValueError("model configuration is incomplete")
    if not api_key and _provider_requires_api_key(provider_name):
        raise ValueError("model configuration is incomplete")
    if provider_name == "anthropic":
        raise ValueError("anthropic direct generation is not supported here")
    if provider_name == "openai-responses":
        return _responses_json(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            asset_type=asset_type,
            query=query,
            context=context,
        )

    prompt = _unit_asset_prompt(asset_type, query, context)

    request_body = {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "You generate safe, approximate, public-source simulator data as JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
    }
    request = urllib.request.Request(
        f"{effective_base}/chat/completions",
        data=json.dumps(request_body).encode("utf-8"),
        headers=_auth_headers(api_key),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise ValueError("AI model request failed") from exc

    content = payload["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return _extract_json_object(str(content))


def _responses_json(
    *,
    provider: str,
    model: str,
    api_key: str,
    base_url: str,
    asset_type: UnitAssetType,
    query: str,
    context: str,
) -> dict[str, Any]:
    effective_base = _effective_base_url(provider, base_url)
    provider_name = provider.strip().lower()
    if not effective_base or not model:
        raise ValueError("model configuration is incomplete")
    if not api_key and _provider_requires_api_key(provider_name):
        raise ValueError("model configuration is incomplete")

    request_body = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": (
                    "You generate safe, approximate, public-source simulator data "
                    "as JSON only."
                ),
            },
            {
                "role": "user",
                "content": _unit_asset_prompt(asset_type, query, context),
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "tianshu_unit_asset",
                "strict": True,
                "schema": _unit_asset_json_schema(asset_type),
            }
        },
    }
    request = urllib.request.Request(
        f"{effective_base}/responses",
        data=json.dumps(request_body).encode("utf-8"),
        headers=_auth_headers(api_key),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise ValueError("AI model request failed") from exc

    return _extract_json_object(_response_text(payload))


async def generate_unit_asset_payload(
    *,
    asset_type: UnitAssetType,
    query: str,
    context: str = "",
    provider: str = "",
    model: str = "",
    api_key: str = "",
    base_url: str = "",
) -> tuple[dict[str, Any], Literal["llm", "estimate"], float, list[str]]:
    warnings: list[str] = []
    if _can_call_llm_provider(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
    ):
        try:
            candidate = await asyncio.to_thread(
                _chat_completion_json,
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
                asset_type=asset_type,
                query=query,
                context=context,
            )
            candidate_type = candidate.get("type", asset_type)
            if candidate_type != asset_type:
                raise ValueError("AI returned a different unit asset type")
            data = candidate.get("data")
            if not isinstance(data, dict):
                raise ValueError("AI returned invalid data")
            _, normalized = normalize_asset_data(asset_type, data)
            confidence = float(candidate.get("confidence", 0.72))
            raw_warnings = candidate.get("warnings", [])
            if isinstance(raw_warnings, list):
                warnings.extend(str(item) for item in raw_warnings[:4])
            return normalized, "llm", min(1.0, max(0.0, confidence)), warnings
        except UnsafeBaseUrlError as exc:
            warnings.append(f"AI Base URL blocked: {exc}")
        except Exception:
            warnings.append("AI 模型暂不可用或返回格式不完整，已改用本地估算。")

    data, confidence, estimate_warnings = estimate_unit_asset(asset_type, query)
    _, normalized = normalize_asset_data(asset_type, data)
    return normalized, "estimate", confidence, warnings + estimate_warnings
