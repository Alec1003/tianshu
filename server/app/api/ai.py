from __future__ import annotations

import asyncio
import json
import logging
import shlex
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.model_checker import check_model_connectivity
from app.ai.custom_skill_store import (
    CustomSkillNotFoundError,
    CustomSkillStore,
    CustomSkillStoreError,
)
from app.ai.internal_skills import build_internal_skill_steps
from app.ai.models import (
    AICommandRequest,
    AICommandResponse,
    BuiltinMcpToolsResponse,
    CommandApprovalResponse,
    CommandProposalListResponse,
    CustomSkillCreateRequest,
    CustomSkillListResponse,
    CustomSkillRead,
    CustomSkillUpdateRequest,
    ExternalMcpValidateRequest,
    ExternalMcpValidateResponse,
    InternalSkillProposalRequest,
    InternalSkillProposalResponse,
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
from app.ai.mcp_client import MCPClientSkeleton, MCPServerConfig
from app.ai.command_service import (
    CommandProposalNotFoundError,
    get_command_proposal,
    list_command_proposals as list_persisted_command_proposals,
    save_command_proposal,
)
from app.ai.model_config_service import (
    AIModelProviderConfigList,
    AIModelProviderConfigRead,
    AIModelProviderConfigUpdate,
    list_model_provider_configs,
    resolve_stored_model_credentials,
    upsert_model_provider_config,
)
from app.tianshu_runtime.persistence import (
    ensure_runtime_state_loaded,
    save_runtime_state,
)
from app.tianshu_runtime.schemas import RuntimeTimelineResponse
from app.tianshu_runtime.timeline import (
    list_runtime_events,
    record_runtime_event,
    runtime_scenario_id,
)
from app.tianshu_runtime.visibility import compute_runtime_visibility
from app.auth.models import User
from app.auth.users import current_active_user
from app.db.session import async_session_maker, get_async_session
from app.unit_assets.service import find_accessible_unit_asset_by_name

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/ai",
    tags=["ai"],
    dependencies=[Depends(current_active_user)],
)

RUNTIME_SCENARIO_HEADER = "x-tianshu-scenario-id"
HEADER_PREFIX = "x-tianshu-"
LEGACY_HEADER_PREFIX = "x-" + "ai" + "cc" + "-"


def _legacy_header_name(name: str) -> str:
    if name.startswith(HEADER_PREFIX):
        return LEGACY_HEADER_PREFIX + name[len(HEADER_PREFIX) :]
    return LEGACY_HEADER_PREFIX + name


def _header_value(request: Request, name: str) -> str:
    return (
        request.headers.get(name)
        or request.headers.get(_legacy_header_name(name))
        or ""
    )


def _runtime_context_from_request(request: Request) -> str | None:
    return _header_value(request, RUNTIME_SCENARIO_HEADER).strip() or None


def _bridge_for_user(request: Request, user: User) -> Any:
    registry = getattr(request.app.state, "bridge_registry", None)
    if registry is not None:
        return registry.get_bridge_for_user(
            user,
            scenario_id=_runtime_context_from_request(request),
        )
    return request.app.state.bridge


def _custom_skill_store(request: Request) -> CustomSkillStore:
    store = getattr(request.app.state, "custom_skill_store", None)
    if store is not None:
        return store
    return CustomSkillStore.from_settings()


def _custom_skill_created_by(user: User) -> str:
    return str(getattr(user, "email", None) or getattr(user, "id", "operator"))


async def _bridge_for_user_loaded(
    request: Request,
    user: User,
    session: AsyncSession,
) -> Any:
    bridge = _bridge_for_user(request, user)
    runtime = getattr(bridge, "runtime", None)
    if runtime is not None:
        await ensure_runtime_state_loaded(
            session,
            user,
            runtime,
            scenario_id=_runtime_context_from_request(request),
        )
    return bridge


async def _runtime_for_user_loaded(
    request: Request,
    user: User,
    session: AsyncSession,
) -> Any:
    bridge = await _bridge_for_user_loaded(request, user, session)
    runtime = getattr(bridge, "runtime", None)
    if runtime is None:
        raise RuntimeError("AI bridge does not expose a runtime")
    return runtime


async def _persisted_runtime_snapshot(
    request: Request,
    user: User,
    session: AsyncSession,
    runtime: Any,
    *,
    action: str,
    state: dict[str, Any] | None = None,
    event_type: str | None = None,
    actor: str = "operator",
    before_scenario: dict[str, Any] | None = None,
    event_payload: dict[str, Any] | None = None,
) -> RuntimeSnapshotResponse:
    await save_runtime_state(
        session,
        user,
        runtime,
        scenario_id=_runtime_context_from_request(request),
    )
    snapshot = _runtime_snapshot(request, user, action=action, state=state)
    if event_type:
        await record_runtime_event(
            session,
            user,
            event_type=event_type,
            action=action,
            actor=actor,
            summary=_runtime_event_summary(action, state or {}),
            payload={"state": state or {}, **(event_payload or {})},
            runtime=runtime,
            before_scenario=before_scenario,
            after_scenario=snapshot.scenario,
        )
    return snapshot


