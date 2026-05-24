"""/api/unit-assets CRUD endpoints."""

from __future__ import annotations

from typing import Sequence

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.users import current_active_user
from app.db.session import get_async_session
from app.unit_assets.errors import (
    UnitAssetConflictError,
    UnitAssetForbiddenError,
    UnitAssetInvalidError,
    UnitAssetNotFoundError,
    UnitAssetServiceError,
)
from app.unit_assets.models import UnitAsset
from app.unit_assets.generator import generate_unit_asset_payload
from app.unit_assets.schemas import (
    UnitAssetCatalog,
    UnitAssetCreate,
    UnitAssetGenerateRequest,
    UnitAssetGenerateResponse,
    UnitAssetImportRequest,
    UnitAssetImportResult,
    UnitAssetRead,
    UnitAssetUpdate,
)
from app.unit_assets.service import (
    catalog_from_assets,
    create_unit_asset,
    delete_unit_asset,
    import_unit_assets,
    list_unit_assets,
    reset_user_unit_assets,
    update_unit_asset,
)

router = APIRouter(prefix="/api/unit-assets", tags=["unit-assets"])


def _http_error(exc: UnitAssetServiceError) -> HTTPException:
    status_code = status.HTTP_400_BAD_REQUEST
    if isinstance(exc, UnitAssetNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, UnitAssetForbiddenError):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, UnitAssetConflictError):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(exc, UnitAssetInvalidError):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    return HTTPException(
        status_code=status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
        },
    )


@router.get("", response_model=list[UnitAssetRead])
async def list_assets(
    type: str | None = None,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Sequence[UnitAsset]:
    try:
        return await list_unit_assets(session, user, asset_type=type)
    except UnitAssetServiceError as exc:
        raise _http_error(exc) from exc


@router.get("/catalog", response_model=UnitAssetCatalog)
async def get_asset_catalog(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> UnitAssetCatalog:
    assets = await list_unit_assets(session, user)
    return catalog_from_assets(assets)


@router.post("", response_model=UnitAssetRead, status_code=status.HTTP_201_CREATED)
async def create_asset(
    payload: UnitAssetCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> UnitAsset:
    try:
        return await create_unit_asset(
            session,
            user,
            asset_type=payload.type,
            data=payload.data,
        )
    except UnitAssetServiceError as exc:
        raise _http_error(exc) from exc


@router.post("/generate", response_model=UnitAssetGenerateResponse)
async def generate_asset(
    payload: UnitAssetGenerateRequest,
    user: User = Depends(current_active_user),
    x_aicc_model_provider: str = Header(default=""),
    x_aicc_model_name: str = Header(default=""),
    x_aicc_model_api_key: str = Header(default=""),
    x_aicc_model_base_url: str = Header(default=""),
) -> UnitAssetGenerateResponse:
    _ = user
    try:
        data, source, confidence, warnings = await generate_unit_asset_payload(
            asset_type=payload.type,
            query=payload.query,
            context=payload.context,
            provider=x_aicc_model_provider.strip(),
            model=x_aicc_model_name.strip(),
            api_key=x_aicc_model_api_key.strip(),
            base_url=x_aicc_model_base_url.strip(),
        )
    except UnitAssetServiceError as exc:
        raise _http_error(exc) from exc
    return UnitAssetGenerateResponse(
        type=payload.type,
        data=data,
        source=source,
        confidence=confidence,
        warnings=warnings,
    )


@router.post("/import", response_model=UnitAssetImportResult)
async def import_assets(
    payload: UnitAssetImportRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> UnitAssetImportResult:
    try:
        return await import_unit_assets(session, user, payload)
    except UnitAssetServiceError as exc:
        raise _http_error(exc) from exc


@router.post("/reset", response_model=list[UnitAssetRead])
async def reset_assets(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Sequence[UnitAsset]:
    return await reset_user_unit_assets(session, user)


@router.patch("/{asset_id}", response_model=UnitAssetRead)
async def update_asset(
    asset_id: str,
    payload: UnitAssetUpdate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> UnitAsset:
    if payload.data is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="data is required",
        )
    try:
        return await update_unit_asset(session, user, asset_id, data=payload.data)
    except UnitAssetServiceError as exc:
        raise _http_error(exc) from exc


@router.delete(
    "/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_asset(
    asset_id: str,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Response:
    try:
        await delete_unit_asset(session, user, asset_id)
    except UnitAssetServiceError as exc:
        raise _http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
