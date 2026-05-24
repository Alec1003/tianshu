"""Pydantic DTOs for /api/unit-assets."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

UnitAssetType = Literal["aircraft", "ship", "facility", "airbase", "weapon"]
VALID_UNIT_ASSET_TYPES = {"aircraft", "ship", "facility", "airbase", "weapon"}


class UnitAssetCreate(BaseModel):
    type: UnitAssetType
    data: dict[str, Any]


class UnitAssetUpdate(BaseModel):
    data: dict[str, Any] | None = None


class UnitAssetGenerateRequest(BaseModel):
    type: UnitAssetType
    query: str = Field(min_length=1, max_length=240)
    context: str = Field(default="", max_length=1200)


class UnitAssetGenerateResponse(BaseModel):
    type: UnitAssetType
    data: dict[str, Any]
    source: Literal["llm", "estimate"]
    confidence: float = Field(ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)


class UnitAssetRead(BaseModel):
    id: str
    type: UnitAssetType
    name: str
    data: dict[str, Any]
    is_system: bool
    owner_id: uuid.UUID | None
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UnitAssetCatalog(BaseModel):
    aircraftDb: list[dict[str, Any]] = Field(default_factory=list)
    airbaseDb: list[dict[str, Any]] = Field(default_factory=list)
    facilityDb: list[dict[str, Any]] = Field(default_factory=list)
    shipDb: list[dict[str, Any]] = Field(default_factory=list)
    weaponDb: list[dict[str, Any]] = Field(default_factory=list)


class UnitAssetImportRequest(UnitAssetCatalog):
    replace_existing: bool = True


class UnitAssetImportResult(BaseModel):
    created: int
    updated: int
    skipped: int
    assets: list[UnitAssetRead]
