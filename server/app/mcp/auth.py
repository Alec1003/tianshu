"""MCP server authentication.

stdio 模式（Claude Desktop / Cursor 本地接入）：
    通过环境变量 ``AICC_MCP_TOKEN`` 提供一次 JWT，server 启动时解析并把
    对应 ``User`` 注入 lifespan context；后续所有 tool 调用都用这个 user
    做权限判断。变量名与 fastapi-users JWTStrategy 兼容（同一份签名密钥）。

为什么不接 OAuth 2.1：FastMCP SDK 内置的 OAuth 协议是给"暴露 token 服
务"用的，对当前 P0 阶段（单用户、单机 stdio）反而是过度设计；下一切片
做 Streamable HTTP 时再引入 ``TokenVerifier``。

错误模型：解析失败 raise ``McpAuthError``，由 ``__main__`` 在 stderr 输
出可读信息后退出。
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import TYPE_CHECKING

from fastapi_users.db import SQLAlchemyUserDatabase

from app.auth.models import User
from app.auth.users import UserManager, get_jwt_strategy

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Env vars (prefix AICC_ aligns with app.config.Settings convention).
ENV_TOKEN = "AICC_MCP_TOKEN"
ENV_USER_ID = "AICC_MCP_USER_ID"


class McpAuthError(RuntimeError):
    """Raised when MCP server cannot identify the user."""


async def resolve_user_from_token(
    session: "AsyncSession", token: str
) -> User:
    """Decode a fastapi-users JWT and load the matching ``User``.

    Re-uses the production ``JWTStrategy`` so token format/signature/lifetime
    rules stay identical to the HTTP API; if a token works for ``/api/auth/
    jwt/login`` it works here, and vice versa. No new attack surface.
    """
    user_db = SQLAlchemyUserDatabase(session, User)
    user_manager = UserManager(user_db)
    jwt_strategy = get_jwt_strategy()
    user = await jwt_strategy.read_token(token, user_manager)
    if user is None:
        raise McpAuthError("invalid or expired token")
    if not user.is_active:
        raise McpAuthError("user is inactive")
    return user


async def resolve_user_from_user_id(
    session: "AsyncSession", user_id: str
) -> User:
    """Dev/test backdoor: directly load a user by UUID.

    Used by the stdio entrypoint when ``AICC_MCP_USER_ID`` is set instead of
    a real JWT (handy for `python -m app.mcp` smoke tests). Production
    deployments should always use ``AICC_MCP_TOKEN``.
    """
    try:
        uid = uuid.UUID(user_id)
    except (TypeError, ValueError) as exc:
        raise McpAuthError(f"invalid user id format: {user_id!r}") from exc
    user = await session.get(User, uid)
    if user is None:
        raise McpAuthError(f"user not found: {user_id}")
    if not user.is_active:
        raise McpAuthError("user is inactive")
    return user


async def resolve_user_from_env(session: "AsyncSession") -> User:
    """Pick the right resolver based on which env var is set.

    Precedence: ``AICC_MCP_TOKEN`` > ``AICC_MCP_USER_ID``. At least one is
    required; otherwise we surface a clear error pointing at the README.
    """
    token = os.environ.get(ENV_TOKEN, "").strip()
    if token:
        logger.info("mcp.auth: resolving user via %s", ENV_TOKEN)
        return await resolve_user_from_token(session, token)

    user_id = os.environ.get(ENV_USER_ID, "").strip()
    if user_id:
        logger.warning(
            "mcp.auth: using dev-only %s (production should set %s)",
            ENV_USER_ID,
            ENV_TOKEN,
        )
        return await resolve_user_from_user_id(session, user_id)

    raise McpAuthError(
        f"no MCP credentials; set {ENV_TOKEN} (preferred) or {ENV_USER_ID}"
    )
