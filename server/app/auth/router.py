"""Auth + users routers aggregated under /api so the existing nginx
``location /api/`` reverse proxy keeps working.

Endpoints exposed:
    POST   /api/auth/register
    POST   /api/auth/jwt/login
    POST   /api/auth/jwt/logout
    GET    /api/users/me
    PATCH  /api/users/me
"""

from __future__ import annotations

from fastapi import APIRouter

from app.auth.schemas import UserCreate, UserRead, UserUpdate
from app.auth.users import auth_backend, fastapi_users

router = APIRouter(prefix="/api")

# /api/auth/jwt/login + /api/auth/jwt/logout
router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)

# /api/auth/register
router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)

# /api/users/me, /api/users/{id} (admin)
router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)
