"""Pydantic DTOs for /api/scenarios/* and /api/scenarios/{id}/aar."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------- Scenario ----------
class ScenarioBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class ScenarioCreate(ScenarioBase):
    # Whole scenario JSON. We accept ``dict`` here so clients can POST the
    # exact structure they currently dump via the export button.
    data: dict[str, Any]


class ScenarioUpdate(BaseModel):
    """All fields optional -- PATCH semantics."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    data: dict[str, Any] | None = None


class ScenarioListItem(BaseModel):
    """Light row for list endpoints; omits the heavy ``data`` blob."""

    id: str
    name: str
    description: str
    is_template: bool
    owner_id: str | None
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ScenarioDetail(ScenarioListItem):
    data: dict[str, Any]


# ---------- AAR ----------
class AarRecordCreate(BaseModel):
    outcome_reason: str = Field(..., max_length=40)
    winner_side_id: str = Field(default="", max_length=80)
    summary: dict[str, Any]
    ended_at: datetime


class AarRecordRead(BaseModel):
    id: str
    scenario_id: str | None
    owner_id: str | None
    outcome_reason: str
    winner_side_id: str
    summary: dict[str, Any]
    ended_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}
