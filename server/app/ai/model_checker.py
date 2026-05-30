from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal
from urllib import error, request

from app.ai.model_endpoint_policy import (
    allows_private_model_network,
    normalize_model_base_url,
)
from app.ai.models import ModelCheckRequest, ModelCheckResponse
from app.security.url_guard import UnsafeBaseUrlError, normalize_and_validate_base_url


@dataclass
class _ProbeResult:
    endpoint: str
    http_status: int | None
    payload: dict | None
    error_message: str | None
    reachable: bool


def _candidate_model_endpoints(base_url: str) -> list[str]:
    normalized = base_url.strip().rstrip("/")
    if normalized.endswith("/models"):
        return [normalized]

    candidates = [f"{normalized}/models"]
    if not normalized.endswith("/v1"):
        candidates.append(f"{normalized}/v1/models")
    return candidates


class _SafeRedirectHandler(request.HTTPRedirectHandler):
    def __init__(self, *, allow_private_network: bool) -> None:
        self._allow_private_network = allow_private_network

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        normalize_and_validate_base_url(
            newurl,
            allow_private_network=self._allow_private_network,
        )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _probe_models_endpoint(
    endpoint: str,
    api_key: str,
    *,
    allow_private_network: bool,
) -> _ProbeResult:
    headers = {
        "Accept": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = request.Request(endpoint, headers=headers, method="GET")
    opener = request.build_opener(
        _SafeRedirectHandler(allow_private_network=allow_private_network)
    )
    try:
        with opener.open(req, timeout=12) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(body) if body else {}
            return _ProbeResult(
                endpoint=endpoint,
                http_status=resp.status,
                payload=parsed if isinstance(parsed, dict) else {},
                error_message=None,
                reachable=True,
            )
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        message = body.strip() or exc.reason
        return _ProbeResult(
            endpoint=endpoint,
            http_status=exc.code,
            payload=None,
            error_message=str(message),
            reachable=True,
        )
    except error.URLError as exc:
        return _ProbeResult(
            endpoint=endpoint,
            http_status=None,
            payload=None,
            error_message=str(exc.reason),
            reachable=False,
        )
    except Exception as exc:  # noqa: BLE001
        return _ProbeResult(
            endpoint=endpoint,
            http_status=None,
            payload=None,
            error_message=str(exc),
            reachable=False,
        )


def check_model_connectivity(payload: ModelCheckRequest) -> ModelCheckResponse:
    allow_private_network = allows_private_model_network(payload.provider)
    try:
        normalized_base_url = normalize_model_base_url(
            payload.provider,
            payload.baseUrl,
        )
    except UnsafeBaseUrlError as exc:
        return ModelCheckResponse(
            status="error",
            message=f"Base URL blocked: {exc}",
            provider=payload.provider,
            endpoint="",
            auth_ok=False,
            models_listed=False,
            checked_model=payload.model or None,
            sample_models=[],
        )

    endpoints = _candidate_model_endpoints(normalized_base_url)
    last_result: _ProbeResult | None = None

    for endpoint in endpoints:
        result = _probe_models_endpoint(
            endpoint,
            payload.apiKey,
            allow_private_network=allow_private_network,
        )
        last_result = result

        if result.http_status == 404 and len(endpoints) > 1:
            continue

        if result.http_status in (401, 403):
            return ModelCheckResponse(
                status="error",
                message="Model endpoint reachable, but API key is unauthorized.",
                provider=payload.provider,
                endpoint=result.endpoint,
                auth_ok=False,
                models_listed=False,
                checked_model=payload.model or None,
                checked_model_exists=None,
                http_status=result.http_status,
                error=result.error_message,
            )

        if result.http_status and result.http_status >= 400:
            return ModelCheckResponse(
                status="error",
                message="Model endpoint returned an error response.",
                provider=payload.provider,
                endpoint=result.endpoint,
                auth_ok=False,
                models_listed=False,
                checked_model=payload.model or None,
                checked_model_exists=None,
                http_status=result.http_status,
                error=result.error_message,
            )

        if result.payload is not None:
            models_raw = result.payload.get("data", [])
            model_ids: list[str] = []
            if isinstance(models_raw, list):
                for item in models_raw:
                    if isinstance(item, dict) and "id" in item:
                        model_ids.append(str(item["id"]))

            model_exists: bool | None = None
            status: Literal["ok", "partial"] = "ok"
            message = "Model endpoint and API key are valid."
            if payload.model:
                model_exists = payload.model in model_ids
                if not model_exists:
                    status = "partial"
                    message = "Endpoint/key are valid, but the specified model was not found."

            return ModelCheckResponse(
                status=status,
                message=message,
                provider=payload.provider,
                endpoint=result.endpoint,
                auth_ok=True,
                models_listed=True,
                checked_model=payload.model or None,
                checked_model_exists=model_exists,
                http_status=result.http_status,
                sample_models=model_ids[:10],
            )

    if last_result is not None:
        return ModelCheckResponse(
            status="error",
            message="Unable to reach model endpoint.",
            provider=payload.provider,
            endpoint=last_result.endpoint,
            auth_ok=False,
            models_listed=False,
            checked_model=payload.model or None,
            checked_model_exists=None,
            http_status=last_result.http_status,
            error=last_result.error_message,
        )

    return ModelCheckResponse(
        status="error",
        message="No endpoint candidate generated from baseUrl.",
        provider=payload.provider,
        endpoint=payload.baseUrl,
        auth_ok=False,
        models_listed=False,
        checked_model=payload.model or None,
        checked_model_exists=None,
    )
