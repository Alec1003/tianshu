"""Pydantic DTOs for /api/scenarios/* and /api/scenarios/{id}/aar."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

ScenarioStatus = str  # "draft" | "running" | "completed"
VALID_STATUSES = {"draft", "running", "completed"}


# ---------- Scenario ----------
class ScenarioBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    status: ScenarioStatus = Field(default="draft")


class ScenarioCreate(ScenarioBase):
    # Whole scenario JSON. We accept ``dict`` here so clients can POST the
    # exact structure they currently dump via the export button.
    data: dict[str, Any]


class ScenarioUpdate(BaseModel):
    """All fields optional -- PATCH semantics."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    data: dict[str, Any] | None = None
    status: ScenarioStatus | None = None


class ScenarioListItem(BaseModel):
    """Light row for list endpoints; omits the heavy ``data`` blob."""

    id: str
    name: str
    description: str
    is_template: bool
    owner_id: uuid.UUID | None
    version: int
    status: ScenarioStatus
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
    owner_id: uuid.UUID | None
    outcome_reason: str
    winner_side_id: str
    summary: dict[str, Any]
    ended_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- Training score ----------
class TrainingScoreDimension(BaseModel):
    key: str
    label: str
    score: int = Field(..., ge=0, le=100)
    weight: float = Field(..., ge=0, le=1)
    summary: str
    evidence: list[str] = Field(default_factory=list)


class TrainingScoreResponse(BaseModel):
    scenario_id: str
    runtime_scenario_id: str | None = None
    generated_at: datetime
    overall_score: int = Field(..., ge=0, le=100)
    grade: str
    confidence: str
    dimensions: list[TrainingScoreDimension]
    metrics: dict[str, Any] = Field(default_factory=dict)
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
