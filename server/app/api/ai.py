from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.ai.model_checker import check_model_connectivity
from app.ai.models import (
    AICommandRequest,
    AICommandResponse,
    CommandApprovalResponse,
    CommandProposalListResponse,
    ModelCheckRequest,
    ModelCheckResponse,
    RuntimeAddWeaponRequest,
    RuntimeAttackRequest,
    RuntimeCreateSideRequest,
    RuntimeDeleteWeaponRequest,
    RuntimeDeployUnitRequest,
    RuntimeLoadScenarioRequest,
    RuntimeMoveUnitRequest,
    RuntimePatrolMissionRequest,
    RuntimeSetCurrentSideRequest,
    RuntimeSetUnitPositionRequest,
    RuntimeSnapshotResponse,
    RuntimeStrikeMissionRequest,
    RuntimeStepRequest,
    RuntimeUpdateSideRequest,
    RuntimeUpdateUnitRequest,
    RuntimeUpdateWeaponQuantityRequest,
)
from app.aicc_runtime.visibility import compute_runtime_visibility
from app.auth.models import User
from app.auth.users import current_active_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/ai",
    tags=["ai"],
    dependencies=[Depends(current_active_user)],
)


def _bridge_for_user(request: Request, user: User) -> Any:
    registry = getattr(request.app.state, "bridge_registry", None)
    if registry is not None:
        return registry.get_bridge_for_user(user)
    return request.app.state.bridge


def _runtime_for_user(request: Request, user: User) -> Any:
    bridge = _bridge_for_user(request, user)
    runtime = getattr(bridge, "runtime", None)
    if runtime is None:
        raise RuntimeError("AI bridge does not expose a runtime")
    return runtime


def _runtime_outcome_payload(runtime: Any) -> dict[str, Any]:
    scenario = runtime.game.current_scenario
    start = int(getattr(scenario, "start_time", 0) or 0)
    duration = int(getattr(scenario, "duration", 0) or 0)
    current = int(getattr(scenario, "current_time", start) or start)
    raw_outcome = getattr(runtime.game, "game_outcome", {}) or {}
    ended = bool(raw_outcome.get("ended", False))
    winner_side_id = (
        raw_outcome.get("winner_side_id") or raw_outcome.get("winnerSideId") or None
    )
    return {
        "ended": ended,
        "winner_side_id": winner_side_id if ended else None,
        "reason": raw_outcome.get("reason", "") or "",
        "ended_at": int(raw_outcome.get("ended_at") or raw_outcome.get("endedAt") or 0),
        "objective_destroyed": getattr(scenario, "last_objective_destroyed", None),
        "time_up": duration > 0 and current >= start + duration,
    }


def _runtime_snapshot(
    request: Request,
    user: User,
    *,
    action: str = "",
    state: dict[str, Any] | None = None,
) -> RuntimeSnapshotResponse:
    bridge = _bridge_for_user(request, user)
    runtime = getattr(bridge, "runtime", None)
    if runtime is None:
        raise RuntimeError("AI bridge does not expose a runtime")
    scenario = runtime.game.current_scenario
    start = int(getattr(scenario, "start_time", 0) or 0)
    duration = int(getattr(scenario, "duration", 0) or 0)
    current = int(getattr(scenario, "current_time", start) or start)
    paused = bool(getattr(runtime.game, "scenario_paused", True))
    return RuntimeSnapshotResponse(
        action=action,
        state=state or {},
        running=not paused,
        paused=paused,
        current_time=current,
        elapsed=max(0, current - start),
        duration_left=max(0, start + duration - current),
        outcome=_runtime_outcome_payload(runtime),
        scenario=bridge.exported_scenario(),
        visibility=compute_runtime_visibility(
            scenario, getattr(runtime.game, "current_side_id", "")
        ),
    )


def _runtime_value_error(exc: ValueError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=str(exc),
    )


@router.post("/command", response_model=AICommandResponse)
async def command(
    request: Request,
    payload: AICommandRequest,
    user: User = Depends(current_active_user),
) -> AICommandResponse:
    bridge = _bridge_for_user(request, user)
    if hasattr(bridge, "propose_command_async"):
        execution, proposals = await bridge.propose_command_async(
            payload.command,
            payload.context,
        )
    else:
        execution = await bridge.process_command_async(payload.command, payload.context)
        proposals = []
    scenario = bridge.exported_scenario()

    if execution.status == "ok":
        message = (
            "Command proposal created. Human approval is required before execution."
            if proposals
            else "Command executed successfully."
        )
    elif execution.status == "partial":
        message = "Command partially executed. Check skill call results."
    else:
        message = execution.error or "Command execution failed."

    return AICommandResponse(
        status=execution.status,
        message=message,
        execution=execution,
        scenario=scenario,
        proposals=proposals,
    )


