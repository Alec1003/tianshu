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
async def command(request: Request, payload: AICommandRequest) -> AICommandResponse:
    bridge = request.app.state.bridge
    execution = await bridge.process_command_async(payload.command, payload.context)
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


@router.get("/runtime/scenario")
def runtime_scenario(request: Request) -> dict:
    """Export the current in-memory runtime scenario as JSON.

    This is the **read-only** counterpart to the MCP ``runtime_*`` tools:
    the front-end (or any HTTP client) can poll this endpoint to grab the
    latest snapshot of the shared ``PanopticonRuntime`` that MCP / AI
    commands are mutating. The returned shape is identical to the
    ``scenario`` field in ``POST /api/ai/command`` responses, so
    ``game.loadScenario(JSON.stringify(response))`` works on the client.

    No auth required (aligns with ``/api/ai/command`` which is also open);
    add ``Depends(current_active_user)`` when multi-tenant auth is wired.
    """
    bridge = request.app.state.bridge
    return bridge.exported_scenario()


@router.get("/skills")
def list_skills(request: Request) -> dict:
    bridge = request.app.state.bridge
    return {"skills": [definition.model_dump() for definition in bridge.skill_registry.definitions()]}


@router.post("/model/check", response_model=ModelCheckResponse)
def check_model(payload: ModelCheckRequest) -> ModelCheckResponse:
    return check_model_connectivity(payload)