def _runtime_event_baseline(runtime: Any) -> dict[str, Any] | None:
    try:
        return runtime.get_exported_scenario()
    except AttributeError:
        return None


def _runtime_event_type(action: str) -> str:
    if action == "step":
        return "runtime.step"
    if action in {"start", "pause", "reset"}:
        return f"runtime.{action}"
    if action == "load_scenario":
        return "scenario.loaded"
    return f"runtime.{action}"


def _runtime_event_summary(action: str, state: dict[str, Any]) -> str:
    if action == "step":
        return f"仿真推进 {state.get('steps', state.get('requestedSteps', 0))} 秒"
    if action == "start":
        return "推演开始"
    if action == "pause":
        return "推演暂停"
    if action == "reset":
        return "推演重置"
    if action == "load_scenario":
        return "加载运行想定"
    if action == "deploy_unit":
        return f"部署单位 {state.get('name') or state.get('unitId') or ''}".strip()
    if action == "delete_unit":
        return f"删除单位 {state.get('unitId') or ''}".strip()
    if action == "move_unit":
        return f"单位机动 {state.get('unitId') or ''}".strip()
    if action == "attack":
        return f"攻击目标 {state.get('targetId') or ''}".strip()
    return action.replace("_", " ")


def _proposal_execution_event_type(proposal: Any) -> str:
    if not getattr(proposal, "steps", None):
        return "runtime.command_execution"
    skills = [step.skill for step in proposal.steps]
    if len(skills) == 1:
        skill = skills[0]
        mapping = {
            "simulation_start": "runtime.start",
            "simulation_pause": "runtime.pause",
            "simulation_reset": "runtime.reset",
            "simulation_stop": "runtime.stop",
            "simulation_step": "runtime.step",
            "load_scenario_snapshot": "scenario.loaded",
            "move_unit": "runtime.move_unit",
            "delete_unit": "runtime.delete_unit",
            "update_unit_state": "runtime.update_unit",
            "trigger_tactical_event": "runtime.tactical_event",
            "update_situation_layer": "runtime.situation_layer",
        }
        if skill.startswith("deploy_"):
            return "runtime.deploy_unit"
        return mapping.get(skill, "runtime.command_execution")
    return "runtime.command_execution"


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
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> AICommandResponse:
    bridge = await _bridge_for_user_loaded(request, user, session)
    runtime = getattr(bridge, "runtime", None)
    before_scenario = _runtime_event_baseline(runtime) if runtime is not None else None
    if hasattr(bridge, "propose_command_async"):
        execution, proposals = await bridge.propose_command_async(
            payload.command,
            payload.context,
        )
    else:
        execution = await bridge.process_command_async(payload.command, payload.context)
        proposals = []
    if proposals:
        saved_proposals = []
        for proposal in proposals:
            saved = await save_command_proposal(
                session,
                user,
                proposal,
                scenario_id=_runtime_context_from_request(request),
            )
            saved_proposals.append(saved)
            await record_runtime_event(
                session,
                user,
                event_type="command.proposed",
                action="proposal_created",
                actor=saved.source,
                summary=f"命令提案：{saved.command}",
                payload=saved.model_dump(mode="json"),
                runtime=runtime,
                proposal_id=saved.id,
            )
        proposals = saved_proposals
    elif execution.status == "ok":
        if runtime is not None:
            await save_runtime_state(
                session,
                user,
                runtime,
                scenario_id=_runtime_context_from_request(request),
            )
            await record_runtime_event(
                session,
                user,
                event_type="command.executed",
                action="command",
                actor="ai",
                summary=f"命令执行：{payload.command}",
                payload=execution.model_dump(mode="json"),
                runtime=runtime,
                before_scenario=before_scenario,
            )
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
async def list_command_proposals(
    request: Request,
    status_filter: str | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> CommandProposalListResponse:
    await _bridge_for_user_loaded(request, user, session)
    _approval_queue_for_user(request, user)
    return CommandProposalListResponse(
        proposals=await list_persisted_command_proposals(
            session,
            user,
            scenario_id=_runtime_context_from_request(request),
            status=status_filter,
            limit=limit,
        )
    )


@router.post(
    "/command/proposals/{proposal_id}/approve",
    response_model=CommandApprovalResponse,
)
async def approve_command_proposal(
    request: Request,
    proposal_id: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> CommandApprovalResponse:
    runtime = await _runtime_for_user_loaded(request, user, session)
    queue = _approval_queue_for_user(request, user)
    before_scenario = _runtime_event_baseline(runtime)
    try:
        persisted = await get_command_proposal(
            session,
            user,
            proposal_id,
            scenario_id=_runtime_context_from_request(request),
        )
        proposal = queue.approve_and_execute_loaded(persisted)
        proposal = await save_command_proposal(
            session,
            user,
            proposal,
            scenario_id=_runtime_context_from_request(request),
        )
        await save_runtime_state(
            session,
            user,
            runtime,
            scenario_id=_runtime_context_from_request(request),
        )
    except CommandProposalNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Command proposal not found.",
        ) from exc
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    snapshot = _runtime_snapshot(
        request,
        user,
        action="approve_command_proposal",
        state={"proposalId": proposal.id, "proposalStatus": proposal.status},
    )
    await record_runtime_event(
        session,
        user,
        event_type="command.approved",
        action="approve_command_proposal",
        actor="operator",
        summary=f"审批通过：{proposal.command}",
        payload=proposal.model_dump(mode="json"),
        runtime=runtime,
        proposal_id=proposal.id,
    )
    await record_runtime_event(
        session,
        user,
        event_type=_proposal_execution_event_type(proposal),
        action="approved_execution",
        actor=proposal.source,
        summary=f"执行审批命令：{proposal.command}",
        payload=proposal.model_dump(mode="json"),
        runtime=runtime,
        before_scenario=before_scenario,
        after_scenario=snapshot.scenario,
        proposal_id=proposal.id,
    )
    return CommandApprovalResponse(proposal=proposal, snapshot=snapshot)


@router.post(
    "/command/proposals/{proposal_id}/reject",
    response_model=CommandApprovalResponse,
)
async def reject_command_proposal(
    request: Request,
    proposal_id: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> CommandApprovalResponse:
    await _bridge_for_user_loaded(request, user, session)
    queue = _approval_queue_for_user(request, user)
    try:
        persisted = await get_command_proposal(
            session,
            user,
            proposal_id,
            scenario_id=_runtime_context_from_request(request),
        )
        proposal = queue.reject_loaded(persisted)
        proposal = await save_command_proposal(
            session,
            user,
            proposal,
            scenario_id=_runtime_context_from_request(request),
        )
    except CommandProposalNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Command proposal not found.",
        ) from exc
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    await record_runtime_event(
        session,
        user,
        event_type="command.rejected",
        action="reject_command_proposal",
        actor="operator",
        summary=f"审批驳回：{proposal.command}",
        payload=proposal.model_dump(mode="json"),
        runtime=getattr(_bridge_for_user(request, user), "runtime", None),
        proposal_id=proposal.id,
    )
    return CommandApprovalResponse(proposal=proposal, snapshot=None)


@router.post(
    "/internal-skills/proposals",
    response_model=InternalSkillProposalResponse,
)
async def create_internal_skill_proposal(
    request: Request,
    payload: InternalSkillProposalRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> InternalSkillProposalResponse:
    bridge = await _bridge_for_user_loaded(request, user, session)
    queue = getattr(bridge, "command_approvals", None)
    if queue is None:
        raise RuntimeError("AI bridge does not expose command approvals")
    try:
        steps = build_internal_skill_steps(bridge.runtime, payload.draft)
        proposal = queue.create_proposal(
            command=payload.command or payload.draft.name,
            steps=steps,
            source="internal_skill",
        )
        saved = await save_command_proposal(
            session,
            user,
            proposal,
            scenario_id=_runtime_context_from_request(request),
        )
        queue.hydrate(saved)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    await record_runtime_event(
        session,
        user,
        event_type="command.proposed",
        action="internal_skill_proposal_created",
        actor=saved.source,
        summary=f"内部战术技能提案：{payload.draft.name}",
        payload={"draft": payload.draft.model_dump(mode="json"), "proposal": saved.model_dump(mode="json")},
        runtime=getattr(bridge, "runtime", None),
        proposal_id=saved.id,
    )
    return InternalSkillProposalResponse(draft=payload.draft, proposal=saved)


@router.get("/runtime/scenario")
async def runtime_scenario(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict:
    """Export the current in-memory runtime scenario as JSON.

    This is the **read-only** counterpart to the MCP ``runtime_*`` tools:
    the front-end (or any HTTP client) can poll this endpoint to grab the
    latest snapshot of the shared ``TianShuRuntime`` that MCP / AI
    commands are mutating. The returned shape is identical to the
    ``scenario`` field in ``POST /api/ai/command`` responses, so
    ``game.loadScenario(JSON.stringify(response))`` works on the client.

    Authentication is enforced at the router level because this shared
    runtime can contain user-loaded scenario state and AI/MCP mutations.
    """
    bridge = await _bridge_for_user_loaded(request, user, session)
    return bridge.exported_scenario()


@router.get("/runtime", response_model=RuntimeSnapshotResponse)
async def runtime_snapshot(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    """Return the authoritative backend runtime snapshot."""
    await _bridge_for_user_loaded(request, user, session)
    return _runtime_snapshot(request, user, action="snapshot")


@router.get("/runtime/timeline", response_model=RuntimeTimelineResponse)
async def runtime_timeline(
    request: Request,
    scenario_id: str | None = None,
    event_type: str | None = None,
    category: str | None = None,
    limit: int = 200,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeTimelineResponse:
    bridge = await _bridge_for_user_loaded(request, user, session)
    effective_scenario_id = scenario_id
    if effective_scenario_id is None:
        effective_scenario_id = runtime_scenario_id(bridge.exported_scenario())
    events = await list_runtime_events(
        session,
        user,
        scenario_id=effective_scenario_id,
        event_type=event_type,
        category=category,
        limit=limit,
    )
    return RuntimeTimelineResponse(events=list(events))


@router.put("/runtime/scenario", response_model=RuntimeSnapshotResponse)
async def runtime_load_scenario(
    request: Request,
    payload: RuntimeLoadScenarioRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    """Load a frontend-shaped scenario JSON into the user's backend runtime."""
    runtime = await _runtime_for_user_loaded(request, user, session)
    before_scenario = _runtime_event_baseline(runtime)
    state = runtime.load_scenario_from_json(json.dumps(payload.scenario))
    return await _persisted_runtime_snapshot(
        request,
        user,
        session,
        runtime,
        action="load_scenario",
        state=state,
        event_type=_runtime_event_type("load_scenario"),
        before_scenario=before_scenario,
    )


@router.post("/runtime/start", response_model=RuntimeSnapshotResponse)
async def runtime_start(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = await _runtime_for_user_loaded(request, user, session)
    before_scenario = _runtime_event_baseline(runtime)
    state = runtime.start_simulation()
    return await _persisted_runtime_snapshot(
        request,
        user,
        session,
        runtime,
        action="start",
        state=state,
        event_type=_runtime_event_type("start"),
        before_scenario=before_scenario,
    )


@router.post("/runtime/pause", response_model=RuntimeSnapshotResponse)
async def runtime_pause(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = await _runtime_for_user_loaded(request, user, session)
    before_scenario = _runtime_event_baseline(runtime)
    state = runtime.pause_simulation()
    return await _persisted_runtime_snapshot(
        request,
        user,
        session,
        runtime,
        action="pause",
        state=state,
        event_type=_runtime_event_type("pause"),
        before_scenario=before_scenario,
    )


@router.post("/runtime/reset", response_model=RuntimeSnapshotResponse)
async def runtime_reset(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = await _runtime_for_user_loaded(request, user, session)
    before_scenario = _runtime_event_baseline(runtime)
    state = runtime.reset_simulation()
    return await _persisted_runtime_snapshot(
        request,
        user,
        session,
        runtime,
        action="reset",
        state=state,
        event_type=_runtime_event_type("reset"),
        before_scenario=before_scenario,
    )


@router.post("/runtime/step", response_model=RuntimeSnapshotResponse)
async def runtime_step(
    request: Request,
    payload: RuntimeStepRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = await _runtime_for_user_loaded(request, user, session)
    before_scenario = _runtime_event_baseline(runtime)
    state = runtime.step_simulation(payload.steps)
    return await _persisted_runtime_snapshot(
        request,
        user,
        session,
        runtime,
        action="step",
        state=state,
        event_type=_runtime_event_type("step"),
        before_scenario=before_scenario,
    )


@router.post("/runtime/attack", response_model=RuntimeSnapshotResponse)
async def runtime_attack(
    request: Request,
    payload: RuntimeAttackRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = await _runtime_for_user_loaded(request, user, session)
    before_scenario = _runtime_event_baseline(runtime)
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
    return await _persisted_runtime_snapshot(
        request,
        user,
        session,
        runtime,
        action="attack",
        state=state,
        event_type=_runtime_event_type("attack"),
        before_scenario=before_scenario,
    )


@router.post("/runtime/units", response_model=RuntimeSnapshotResponse)
async def runtime_deploy_unit(
    request: Request,
    payload: RuntimeDeployUnitRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = await _runtime_for_user_loaded(request, user, session)
    before_scenario = _runtime_event_baseline(runtime)
    try:
        asset = (
            await find_accessible_unit_asset_by_name(
                session,
                user,
                asset_type=payload.unit_type,
                name=payload.class_name,
            )
            if payload.unit_type in {"aircraft", "ship", "facility", "airbase"}
            else None
        )
        template = asset.data if asset is not None else None
        if payload.unit_type == "aircraft":
            state = runtime.deploy_aircraft(
                payload.class_name,
                payload.latitude,
                payload.longitude,
                side=payload.side,
                name=payload.name,
                altitude=payload.altitude or 10000.0,
                template=template,
            )
        elif payload.unit_type == "ship":
            state = runtime.deploy_ship(
                payload.class_name,
                payload.latitude,
                payload.longitude,
                side=payload.side,
                name=payload.name,
                template=template,
            )
        elif payload.unit_type == "facility":
            state = runtime.deploy_facility(
                payload.class_name,
                payload.latitude,
                payload.longitude,
                side=payload.side,
                name=payload.name,
                template=template,
            )
        elif payload.unit_type == "airbase":
            state = runtime.deploy_airbase(
                payload.class_name,
                payload.latitude,
                payload.longitude,
                side=payload.side,
                name=payload.name,
                template=template,
            )
        elif payload.unit_type == "obstacle":
            state = runtime.deploy_obstacle(
                payload.class_name,
                payload.latitude,
                payload.longitude,
                name=payload.name,
                side=payload.side,
                radius_nm=payload.radius_nm or 15.0,
                obstacle_type=payload.obstacle_type or "no_go",
                movement_penalty=(
                    1.0
                    if payload.movement_penalty is None
                    else payload.movement_penalty
                ),
                detection_penalty=payload.detection_penalty or 0.0,
                communication_penalty=payload.communication_penalty or 0.0,
                affected_domains=payload.affected_domains,
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
    return await _persisted_runtime_snapshot(
        request,
        user,
        session,
        runtime,
        action="deploy_unit",
        state=state,
        event_type=_runtime_event_type("deploy_unit"),
        before_scenario=before_scenario,
    )


@router.delete(
    "/runtime/units/{unit_type}/{unit_id}",
    response_model=RuntimeSnapshotResponse,
)
async def runtime_delete_unit(
    request: Request,
    unit_type: str,
    unit_id: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = await _runtime_for_user_loaded(request, user, session)
    before_scenario = _runtime_event_baseline(runtime)
    try:
        state = runtime.delete_unit(unit_type, unit_id)
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    return await _persisted_runtime_snapshot(
        request,
        user,
        session,
        runtime,
        action="delete_unit",
        state=state,
        event_type=_runtime_event_type("delete_unit"),
        before_scenario=before_scenario,
    )


@router.patch("/runtime/units/route", response_model=RuntimeSnapshotResponse)
async def runtime_move_unit(
    request: Request,
    payload: RuntimeMoveUnitRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = await _runtime_for_user_loaded(request, user, session)
    before_scenario = _runtime_event_baseline(runtime)
    try:
        state = runtime.move_unit(
            payload.unit_type,
            payload.unit_id,
            payload.route,
        )
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    return await _persisted_runtime_snapshot(
        request,
        user,
        session,
        runtime,
        action="move_unit",
        state=state,
        event_type=_runtime_event_type("move_unit"),
        before_scenario=before_scenario,
    )


@router.patch("/runtime/units/position", response_model=RuntimeSnapshotResponse)
async def runtime_set_unit_position(
    request: Request,
    payload: RuntimeSetUnitPositionRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = await _runtime_for_user_loaded(request, user, session)
    before_scenario = _runtime_event_baseline(runtime)
    try:
        state = runtime.set_unit_position(
            payload.unit_type,
            payload.unit_id,
            payload.latitude,
            payload.longitude,
        )
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    return await _persisted_runtime_snapshot(
        request,
        user,
        session,
        runtime,
        action="set_unit_position",
        state=state,
        event_type=_runtime_event_type("set_unit_position"),
        before_scenario=before_scenario,
    )


@router.patch("/runtime/units", response_model=RuntimeSnapshotResponse)
async def runtime_update_unit(
    request: Request,
    payload: RuntimeUpdateUnitRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = await _runtime_for_user_loaded(request, user, session)
    before_scenario = _runtime_event_baseline(runtime)
    try:
        state = runtime.update_unit_state(
            payload.unit_type,
            payload.unit_id,
            payload.patch,
        )
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    return await _persisted_runtime_snapshot(
        request,
        user,
        session,
        runtime,
        action="update_unit",
        state=state,
        event_type=_runtime_event_type("update_unit"),
        before_scenario=before_scenario,
    )


@router.patch("/runtime/side/current", response_model=RuntimeSnapshotResponse)
async def runtime_set_current_side(
    request: Request,
    payload: RuntimeSetCurrentSideRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = await _runtime_for_user_loaded(request, user, session)
    before_scenario = _runtime_event_baseline(runtime)
    try:
        state = runtime.set_current_side(payload.side)
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    return await _persisted_runtime_snapshot(
        request,
        user,
        session,
        runtime,
        action="set_current_side",
        state=state,
        event_type=_runtime_event_type("set_current_side"),
        before_scenario=before_scenario,
    )


@router.post("/runtime/sides", response_model=RuntimeSnapshotResponse)
async def runtime_create_side(
    request: Request,
    payload: RuntimeCreateSideRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = await _runtime_for_user_loaded(request, user, session)
    before_scenario = _runtime_event_baseline(runtime)
    state = runtime.add_side(
        payload.name,
        payload.color,
        payload.hostiles,
        payload.allies,
        payload.doctrine,
    )
    return await _persisted_runtime_snapshot(
        request,
        user,
        session,
        runtime,
        action="create_side",
        state=state,
        event_type=_runtime_event_type("create_side"),
        before_scenario=before_scenario,
    )


@router.patch("/runtime/sides/{side_id}", response_model=RuntimeSnapshotResponse)
async def runtime_update_side(
    request: Request,
    side_id: str,
    payload: RuntimeUpdateSideRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = await _runtime_for_user_loaded(request, user, session)
    before_scenario = _runtime_event_baseline(runtime)
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
    return await _persisted_runtime_snapshot(
        request,
        user,
        session,
        runtime,
        action="update_side",
        state=state,
        event_type=_runtime_event_type("update_side"),
        before_scenario=before_scenario,
    )


@router.delete("/runtime/sides/{side_id}", response_model=RuntimeSnapshotResponse)
async def runtime_delete_side(
    request: Request,
    side_id: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = await _runtime_for_user_loaded(request, user, session)
    before_scenario = _runtime_event_baseline(runtime)
    try:
        state = runtime.delete_side(side_id)
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    return await _persisted_runtime_snapshot(
        request,
        user,
        session,
        runtime,
        action="delete_side",
        state=state,
        event_type=_runtime_event_type("delete_side"),
        before_scenario=before_scenario,
    )


@router.delete("/runtime/missions/{mission_id}", response_model=RuntimeSnapshotResponse)
async def runtime_delete_mission(
    request: Request,
    mission_id: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = await _runtime_for_user_loaded(request, user, session)
    before_scenario = _runtime_event_baseline(runtime)
    state = runtime.delete_mission(mission_id)
    return await _persisted_runtime_snapshot(
        request,
        user,
        session,
        runtime,
        action="delete_mission",
        state=state,
        event_type=_runtime_event_type("delete_mission"),
        before_scenario=before_scenario,
    )


@router.post("/runtime/missions/patrol", response_model=RuntimeSnapshotResponse)
async def runtime_create_patrol_mission(
    request: Request,
    payload: RuntimePatrolMissionRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = await _runtime_for_user_loaded(request, user, session)
    before_scenario = _runtime_event_baseline(runtime)
    state = runtime.create_patrol_mission(
        payload.name,
        payload.assigned_unit_ids,
        payload.reference_point_ids,
    )
    return await _persisted_runtime_snapshot(
        request,
        user,
        session,
        runtime,
        action="create_patrol_mission",
        state=state,
        event_type=_runtime_event_type("create_patrol_mission"),
        before_scenario=before_scenario,
    )


@router.patch(
    "/runtime/missions/patrol/{mission_id}",
    response_model=RuntimeSnapshotResponse,
)
async def runtime_update_patrol_mission(
    request: Request,
    mission_id: str,
    payload: RuntimePatrolMissionRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = await _runtime_for_user_loaded(request, user, session)
    before_scenario = _runtime_event_baseline(runtime)
    try:
        state = runtime.update_patrol_mission(
            mission_id,
            payload.name,
            payload.assigned_unit_ids,
            payload.reference_point_ids,
        )
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    return await _persisted_runtime_snapshot(
        request,
        user,
        session,
        runtime,
        action="update_patrol_mission",
        state=state,
        event_type=_runtime_event_type("update_patrol_mission"),
        before_scenario=before_scenario,
    )


@router.post("/runtime/missions/strike", response_model=RuntimeSnapshotResponse)
async def runtime_create_strike_mission(
    request: Request,
    payload: RuntimeStrikeMissionRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = await _runtime_for_user_loaded(request, user, session)
    before_scenario = _runtime_event_baseline(runtime)
    state = runtime.create_strike_mission(
        payload.name,
        payload.assigned_unit_ids,
        payload.assigned_target_ids,
    )
    return await _persisted_runtime_snapshot(
        request,
        user,
        session,
        runtime,
        action="create_strike_mission",
        state=state,
        event_type=_runtime_event_type("create_strike_mission"),
        before_scenario=before_scenario,
    )


@router.patch(
    "/runtime/missions/strike/{mission_id}",
    response_model=RuntimeSnapshotResponse,
)
async def runtime_update_strike_mission(
    request: Request,
    mission_id: str,
    payload: RuntimeStrikeMissionRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = await _runtime_for_user_loaded(request, user, session)
    before_scenario = _runtime_event_baseline(runtime)
    try:
        state = runtime.update_strike_mission(
            mission_id,
            payload.name,
            payload.assigned_unit_ids,
            payload.assigned_target_ids,
        )
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    return await _persisted_runtime_snapshot(
        request,
        user,
        session,
        runtime,
        action="update_strike_mission",
        state=state,
        event_type=_runtime_event_type("update_strike_mission"),
        before_scenario=before_scenario,
    )


@router.post("/runtime/weapons", response_model=RuntimeSnapshotResponse)
async def runtime_add_weapon(
    request: Request,
    payload: RuntimeAddWeaponRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = await _runtime_for_user_loaded(request, user, session)
    before_scenario = _runtime_event_baseline(runtime)
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
    return await _persisted_runtime_snapshot(
        request,
        user,
        session,
        runtime,
        action="add_weapon",
        state=state,
        event_type=_runtime_event_type("add_weapon"),
        before_scenario=before_scenario,
    )


@router.delete("/runtime/weapons", response_model=RuntimeSnapshotResponse)
async def runtime_delete_weapon(
    request: Request,
    payload: RuntimeDeleteWeaponRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = await _runtime_for_user_loaded(request, user, session)
    before_scenario = _runtime_event_baseline(runtime)
    try:
        state = runtime.delete_weapon_from_unit(
            payload.unit_type,
            payload.unit_id,
            payload.weapon_id,
        )
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    return await _persisted_runtime_snapshot(
        request,
        user,
        session,
        runtime,
        action="delete_weapon",
        state=state,
        event_type=_runtime_event_type("delete_weapon"),
        before_scenario=before_scenario,
    )


@router.patch("/runtime/weapons/quantity", response_model=RuntimeSnapshotResponse)
async def runtime_update_weapon_quantity(
    request: Request,
    payload: RuntimeUpdateWeaponQuantityRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> RuntimeSnapshotResponse:
    runtime = await _runtime_for_user_loaded(request, user, session)
    before_scenario = _runtime_event_baseline(runtime)
    try:
        state = runtime.update_weapon_quantity(
            payload.unit_type,
            payload.unit_id,
            payload.weapon_id,
            payload.increment,
        )
    except ValueError as exc:
        raise _runtime_value_error(exc) from exc
    return await _persisted_runtime_snapshot(
        request,
        user,
        session,
        runtime,
        action="update_weapon_quantity",
        state=state,
        event_type=_runtime_event_type("update_weapon_quantity"),
        before_scenario=before_scenario,
    )


@router.get("/skills")
def list_skills(
    request: Request,
    user: User = Depends(current_active_user),
) -> dict:
    bridge = _bridge_for_user(request, user)
    return {"skills": [definition.model_dump() for definition in bridge.skill_registry.definitions()]}


@router.get("/custom-skills", response_model=CustomSkillListResponse)
def list_custom_skills(
    request: Request,
    user: User = Depends(current_active_user),
) -> CustomSkillListResponse:
    store = _custom_skill_store(request)
    return CustomSkillListResponse(
        skills=store.list(str(user.id)),
        skillsDir=str(store.root_dir),
    )


@router.post(
    "/custom-skills",
    response_model=CustomSkillRead,
    status_code=status.HTTP_201_CREATED,
)
def create_custom_skill(
    request: Request,
    payload: CustomSkillCreateRequest,
    user: User = Depends(current_active_user),
) -> CustomSkillRead:
    try:
        return _custom_skill_store(request).create(
            str(user.id),
            payload,
            created_by=_custom_skill_created_by(user),
        )
    except CustomSkillStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.patch("/custom-skills/{skill_id}", response_model=CustomSkillRead)
def update_custom_skill(
    request: Request,
    skill_id: str,
    payload: CustomSkillUpdateRequest,
    user: User = Depends(current_active_user),
) -> CustomSkillRead:
    try:
        return _custom_skill_store(request).update(str(user.id), skill_id, payload)
    except CustomSkillNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Custom skill not found.",
        ) from exc
    except CustomSkillStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.delete(
    "/custom-skills/{skill_id}",
    response_class=Response,
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_custom_skill(
    request: Request,
    skill_id: str,
    user: User = Depends(current_active_user),
) -> None:
    try:
        _custom_skill_store(request).delete(str(user.id), skill_id)
    except CustomSkillNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Custom skill not found.",
        ) from exc
    except CustomSkillStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


def _external_mcp_transport(payload: ExternalMcpValidateRequest) -> str:
    transport = payload.transport.strip().lower().replace("-", "_")
    if transport in {"http", "sse", "streamablehttp", "streamable_http"}:
        return "streamable_http"
    if transport == "stdio":
        return "stdio"
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"Unsupported MCP transport: {payload.transport}",
    )


def _split_mcp_command_line(command_line: str) -> tuple[str, list[str]]:
    if not command_line.strip() or command_line.startswith("stdio://"):
        return "", []
    try:
        parts = shlex.split(command_line, posix=True)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid stdio command line: {exc}",
        ) from exc
    if not parts:
        return "", []
    return parts[0], parts[1:]


def _external_mcp_config_from_payload(
    payload: ExternalMcpValidateRequest,
) -> MCPServerConfig:
    transport = _external_mcp_transport(payload)
    endpoint = payload.endpoint.strip()
    command = payload.command.strip()
    args = [arg for arg in payload.args if arg.strip()]
    url = (payload.url or "").strip()

    if transport == "stdio":
        if not command:
            command, fallback_args = _split_mcp_command_line(endpoint)
            args = args or fallback_args
        if not command:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="stdio MCP validation requires command or command-line endpoint.",
            )
        url = ""
    else:
        url = url or endpoint
        if not url:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="HTTP MCP validation requires url or endpoint.",
            )
        command = ""
        args = []

    return MCPServerConfig(
        name=payload.name,
        transport=transport,
        command=command,
        args=args,
        env=dict(payload.env),
        url=url,
        headers=dict(payload.headers),
        allowed_tools=list(payload.allowedTools),
        enabled=payload.enabled,
        timeout_seconds=min(max(float(payload.timeoutSeconds), 1.0), 15.0),
    )


@router.post("/mcp/validate", response_model=ExternalMcpValidateResponse)
async def validate_external_mcp_server(
    payload: ExternalMcpValidateRequest,
    user: User = Depends(current_active_user),
) -> ExternalMcpValidateResponse:
    """Validate one operator-provided MCP server and return its tool list.

    The config is intentionally not persisted server-side here. The client uses
    this as a connection proof before saving its local MCP configuration.
    """
    _ = user
    config = _external_mcp_config_from_payload(payload)
    client = MCPClientSkeleton()
    try:
        client.register_server(config)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    trace, tools = await client.list_tools(config.name)
    ok = any(item.status == "ok" for item in trace)
    message = trace[-1].message if trace else "MCP validation finished."
    return ExternalMcpValidateResponse(
        ok=ok,
        server=config.name,
        transport=config.normalized_transport(),  # type: ignore[arg-type]
        message=message,
        tools=tools,
        trace=trace,
    )


@router.get("/mcp/builtin/tools", response_model=BuiltinMcpToolsResponse)
async def list_builtin_mcp_tools(
    user: User = Depends(current_active_user),
) -> BuiltinMcpToolsResponse:
    """Return the built-in TianShu MCP tool registry for the settings UI."""
    _ = user
    from app.mcp.server import list_builtin_mcp_tool_definitions

    tools = await list_builtin_mcp_tool_definitions()
    return BuiltinMcpToolsResponse(
        ok=True,
        server="TianShu MCP",
        message=f"{len(tools)} built-in TianShu MCP tools available.",
        tools=tools,
    )


@router.post("/model/check", response_model=ModelCheckResponse)
async def check_model(
    payload: ModelCheckRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> ModelCheckResponse:
    if payload.provider and not payload.apiKey:
        stored_api_key, stored_base_url = await resolve_stored_model_credentials(
            session,
            user,
            provider_id=payload.providerId,
            provider=payload.provider,
            base_url=payload.baseUrl,
        )
        payload = payload.model_copy(
            update={
                "apiKey": stored_api_key,
                "baseUrl": stored_base_url,
            }
        )
    return check_model_connectivity(payload)


@router.get("/model/providers", response_model=AIModelProviderConfigList)
async def list_model_providers(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> AIModelProviderConfigList:
    return AIModelProviderConfigList(
        providers=await list_model_provider_configs(session, user)
    )


@router.put(
    "/model/providers/{provider_id}",
    response_model=AIModelProviderConfigRead,
)
async def save_model_provider(
    provider_id: str,
    payload: AIModelProviderConfigUpdate,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> AIModelProviderConfigRead:
    return await upsert_model_provider_config(session, user, provider_id, payload)


# ─── S4: Streaming Chat (Pydantic AI) ─────────────────────────────────────────


def _read_model_override_from_headers(
    request: Request,
) -> tuple[str, str, str, str, str]:
    """Pull per-request model override fields from custom headers.

    The AI sidebar sends ``X-TianShu-Model-{Provider,Name,Api-Key,Base-Url}``
    whenever the user has filled in a model config. Empty / missing
    headers fall back to "" so the caller can decide between override and
    the env-configured global agent.
    """
    return (
        _header_value(request, "x-tianshu-model-provider-id").strip(),
        _header_value(request, "x-tianshu-model-provider").strip(),
        _header_value(request, "x-tianshu-model-name").strip(),
        _header_value(request, "x-tianshu-model-api-key").strip(),
        _header_value(request, "x-tianshu-model-base-url").strip(),
    )


def _read_chat_mode_from_headers(request: Request) -> str:
    mode = (_header_value(request, "x-tianshu-chat-mode") or "command").strip().lower()
    return "ask" if mode == "ask" else "command"


@router.post("/chat")
async def chat(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> StreamingResponse:
    """Streaming chat endpoint powered by pydantic-ai.

    Accepts Vercel AI SDK compatible request body (messages array).
    Returns SSE stream of text deltas + tool-invocation chunks that any
    AI-SDK–compatible frontend (``useChat`` from ``@ai-sdk/react``) can
    consume out of the box.

    Model override: when the request carries
    ``X-TianShu-Model-{Provider,Name,Api-Key,Base-Url}`` headers (i.e. the
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

    bridge = await _bridge_for_user_loaded(request, user, session)
    chat_mode = _read_chat_mode_from_headers(request)

    # Per-request model override via headers (set by AI sidebar useChat).
    provider_id, provider, model_name, api_key, base_url = (
        _read_model_override_from_headers(request)
    )
    if provider and not api_key:
        stored_api_key, stored_base_url = await resolve_stored_model_credentials(
            session,
            user,
            provider_id=provider_id,
            provider=provider,
            base_url=base_url,
        )
        api_key = stored_api_key
        base_url = stored_base_url
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
                                "No LLM configured. Either set TIANSHU_LLM_MODEL + "
                                "TIANSHU_LLM_API_KEY on the server, or fill the "
                                "model section in the AI sidebar (Settings)."
                            )
                        }
                    )
                ]
            ),
            status_code=503,
            media_type="application/json",
        )

    approval_queue = (
        getattr(bridge, "command_approvals", None)
        if chat_mode == "command"
        else None
    )
    event_loop = asyncio.get_running_loop()

    def _record_proposal(proposal):
        async def _persist() -> None:
            async with async_session_maker() as session:
                saved = await save_command_proposal(
                    session,
                    user,
                    proposal,
                    scenario_id=_runtime_context_from_request(request),
                )
                await record_runtime_event(
                    session,
                    user,
                    event_type="command.proposed",
                    action="proposal_created",
                    actor=saved.source,
                    summary=f"命令提案：{saved.command}",
                    payload=saved.model_dump(mode="json"),
                    runtime=getattr(bridge, "runtime", None),
                    proposal_id=saved.id,
                )
            if approval_queue is not None:
                approval_queue.hydrate(saved)

        event_loop.call_soon_threadsafe(lambda: event_loop.create_task(_persist()))

    deps = AgentDeps(
        registry=bridge.skill_registry,
        chat_mode=chat_mode,
        approval_queue=approval_queue,
        proposal_recorder=_record_proposal if approval_queue is not None else None,
        mcp_client=bridge.mcp_client,
        session=session,
        user=user,
        scenario_id=_runtime_context_from_request(request),
        bridge_provider=lambda owner, scenario_ctx=None: _bridge_for_user(
            request,
            owner,
            scenario_ctx,
        ),
    )
    return await VercelAIAdapter.dispatch_request(
        request,
        agent=agent,
        deps=deps,
    )