def _approval_queue_for_user(request: Request, user: User) -> Any:
    bridge = _bridge_for_user(request, user)
    queue = getattr(bridge, "command_approvals", None)
    if queue is None:
        raise RuntimeError("AI bridge does not expose command approvals")
    return queue


@router.get("/command/proposals", response_model=CommandProposalListResponse)
def list_command_proposals(
    request: Request,
    status_filter: str | None = None,
    limit: int = 50,
    user: User = Depends(current_active_user),
) -> CommandProposalListResponse:
    queue = _approval_queue_for_user(request, user)
    return CommandProposalListResponse(
        proposals=queue.list_proposals(status=status_filter, limit=limit)
    )


@router.post(
    "/command/proposals/{proposal_id}/approve",
    response_model=CommandApprovalResponse,
)
def approve_command_proposal(
    request: Request,
    proposal_id: str,
    user: User = Depends(current_active_user),
) -> CommandApprovalResponse:
    queue = _approval_queue_for_user(request, user)
    try:
        proposal = queue.approve_and_execute(proposal_id)
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    snapshot = _runtime_snapshot(
        request,
        user,
        action="approve_command_proposal",
        state={"proposalId": proposal.id, "proposalStatus": proposal.status},
    )
    return CommandApprovalResponse(proposal=proposal, snapshot=snapshot)


@router.post(
    "/command/proposals/{proposal_id}/reject",
    response_model=CommandApprovalResponse,
)
def reject_command_proposal(
    request: Request,
    proposal_id: str,
    user: User = Depends(current_active_user),
) -> CommandApprovalResponse:
    queue = _approval_queue_for_user(request, user)
    try:
        proposal = queue.reject(proposal_id)
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    return CommandApprovalResponse(proposal=proposal, snapshot=None)


@router.get("/runtime/scenario")
def runtime_scenario(
    request: Request,
    user: User = Depends(current_active_user),
) -> dict:
    """Export the current in-memory runtime scenario as JSON.

    This is the **read-only** counterpart to the MCP ``runtime_*`` tools:
    the front-end (or any HTTP client) can poll this endpoint to grab the
    latest snapshot of the shared ``AICCRuntime`` that MCP / AI
    commands are mutating. The returned shape is identical to the
    ``scenario`` field in ``POST /api/ai/command`` responses, so
    ``game.loadScenario(JSON.stringify(response))`` works on the client.

    Authentication is enforced at the router level because this shared
    runtime can contain user-loaded scenario state and AI/MCP mutations.
    """
    bridge = _bridge_for_user(request, user)
    return bridge.exported_scenario()


