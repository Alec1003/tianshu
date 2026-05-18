from __future__ import annotations

from fastapi import APIRouter, Request

from app.ai.model_checker import check_model_connectivity
from app.ai.models import (
    AICommandRequest,
    AICommandResponse,
    ModelCheckRequest,
    ModelCheckResponse,
)


router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/command", response_model=AICommandResponse)
def command(request: Request, payload: AICommandRequest) -> AICommandResponse:
    bridge = request.app.state.bridge
    execution = bridge.process_command(payload.command, payload.context)
    scenario = bridge.exported_scenario()

    if execution.status == "ok":
        message = "Command executed successfully."
    elif execution.status == "partial":
        message = "Command partially executed. Check skill call results."
    else:
        message = execution.error or "Command execution failed."

    return AICommandResponse(
        status=execution.status,
        message=message,
        execution=execution,
        scenario=scenario,
    )


@router.get("/skills")
def list_skills(request: Request) -> dict:
    bridge = request.app.state.bridge
    return {"skills": [definition.model_dump() for definition in bridge.skill_registry.definitions()]}


@router.post("/model/check", response_model=ModelCheckResponse)
def check_model(payload: ModelCheckRequest) -> ModelCheckResponse:
    return check_model_connectivity(payload)
