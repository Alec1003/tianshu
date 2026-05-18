"""fastapi-users wiring: UserManager + auth backend + dependency factories.

This is the central piece glueing model -> manager -> backend -> routers.
"""

from __future__ import annotations

import uuid
from typing import AsyncGenerator

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.config import get_settings
from app.db.session import get_async_session

settings = get_settings()


# ----- DB adapter: links our SQLAlchemy session to fastapi-users -------------
async def get_user_db(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
    yield SQLAlchemyUserDatabase(session, User)


# ----- UserManager: where lifecycle hooks (on_after_register, etc.) live -----
class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.jwt_secret
    verification_token_secret = settings.jwt_secret

    async def on_after_register(
        self, user: User, request: Request | None = None
    ) -> None:
        """First-user-as-superuser bootstrap to avoid a chicken-and-egg setup
        in dev. Disable via ``AICC_FIRST_USER_IS_SUPERUSER=false`` in shared
        environments where you want manual ops to gate it.

        We reuse ``self.user_db.session`` because ``user`` is already attached
        to it; opening a fresh session would raise ``InvalidRequestError:
        Object is already attached to session``.
        """
        if not settings.first_user_is_superuser:
            return
        sess: AsyncSession = self.user_db.session  # type: ignore[assignment]
        total_users = await sess.scalar(select(func.count(User.id)))
        if total_users == 1:
            # First-ever account -> promote in-place.
            user.is_superuser = True
            user.is_verified = True
            await sess.commit()


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
) -> AsyncGenerator[UserManager, None]:
    yield UserManager(user_db)


# ----- Auth backend: JWT in Authorization: Bearer <token> --------------------
bearer_transport = BearerTransport(tokenUrl="api/auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(
        secret=settings.jwt_secret,
        lifetime_seconds=settings.jwt_lifetime_seconds,
    )


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)


# ----- FastAPIUsers facade + ready-to-use dependencies -----------------------
fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

# Standard dependencies most route handlers will reach for.
current_active_user = fastapi_users.current_user(active=True)
current_active_superuser = fastapi_users.current_user(active=True, superuser=True)