@router.get("/runtime", response_model=RuntimeSnapshotResponse)
def runtime_snapshot(
    request: Request,
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    """Return the authoritative backend runtime snapshot."""
    return _runtime_snapshot(request, user, action="snapshot")


@router.put("/runtime/scenario", response_model=RuntimeSnapshotResponse)
def runtime_load_scenario(
    request: Request,
    payload: RuntimeLoadScenarioRequest,
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    """Load a frontend-shaped scenario JSON into the user's backend runtime."""
    runtime = _runtime_for_user(request, user)
    state = runtime.load_scenario_from_json(json.dumps(payload.scenario))
    return _runtime_snapshot(request, user, action="load_scenario", state=state)


@router.post("/runtime/start", response_model=RuntimeSnapshotResponse)
def runtime_start(
    request: Request,
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = _runtime_for_user(request, user)
    state = runtime.start_simulation()
    return _runtime_snapshot(request, user, action="start", state=state)


@router.post("/runtime/pause", response_model=RuntimeSnapshotResponse)
def runtime_pause(
    request: Request,
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = _runtime_for_user(request, user)
    state = runtime.pause_simulation()
    return _runtime_snapshot(request, user, action="pause", state=state)


@router.post("/runtime/reset", response_model=RuntimeSnapshotResponse)
def runtime_reset(
    request: Request,
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = _runtime_for_user(request, user)
    state = runtime.reset_simulation()
    return _runtime_snapshot(request, user, action="reset", state=state)


@router.post("/runtime/step", response_model=RuntimeSnapshotResponse)
def runtime_step(
    request: Request,
    payload: RuntimeStepRequest,
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = _runtime_for_user(request, user)
    state = runtime.step_simulation(payload.steps)
    return _runtime_snapshot(request, user, action="step", state=state)


@router.post("/runtime/attack", response_model=RuntimeSnapshotResponse)
def runtime_attack(
    request: Request,
    payload: RuntimeAttackRequest,
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = _runtime_for_user(request, user)
    try:
        state = runtime.attack_unit(
            attacker_type=payload.attacker_type,
            attacker_id=payload.attacker_id,
            target_id=payload.target_id,
            weapon_id=payload.weapon_id,
            weapon_quantity=payload.weapon_quantity,
            auto=payload.auto,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return _runtime_snapshot(request, user, action="attack", state=state)


@router.post("/runtime/units", response_model=RuntimeSnapshotResponse)
def runtime_deploy_unit(
    request: Request,
    payload: RuntimeDeployUnitRequest,
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = _runtime_for_user(request, user)
    try:
        if payload.unit_type == "aircraft":
            state = runtime.deploy_aircraft(
                payload.class_name,
                payload.latitude,
                payload.longitude,
                side=payload.side,
                name=payload.name,
                altitude=payload.altitude or 10000.0,
            )
        elif payload.unit_type == "ship":
            state = runtime.deploy_ship(
                payload.class_name,
                payload.latitude,
                payload.longitude,
                side=payload.side,
                name=payload.name,
            )
        elif payload.unit_type == "facility":
            state = runtime.deploy_facility(
                payload.class_name,
                payload.latitude,
                payload.longitude,
                side=payload.side,
                name=payload.name,
            )
        elif payload.unit_type == "airbase":
            state = runtime.deploy_airbase(
                payload.class_name,
                payload.latitude,
                payload.longitude,
                side=payload.side,
                name=payload.name,
            )
        else:
            state = runtime.deploy_reference_point(
                payload.name or payload.class_name,
                payload.latitude,
                payload.longitude,
                side=payload.side,
            )
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    return _runtime_snapshot(request, user, action="deploy_unit", state=state)


@router.delete(
    "/runtime/units/{unit_type}/{unit_id}",
    response_model=RuntimeSnapshotResponse,
)
def runtime_delete_unit(
    request: Request,
    unit_type: str,
    unit_id: str,
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = _runtime_for_user(request, user)
    try:
        state = runtime.delete_unit(unit_type, unit_id)
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    return _runtime_snapshot(request, user, action="delete_unit", state=state)


@router.patch("/runtime/units/route", response_model=RuntimeSnapshotResponse)
def runtime_move_unit(
    request: Request,
    payload: RuntimeMoveUnitRequest,
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = _runtime_for_user(request, user)
    try:
        state = runtime.move_unit(
            payload.unit_type,
            payload.unit_id,
            payload.route,
        )
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    return _runtime_snapshot(request, user, action="move_unit", state=state)


@router.patch("/runtime/units/position", response_model=RuntimeSnapshotResponse)
def runtime_set_unit_position(
    request: Request,
    payload: RuntimeSetUnitPositionRequest,
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = _runtime_for_user(request, user)
    try:
        state = runtime.set_unit_position(
            payload.unit_type,
            payload.unit_id,
            payload.latitude,
            payload.longitude,
        )
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    return _runtime_snapshot(request, user, action="set_unit_position", state=state)


@router.patch("/runtime/units", response_model=RuntimeSnapshotResponse)
def runtime_update_unit(
    request: Request,
    payload: RuntimeUpdateUnitRequest,
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = _runtime_for_user(request, user)
    try:
        state = runtime.update_unit_state(
            payload.unit_type,
            payload.unit_id,
            payload.patch,
        )
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    return _runtime_snapshot(request, user, action="update_unit", state=state)


@router.patch("/runtime/side/current", response_model=RuntimeSnapshotResponse)
def runtime_set_current_side(
    request: Request,
    payload: RuntimeSetCurrentSideRequest,
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = _runtime_for_user(request, user)
    try:
        state = runtime.set_current_side(payload.side)
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    return _runtime_snapshot(request, user, action="set_current_side", state=state)


@router.post("/runtime/sides", response_model=RuntimeSnapshotResponse)
def runtime_create_side(
    request: Request,
    payload: RuntimeCreateSideRequest,
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = _runtime_for_user(request, user)
    state = runtime.add_side(
        payload.name,
        payload.color,
        payload.hostiles,
        payload.allies,
        payload.doctrine,
    )
    return _runtime_snapshot(request, user, action="create_side", state=state)


@router.patch("/runtime/sides/{side_id}", response_model=RuntimeSnapshotResponse)
def runtime_update_side(
    request: Request,
    side_id: str,
    payload: RuntimeUpdateSideRequest,
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = _runtime_for_user(request, user)
    try:
        state = runtime.update_side(
            side_id,
            payload.name,
            payload.color,
            payload.hostiles,
            payload.allies,
            payload.doctrine,
        )
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    return _runtime_snapshot(request, user, action="update_side", state=state)


@router.delete("/runtime/sides/{side_id}", response_model=RuntimeSnapshotResponse)
def runtime_delete_side(
    request: Request,
    side_id: str,
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = _runtime_for_user(request, user)
    try:
        state = runtime.delete_side(side_id)
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    return _runtime_snapshot(request, user, action="delete_side", state=state)


@router.delete("/runtime/missions/{mission_id}", response_model=RuntimeSnapshotResponse)
def runtime_delete_mission(
    request: Request,
    mission_id: str,
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = _runtime_for_user(request, user)
    state = runtime.delete_mission(mission_id)
    return _runtime_snapshot(request, user, action="delete_mission", state=state)


@router.post("/runtime/missions/patrol", response_model=RuntimeSnapshotResponse)
def runtime_create_patrol_mission(
    request: Request,
    payload: RuntimePatrolMissionRequest,
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = _runtime_for_user(request, user)
    state = runtime.create_patrol_mission(
        payload.name,
        payload.assigned_unit_ids,
        payload.reference_point_ids,
    )
    return _runtime_snapshot(request, user, action="create_patrol_mission", state=state)


@router.patch(
    "/runtime/missions/patrol/{mission_id}",
    response_model=RuntimeSnapshotResponse,
)
def runtime_update_patrol_mission(
    request: Request,
    mission_id: str,
    payload: RuntimePatrolMissionRequest,
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = _runtime_for_user(request, user)
    try:
        state = runtime.update_patrol_mission(
            mission_id,
            payload.name,
            payload.assigned_unit_ids,
            payload.reference_point_ids,
        )
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    return _runtime_snapshot(request, user, action="update_patrol_mission", state=state)


@router.post("/runtime/missions/strike", response_model=RuntimeSnapshotResponse)
def runtime_create_strike_mission(
    request: Request,
    payload: RuntimeStrikeMissionRequest,
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = _runtime_for_user(request, user)
    state = runtime.create_strike_mission(
        payload.name,
        payload.assigned_unit_ids,
        payload.assigned_target_ids,
    )
    return _runtime_snapshot(request, user, action="create_strike_mission", state=state)


@router.patch(
    "/runtime/missions/strike/{mission_id}",
    response_model=RuntimeSnapshotResponse,
)
def runtime_update_strike_mission(
    request: Request,
    mission_id: str,
    payload: RuntimeStrikeMissionRequest,
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = _runtime_for_user(request, user)
    try:
        state = runtime.update_strike_mission(
            mission_id,
            payload.name,
            payload.assigned_unit_ids,
            payload.assigned_target_ids,
        )
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    return _runtime_snapshot(request, user, action="update_strike_mission", state=state)


@router.post("/runtime/weapons", response_model=RuntimeSnapshotResponse)
def runtime_add_weapon(
    request: Request,
    payload: RuntimeAddWeaponRequest,
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = _runtime_for_user(request, user)
    try:
        state = runtime.add_weapon_to_unit(
            payload.unit_type,
            payload.unit_id,
            payload.class_name,
            payload.speed,
            payload.max_fuel,
            payload.fuel_rate,
            payload.range,
            payload.lethality,
            payload.quantity,
        )
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    return _runtime_snapshot(request, user, action="add_weapon", state=state)


@router.delete("/runtime/weapons", response_model=RuntimeSnapshotResponse)
def runtime_delete_weapon(
    request: Request,
    payload: RuntimeDeleteWeaponRequest,
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = _runtime_for_user(request, user)
    try:
        state = runtime.delete_weapon_from_unit(
            payload.unit_type,
            payload.unit_id,
            payload.weapon_id,
        )
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    return _runtime_snapshot(request, user, action="delete_weapon", state=state)


@router.patch("/runtime/weapons/quantity", response_model=RuntimeSnapshotResponse)
def runtime_update_weapon_quantity(
    request: Request,
    payload: RuntimeUpdateWeaponQuantityRequest,
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = _runtime_for_user(request, user)
    try:
        state = runtime.update_weapon_quantity(
            payload.unit_type,
            payload.unit_id,
            payload.weapon_id,
            payload.increment,
        )
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    return _runtime_snapshot(request, user, action="update_weapon_quantity", state=state)


@router.get("/skills")
def list_skills(
    request: Request,
    user: User = Depends(current_active_user),
) -> dict:
    bridge = _bridge_for_user(request, user)
    return {"skills": [definition.model_dump() for definition in bridge.skill_registry.definitions()]}


@router.post("/model/check", response_model=ModelCheckResponse)
def check_model(payload: ModelCheckRequest) -> ModelCheckResponse:
    return check_model_connectivity(payload)


# ─── S4: Streaming Chat (Pydantic AI) ─────────────────────────────────────────


def _read_model_override_from_headers(
    request: Request,
) -> tuple[str, str, str, str]:
    """Pull per-request model override fields from custom headers.

    The AI sidebar sends ``X-AICC-Model-{Provider,Name,Api-Key,Base-Url}``
    whenever the user has filled in a model config. Empty / missing
    headers fall back to "" so the caller can decide between override and
    the env-configured global agent.
    """
    return (
        (request.headers.get("x-aicc-model-provider") or "").strip(),
        (request.headers.get("x-aicc-model-name") or "").strip(),
        (request.headers.get("x-aicc-model-api-key") or "").strip(),
        (request.headers.get("x-aicc-model-base-url") or "").strip(),
    )


def _read_chat_mode_from_headers(request: Request) -> str:
    mode = (request.headers.get("x-aicc-chat-mode") or "command").strip().lower()
    return "ask" if mode == "ask" else "command"


@router.post("/chat")
async def chat(
    request: Request,
    user: User = Depends(current_active_user),
) -> StreamingResponse:
    """Streaming chat endpoint powered by pydantic-ai.

    Accepts Vercel AI SDK compatible request body (messages array).
    Returns SSE stream of text deltas + tool-invocation chunks that any
    AI-SDK–compatible frontend (``useChat`` from ``@ai-sdk/react``) can
    consume out of the box.

    Model override: when the request carries
    ``X-AICC-Model-{Provider,Name,Api-Key,Base-Url}`` headers (i.e. the
    user filled in the sidebar Settings panel) we build a one-off agent
    so the user-supplied credentials/provider actually drive the stream.
    Otherwise we fall back to the env-configured ``bridge.pydantic_agent``.

    Falls back to a non-streaming JSON error if no LLM is configured at all.
    """
    from pydantic_ai.ui.vercel_ai import VercelAIAdapter  # noqa: PLC0415

    from app.ai.pydantic_agent import (  # noqa: PLC0415
        AgentDeps,
        build_agent,
        can_build_model_override,
    )

    bridge = _bridge_for_user(request, user)
    chat_mode = _read_chat_mode_from_headers(request)

    # Per-request model override via headers (set by AI sidebar useChat).
    provider, model_name, api_key, base_url = _read_model_override_from_headers(request)
    per_request_agent = None
    if can_build_model_override(provider, model_name, api_key, base_url):
        model_id = f"{provider}:{model_name}"
        try:
            per_request_agent = build_agent(
                model_id=model_id,
                api_key=api_key,
                base_url=base_url,
                enable_tools=chat_mode == "command",
            )
        except Exception as exc:  # pragma: no cover - depends on SDK install
            logger.warning(
                "chat: per-request agent build failed (%s): %s", model_id, exc
            )

    fallback_agent = (
        bridge.pydantic_agent
        if chat_mode == "command"
        else getattr(bridge, "pydantic_ask_agent", None)
    )
    agent = per_request_agent or fallback_agent
    if agent is None:
        return StreamingResponse(
            iter(
                [
                    json.dumps(
                        {
                            "error": (
                                "No LLM configured. Either set AICC_LLM_MODEL + "
                                "AICC_LLM_API_KEY on the server, or fill the "
                                "model section in the AI sidebar (Settings)."
                            )
                        }
                    )
                ]
            ),
            status_code=503,
            media_type="application/json",
        )

    deps = AgentDeps(
        registry=bridge.skill_registry,
        chat_mode=chat_mode,
        approval_queue=(
            getattr(bridge, "command_approvals", None)
            if chat_mode == "command"
            else None
        ),
    )
    return await VercelAIAdapter.dispatch_request(
        request,
        agent=agent,
        deps=deps,
    )
