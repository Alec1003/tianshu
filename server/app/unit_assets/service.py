"""Unit asset business functions."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable, Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.unit_assets.errors import (
    UnitAssetConflictError,
    UnitAssetForbiddenError,
    UnitAssetInvalidError,
    UnitAssetNotFoundError,
)
from app.unit_assets.models import UnitAsset
from app.unit_assets.schemas import (
    VALID_UNIT_ASSET_TYPES,
    UnitAssetCatalog,
    UnitAssetImportRequest,
    UnitAssetImportResult,
)

DEFAULT_UNIT_ASSETS_PATH = Path(__file__).with_name("default_unit_assets.json")

CATALOG_KEYS: dict[str, str] = {
    "aircraft": "aircraftDb",
    "ship": "shipDb",
    "facility": "facilityDb",
    "airbase": "airbaseDb",
    "weapon": "weaponDb",
}

NAME_FIELDS: dict[str, str] = {
    "airbase": "name",
    "aircraft": "className",
    "ship": "className",
    "facility": "className",
    "weapon": "className",
}

REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "aircraft": ("className", "speed", "maxFuel", "fuelRate", "range"),
    "ship": ("className", "speed", "maxFuel", "fuelRate", "range"),
    "facility": ("className", "range"),
    "airbase": ("name", "latitude", "longitude", "country"),
    "weapon": ("className", "speed", "maxFuel", "fuelRate", "range", "lethality"),
}

NUMERIC_FIELDS: dict[str, tuple[str, ...]] = {
    "aircraft": (
        "speed",
        "maxFuel",
        "fuelRate",
        "range",
        "fuelOffloadCapacity",
        "fuelTransferRate",
        "refuelRange",
    ),
    "ship": ("speed", "maxFuel", "fuelRate", "range"),
    "facility": ("range",),
    "airbase": ("latitude", "longitude"),
    "weapon": ("speed", "maxFuel", "fuelRate", "range", "lethality"),
}


def _asset_name(asset_type: str, data: dict[str, Any]) -> str:
    field = NAME_FIELDS[asset_type]
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise UnitAssetInvalidError(field, "must not be empty")
    name = value.strip()
    if len(name) > 160:
        raise UnitAssetInvalidError(field, "exceeds 160 chars")
    return name


def _validate_number(value: Any, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise UnitAssetInvalidError(field, "must be a number")
    if not math.isfinite(float(value)):
        raise UnitAssetInvalidError(field, "must be finite")


def normalize_asset_data(asset_type: str, data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if asset_type not in VALID_UNIT_ASSET_TYPES:
        raise UnitAssetInvalidError("type", "unknown unit asset type")
    if not isinstance(data, dict):
        raise UnitAssetInvalidError("data", "must be a JSON object")

    normalized = dict(data)
    required = REQUIRED_FIELDS[asset_type]
    for field in required:
        if field not in normalized or normalized[field] is None:
            raise UnitAssetInvalidError(field, "is required")

    name = _asset_name(asset_type, normalized)
    normalized[NAME_FIELDS[asset_type]] = name

    for field in NUMERIC_FIELDS[asset_type]:
        if field in normalized and normalized[field] is not None:
            _validate_number(normalized[field], field)

    return name, normalized


def _can_write(asset: UnitAsset, user: User) -> bool:
    if user.is_superuser:
        return True
    if asset.is_system:
        return False
    return str(asset.owner_id) == str(user.id)


async def _load_or_404(session: AsyncSession, asset_id: str) -> UnitAsset:
    asset = await session.get(UnitAsset, asset_id)
    if asset is None:
        raise UnitAssetNotFoundError(asset_id)
    return asset


async def _find_system_by_type_name(
    session: AsyncSession, asset_type: str, name: str
) -> UnitAsset | None:
    rows = await session.execute(
        select(UnitAsset).where(
            UnitAsset.type == asset_type,
            UnitAsset.name == name,
            UnitAsset.owner_id.is_(None),
        )
    )
    return rows.scalar_one_or_none()


async def _find_user_by_type_name(
    session: AsyncSession,
    user: User,
    asset_type: str,
    name: str,
) -> UnitAsset | None:
    rows = await session.execute(
        select(UnitAsset).where(
            UnitAsset.type == asset_type,
            UnitAsset.name == name,
            UnitAsset.owner_id == user.id,
        )
    )
    return rows.scalar_one_or_none()


async def _find_scope_conflict(
    session: AsyncSession,
    user: User,
    *,
    asset_type: str,
    name: str,
    is_system: bool,
    exclude_id: str | None = None,
) -> UnitAsset | None:
    existing = (
        await _find_system_by_type_name(session, asset_type, name)
        if is_system
        else await _find_user_by_type_name(session, user, asset_type, name)
    )
    if existing is not None and existing.id != exclude_id:
        return existing
    return None


async def list_unit_assets(
    session: AsyncSession,
    user: User,
    *,
    asset_type: str | None = None,
) -> Sequence[UnitAsset]:
    stmt = select(UnitAsset).where(
        (UnitAsset.is_system == True) | (UnitAsset.owner_id == user.id)  # noqa: E712
    )
    if asset_type:
        if asset_type not in VALID_UNIT_ASSET_TYPES:
            raise UnitAssetInvalidError("type", "unknown unit asset type")
        stmt = stmt.where(UnitAsset.type == asset_type)
    stmt = stmt.order_by(
        UnitAsset.type.asc(),
        UnitAsset.name.asc(),
        UnitAsset.is_system.desc(),
    )
    rows = await session.execute(stmt)
    return rows.scalars().all()


async def create_unit_asset(
    session: AsyncSession,
    user: User,
    *,
    asset_type: str,
    data: dict[str, Any],
    is_system: bool = False,
) -> UnitAsset:
    name, normalized = normalize_asset_data(asset_type, data)
    existing = await _find_scope_conflict(
        session,
        user,
        asset_type=asset_type,
        name=name,
        is_system=is_system,
    )
    if existing is not None:
        raise UnitAssetConflictError(asset_type, name)

    asset = UnitAsset(
        type=asset_type,
        name=name,
        data=normalized,
        is_system=is_system,
        owner_id=None if is_system else user.id,
    )
    session.add(asset)
    await session.commit()
    await session.refresh(asset)
    return asset


async def update_unit_asset(
    session: AsyncSession,
    user: User,
    asset_id: str,
    *,
    data: dict[str, Any],
) -> UnitAsset:
    asset = await _load_or_404(session, asset_id)
    if not _can_write(asset, user):
        raise UnitAssetForbiddenError(asset.id)

    name, normalized = normalize_asset_data(asset.type, data)
    existing = await _find_scope_conflict(
        session,
        user,
        asset_type=asset.type,
        name=name,
        is_system=asset.is_system,
        exclude_id=asset.id,
    )
    if existing is not None:
        raise UnitAssetConflictError(asset.type, name)

    asset.name = name
    asset.data = normalized
    asset.version += 1
    await session.commit()
    await session.refresh(asset)
    return asset


async def delete_unit_asset(
    session: AsyncSession,
    user: User,
    asset_id: str,
) -> None:
    asset = await _load_or_404(session, asset_id)
    if not _can_write(asset, user):
        raise UnitAssetForbiddenError(asset.id)
    await session.delete(asset)
    await session.commit()


async def reset_user_unit_assets(session: AsyncSession, user: User) -> Sequence[UnitAsset]:
    await session.execute(delete(UnitAsset).where(UnitAsset.owner_id == user.id))
    await session.commit()
    return await list_unit_assets(session, user)


def catalog_from_assets(assets: Iterable[UnitAsset]) -> UnitAssetCatalog:
    catalog = UnitAssetCatalog()
    for asset in assets:
        key = CATALOG_KEYS.get(asset.type)
        if key is None:
            continue
        getattr(catalog, key).append(asset.data)
    return catalog


def iter_catalog_items(catalog: UnitAssetCatalog) -> Iterable[tuple[str, dict[str, Any]]]:
    for asset_type, key in CATALOG_KEYS.items():
        for item in getattr(catalog, key):
            yield asset_type, item


async def import_unit_assets(
    session: AsyncSession,
    user: User,
    payload: UnitAssetImportRequest,
) -> UnitAssetImportResult:
    created = 0
    updated = 0
    skipped = 0

    for asset_type, item in iter_catalog_items(payload):
        name, normalized = normalize_asset_data(asset_type, item)
        existing = await _find_user_by_type_name(session, user, asset_type, name)
        if existing is not None:
            if not payload.replace_existing:
                skipped += 1
                continue
            existing.data = normalized
            existing.version += 1
            updated += 1
            continue

        system_existing = await _find_system_by_type_name(session, asset_type, name)
        if system_existing is not None:
            if payload.replace_existing and _can_write(system_existing, user):
                system_existing.data = normalized
                system_existing.version += 1
                updated += 1
                continue
            skipped += 1
            continue

        if existing is None:
            session.add(
                UnitAsset(
                    type=asset_type,
                    name=name,
                    data=normalized,
                    is_system=False,
                    owner_id=user.id,
                )
            )
            created += 1
            continue

    await session.commit()
    assets = await list_unit_assets(session, user)
    return UnitAssetImportResult(
        created=created,
        updated=updated,
        skipped=skipped,
        assets=list(assets),
    )


def load_default_catalog() -> UnitAssetCatalog:
    data = json.loads(DEFAULT_UNIT_ASSETS_PATH.read_text(encoding="utf-8"))
    return UnitAssetCatalog.model_validate(data)


async def seed_default_unit_assets(session: AsyncSession) -> int:
    catalog = load_default_catalog()
    seeded = 0
    for asset_type, item in iter_catalog_items(catalog):
        name, normalized = normalize_asset_data(asset_type, item)
        existing = await _find_system_by_type_name(session, asset_type, name)
        if existing is not None:
            continue
        session.add(
            UnitAsset(
                type=asset_type,
                name=name,
                data=normalized,
                is_system=True,
                owner_id=None,
            )
        )
        seeded += 1
    if seeded:
        await session.commit()
    return seeded
