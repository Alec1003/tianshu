"""Per-request Bearer-token auth for the MCP HTTP transport.

Why an ASGI middleware (not a FastAPI ``Depends``):
    The MCP server is a Starlette ``ASGIApp`` that we ``mount`` under
    ``/api/mcp``; FastAPI dependency injection only fires on FastAPI
    ``APIRouter`` endpoints, not on mounted sub-apps. So we wrap the MCP
    ASGI app with an ASGI-level middleware that:

    1. Pulls ``Authorization: Bearer <jwt>`` off the request.
    2. Hands it to fastapi-users' production ``JWTStrategy`` (the same one
       backing ``/api/auth/jwt/login``) so token format/lifetime/signature
       rules stay identical.
    3. Sets ``app.mcp.server._request_user_var`` for the duration of the
       request via a context-token (so simultaneous SSE/HTTP requests don't
       leak each other's user identity).
    4. Rejects unauthenticated requests with a structured 401 + WWW-Authenticate
       header before they reach the tool layer.

Dev escape hatch:
    Setting ``AICC_MCP_HTTP_DEV_USER_ID=<uuid>`` skips token validation and
    pins every request to that user. Only meaningful for local debugging
    (mcp inspector, smoke scripts) -- ``logger.warning`` flags it loudly so
    it doesn't ship to prod by accident.

Cookie / OPTIONS handling:
    - We honor ``Authorization`` header only; cookie-based auth is out of
      scope (CORS preflight + browser ergonomics for that belong in the
      front-end Sidebar slice, not here).
    - ``OPTIONS`` (CORS preflight) is passed through unauthenticated so
      browsers can negotiate CORS without throwing 401 noise.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.auth.models import User
from app.db.session import async_session_maker
from app.mcp.auth import (
    McpAuthError,
    resolve_user_from_token,
    resolve_user_from_user_id,
)
from app.mcp.server import reset_request_user, set_request_user

logger = logging.getLogger(__name__)

ENV_HTTP_DEV_USER_ID = "AICC_MCP_HTTP_DEV_USER_ID"


def _bearer_from_scope(scope: Scope) -> str | None:
    """Extract the raw token from ``Authorization: Bearer <token>``."""
    for raw_name, raw_value in scope.get("headers", []):
        if raw_name == b"authorization":
            value = raw_value.decode("latin-1")
            if value.lower().startswith("bearer "):
                return value[7:].strip()
            return None
    return None


async def _resolve_user(token: str | None) -> User | None:
    """Run our auth resolution, returning ``None`` for a hard reject.

    Intentionally swallows ``McpAuthError`` -- the middleware turns ``None``
    into a 401 envelope; we don't want stack traces on the MCP wire.
    """
    dev_user_id = os.environ.get(ENV_HTTP_DEV_USER_ID, "").strip()
    if dev_user_id:
        # Dev-only path: warn loudly and short-circuit token verification.
        logger.warning(
            "mcp.http_auth: bypassing token check via %s (dev only!)",
            ENV_HTTP_DEV_USER_ID,
        )
        try:
            async with async_session_maker() as session:
                return await resolve_user_from_user_id(session, dev_user_id)
        except McpAuthError as exc:
            logger.error("mcp.http_auth: dev user id invalid: %s", exc)
            return None

    if not token:
        return None
    try:
        async with async_session_maker() as session:
            return await resolve_user_from_token(session, token)
    except McpAuthError as exc:
        logger.info("mcp.http_auth: rejecting request: %s", exc)
        return None


async def _send_unauthorized(send: Send, description: str) -> None:
    body: dict[str, Any] = {
        "error": "unauthorized",
        "error_description": description,
    }
    body_bytes = json.dumps(body).encode()
    www_auth = f'Bearer error="invalid_token", error_description="{description}"'
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body_bytes)).encode()),
                (b"www-authenticate", www_auth.encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body_bytes})


class BearerAuthASGI:
    """ASGI middleware: gate the MCP transport behind a fastapi-users JWT."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            # Streamable HTTP transport never opens a websocket; pass others
            # through verbatim so we don't break unrelated traffic if the host
            # nests this middleware deeper than we expect.
            await self.app(scope, receive, send)
            return

        # CORS preflight: let the browser negotiate without auth headers.
        if scope.get("method", "").upper() == "OPTIONS":
            await self.app(scope, receive, send)
            return

        token = _bearer_from_scope(scope)
        user = await _resolve_user(token)
        if user is None:
            await _send_unauthorized(send, "valid Bearer token required")
            return

        # Bind for the duration of this request only; the contextvar token
        # is reset in the finally block so concurrent requests don't see
        # each other's user (anyio task contexts copy contextvars, but ASGI
        # frameworks reuse tasks across requests in some setups).
        ctx_token = set_request_user(user)
        try:
            # Lightweight access log; aligns with FastAPI's uvicorn access.
            request_id = scope.get("headers", [])
            logger.debug(
                "mcp.http_auth: authorized user=%s path=%s",
                user.email,
                scope.get("path"),
            )

            # Wrap ``send`` only to detect when the response actually starts;
            # we do not mutate the body.
            async def send_wrapper(message: Message) -> None:
                await send(message)

            await self.app(scope, receive, send_wrapper)
        finally:
            reset_request_user(ctx_token)
