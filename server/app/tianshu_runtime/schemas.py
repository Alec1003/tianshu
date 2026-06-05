from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RuntimeUnitChange(BaseModel):
    change_type: Literal["added", "removed", "updated"]
    unit_type: str
    unit_id: str
    name: str = ""
    side_id: str = ""
    fields: dict[str, dict[str, Any]] = Field(default_factory=dict)
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


class RuntimeTimelineEventRead(BaseModel):
    id: str
    owner_id: uuid.UUID
    scenario_id: str | None = None
    event_type: str
    category: str
    action: str
    actor: str
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    unit_changes: list[RuntimeUnitChange] = Field(default_factory=list)
    current_time: int | None = None
    proposal_id: str | None = None
    aar_record_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RuntimeTimelineResponse(BaseModel):
    events: list[RuntimeTimelineEventRead] = Field(default_factory=list)
