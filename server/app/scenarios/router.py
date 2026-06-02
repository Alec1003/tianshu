"""/api/scenarios CRUD + AAR endpoints.

Permission model (v1, single-user-owned):
    list   -- own + system templates
    get    -- own OR system template
    create -- any logged-in user
    update -- only owner; system templates are read-only
    delete -- only owner; system templates are read-only
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, NoReturn, Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.aicc_runtime.persistence import save_runtime_state
from app.aicc_runtime.schemas import RuntimeTimelineResponse
from app.aicc_runtime.timeline import (
    list_runtime_events,
    record_runtime_event,
    runtime_scenario_id,
)
from app.auth.models import User
from app.auth.users import current_active_user
from app.db.session import get_async_session
from app.scenarios import service as scenario_service
from app.scenarios.errors import (
    ScenarioForbiddenError,
    ScenarioInvalidError,
    ScenarioNotFoundError,
    ScenarioServiceError,
    ScenarioTemplateReadOnlyError,
)
from app.scenarios.models import AarRecord, Scenario
from app.scenarios.schemas import (
    AarRecordCreate,
    AarRecordRead,
    ScenarioBatchSimulationRequest,
    ScenarioBatchSimulationResponse,
    ScenarioBranchCreate,
    ScenarioCompareForkCreate,
    ScenarioCompareResponse,
    ScenarioCompareReportCreate,
    ScenarioCompareReportRead,
    ScenarioCompareSessionCreate,
    ScenarioCompareSessionRead,
    ScenarioCompareSessionUpdate,
    ScenarioCreate,
    ScenarioDetail,
    ScenarioListItem,
    ScenarioPlanSetCreate,
    ScenarioPlanSetRead,
    ScenarioUpdate,
    TrainingScoreRecordRead,
    TrainingScoreResponse,
)

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


def _bridge_for_user(
    request: Request,
    user: User,
    scenario_id: str | None = None,
) -> Any:
    registry = getattr(request.app.state, "bridge_registry", None)
    if registry is not None:
        return registry.get_bridge_for_user(user, scenario_id=scenario_id)
    return request.app.state.bridge


def _raise_scenario_http(exc: ScenarioServiceError) -> NoReturn:
    if isinstance(exc, ScenarioNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, ScenarioForbiddenError | ScenarioTemplateReadOnlyError):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, ScenarioInvalidError):
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        code = status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=code, detail=exc.to_dict()) from exc


# ---------- list / detail ----------
@router.get("", response_model=list[ScenarioListItem])
async def list_scenarios(
    include_templates: bool = True,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Sequence[Scenario]:
    """Returns scenarios owned by the caller plus system templates.

    The frontend "我的想定" page consumes this; templates show up alongside
    user-saved ones with an ``is_template`` badge.
    """
    return await scenario_service.list_scenarios(
        session,
        user,
        include_templates=include_templates,
    )


@router.get("/compare", response_model=ScenarioCompareResponse)
async def compare_scenarios(
    scenario_id: list[str] = Query(...),
    baseline_id: str | None = None,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> ScenarioCompareResponse:
    ordered_ids = list(dict.fromkeys(scenario_id))
    if len(ordered_ids) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "scenario_compare_invalid",
                "message": "comparison requires at least two distinct scenarios",
            },
        )
    if len(ordered_ids) > 6:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "scenario_compare_invalid",
                "message": "comparison supports up to six scenarios at a time",
            },
        )
    effective_baseline = baseline_id or ordered_ids[0]
    if effective_baseline not in ordered_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "scenario_compare_invalid",
                "message": "baseline must be included in scenario_id",
            },
        )
    try:
        items = await scenario_service.build_scenario_compare_items(
            session,
            user,
            ordered_ids,
        )
    except ScenarioServiceError as exc:
        _raise_scenario_http(exc)
    return ScenarioCompareResponse(
        baseline_id=effective_baseline,
        generated_at=datetime.now(timezone.utc),
        items=items,
    )


@router.get("/compare/reports", response_model=list[ScenarioCompareReportRead])
async def list_compare_reports(
    limit: int = 50,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        return await scenario_service.list_compare_reports(
            session,
            user,
            limit=limit,
        )
    except ScenarioServiceError as exc:
        _raise_scenario_http(exc)


@router.post(
    "/compare/reports",
    response_model=ScenarioCompareReportRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_compare_report(
    payload: ScenarioCompareReportCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        return await scenario_service.create_compare_report(
            session,
            user,
            payload=payload,
        )
    except ScenarioServiceError as exc:
        _raise_scenario_http(exc)


@router.get("/compare/sessions", response_model=list[ScenarioCompareSessionRead])
async def list_compare_sessions(
    limit: int = 50,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        return await scenario_service.list_compare_sessions(
            session,
            user,
            limit=limit,
        )
    except ScenarioServiceError as exc:
        _raise_scenario_http(exc)


@router.post(
    "/compare/sessions",
    response_model=ScenarioCompareSessionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_compare_session(
    payload: ScenarioCompareSessionCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        return await scenario_service.create_compare_session(
            session,
            user,
            payload=payload,
        )
    except ScenarioServiceError as exc:
        _raise_scenario_http(exc)


@router.get(
    "/compare/sessions/{compare_session_id}",
    response_model=ScenarioCompareSessionRead,
)
async def get_compare_session(
    compare_session_id: str,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        return await scenario_service.get_compare_session(
            session,
            user,
            compare_session_id,
        )
    except ScenarioServiceError as exc:
        _raise_scenario_http(exc)


@router.patch(
    "/compare/sessions/{compare_session_id}",
    response_model=ScenarioCompareSessionRead,
)
async def update_compare_session(
    compare_session_id: str,
    payload: ScenarioCompareSessionUpdate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        return await scenario_service.update_compare_session(
            session,
            user,
            compare_session_id,
            payload=payload,
        )
    except ScenarioServiceError as exc:
        _raise_scenario_http(exc)


@router.delete(
    "/compare/sessions/{compare_session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_compare_session(
    compare_session_id: str,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Response:
    try:
        await scenario_service.delete_compare_session(
            session,
            user,
            compare_session_id,
        )
    except ScenarioServiceError as exc:
        _raise_scenario_http(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/compare/reports/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_compare_report(
    report_id: str,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Response:
    try:
        await scenario_service.delete_compare_report(
            session,
            user,
            report_id,
        )
    except ScenarioServiceError as exc:
        _raise_scenario_http(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{scenario_id}", response_model=ScenarioDetail)
async def get_scenario(
    scenario_id: str,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Scenario:
    try:
        return await scenario_service.get_scenario(session, user, scenario_id)
    except ScenarioServiceError as exc:
        _raise_scenario_http(exc)


# ---------- create / update / delete ----------
@router.post("", response_model=ScenarioDetail, status_code=status.HTTP_201_CREATED)
async def create_scenario(
    payload: ScenarioCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Scenario:
    try:
        return await scenario_service.create_scenario(
            session,
            user,
            name=payload.name,
            description=payload.description,
            data=payload.data,
            status=payload.status,
        )
    except ScenarioServiceError as exc:
        _raise_scenario_http(exc)


@router.post(
    "/{scenario_id}/branch",
    response_model=ScenarioDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_scenario_branch(
    scenario_id: str,
    payload: ScenarioBranchCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Scenario:
    try:
        return await scenario_service.create_branch_scenario(
            session,
            user,
            scenario_id,
            name=payload.name,
            description=payload.description,
            branch_label=payload.branch_label,
            status=payload.status,
            data=payload.data,
        )
    except ScenarioServiceError as exc:
        _raise_scenario_http(exc)


@router.post(
    "/{scenario_id}/compare-session/fork",
    response_model=ScenarioCompareSessionRead,
    status_code=status.HTTP_201_CREATED,
)
async def fork_compare_session(
    scenario_id: str,
    payload: ScenarioCompareForkCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> ScenarioCompareSessionRead:
    try:
        return await scenario_service.fork_compare_session(
            session,
            user,
            scenario_id,
            payload=payload,
        )
    except ScenarioServiceError as exc:
        _raise_scenario_http(exc)


@router.post(
    "/{scenario_id}/plan-set",
    response_model=ScenarioPlanSetRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_plan_set(
    scenario_id: str,
    payload: ScenarioPlanSetCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> ScenarioPlanSetRead:
    try:
        return await scenario_service.create_plan_set_compare_session(
            session,
            user,
            scenario_id,
            payload=payload,
        )
    except ScenarioServiceError as exc:
        _raise_scenario_http(exc)


@router.post(
    "/compare/sessions/{compare_session_id}/simulate",
    response_model=ScenarioBatchSimulationResponse,
)
async def simulate_compare_session(
    compare_session_id: str,
    payload: ScenarioBatchSimulationRequest,
    request: Request,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> ScenarioBatchSimulationResponse:
    try:
        return await scenario_service.simulate_compare_session_batch(
            session,
            user,
            compare_session_id,
            payload=payload,
            bridge_provider=lambda owner, scenario_ctx=None: _bridge_for_user(
                request,
                owner,
                scenario_ctx,
            ),
        )
    except ScenarioServiceError as exc:
        _raise_scenario_http(exc)


@router.patch("/{scenario_id}", response_model=ScenarioDetail)
async def update_scenario(
    scenario_id: str,
    payload: ScenarioUpdate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Scenario:
    try:
        return await scenario_service.update_scenario(
            session,
            user,
            scenario_id,
            name=payload.name,
            description=payload.description,
            data=payload.data,
            status=payload.status,
        )
    except ScenarioServiceError as exc:
        _raise_scenario_http(exc)


@router.delete(
    "/{scenario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_scenario(
    scenario_id: str,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Response:
    try:
        await scenario_service.delete_scenario(session, user, scenario_id)
    except ScenarioServiceError as exc:
        _raise_scenario_http(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- AAR records (per scenario) ----------
@router.get("/{scenario_id}/aar", response_model=list[AarRecordRead])
async def list_aar_records(
    scenario_id: str,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Sequence[AarRecord]:
    try:
        return await scenario_service.list_aar_records(session, user, scenario_id)
    except ScenarioServiceError as exc:
        _raise_scenario_http(exc)


@router.post(
    "/{scenario_id}/aar",
    response_model=AarRecordRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_aar_record(
    scenario_id: str,
    payload: AarRecordCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> AarRecord:
    # We don't gate on scenario existence: clients can post AARs against
    # imported scenarios that were never persisted to DB. ``scenario_id`` then
    # acts as a free-form correlation tag.
    try:
        rec = await scenario_service.create_aar_record(
            session,
            user,
            scenario_id,
            outcome_reason=payload.outcome_reason,
            winner_side_id=payload.winner_side_id,
            summary=payload.summary,
            ended_at=payload.ended_at,
        )
    except ScenarioServiceError as exc:
        _raise_scenario_http(exc)
    event_scenario_id = scenario_id
    sc: Scenario | None = None
    try:
        sc = await scenario_service.get_scenario(session, user, scenario_id)
        event_scenario_id = runtime_scenario_id(sc.data) or scenario_id
    except ScenarioServiceError:
        event_scenario_id = scenario_id
    await record_runtime_event(
        session,
        user,
        event_type="aar.created",
        action="create_aar_record",
        actor="operator",
        summary="生成 AAR 复盘记录",
        payload=AarRecordRead.model_validate(rec).model_dump(mode="json"),
        scenario_id=event_scenario_id,
        aar_record_id=rec.id,
    )
    if sc is not None:
        score = await scenario_service.build_training_score_for_scenario(
            session,
            user,
            sc,
            scenario_id,
        )
        await scenario_service.create_training_score_record(
            session,
            user,
            scenario_id,
            score=score,
            aar_record_id=rec.id,
        )
    return rec


@router.get("/{scenario_id}/timeline", response_model=RuntimeTimelineResponse)
async def list_scenario_timeline(
    scenario_id: str,
    event_type: str | None = None,
    category: str | None = None,
    limit: int = 200,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> RuntimeTimelineResponse:
    try:
        sc = await scenario_service.get_scenario(session, user, scenario_id)
    except ScenarioServiceError as exc:
        _raise_scenario_http(exc)
    inner_id = runtime_scenario_id(sc.data)
    scenario_ids = [scenario_id]
    if inner_id and inner_id != scenario_id:
        scenario_ids.append(inner_id)
    events = await list_runtime_events(
        session,
        user,
        scenario_id=scenario_ids,
        event_type=event_type,
        category=category,
        limit=limit,
    )
    return RuntimeTimelineResponse(events=list(events))


@router.get("/{scenario_id}/training-score", response_model=TrainingScoreResponse)
async def get_scenario_training_score(
    scenario_id: str,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> TrainingScoreResponse:
    try:
        sc = await scenario_service.get_scenario(session, user, scenario_id)
    except ScenarioServiceError as exc:
        _raise_scenario_http(exc)
    return await scenario_service.build_training_score_for_scenario(
        session,
        user,
        sc,
        scenario_id,
    )


@router.get(
    "/{scenario_id}/training-score/records",
    response_model=list[TrainingScoreRecordRead],
)
async def list_scenario_training_score_records(
    scenario_id: str,
    limit: int = 20,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Sequence:
    try:
        return await scenario_service.list_training_score_records(
            session,
            user,
            scenario_id,
            limit=limit,
        )
    except ScenarioServiceError as exc:
        _raise_scenario_http(exc)


@router.post(
    "/{scenario_id}/training-score/records",
    response_model=TrainingScoreRecordRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_scenario_training_score_record(
    scenario_id: str,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        sc = await scenario_service.get_scenario(session, user, scenario_id)
        score = await scenario_service.build_training_score_for_scenario(
            session,
            user,
            sc,
            scenario_id,
        )
        return await scenario_service.create_training_score_record(
            session,
            user,
            scenario_id,
            score=score,
        )
    except ScenarioServiceError as exc:
        _raise_scenario_http(exc)


# ---------- runtime activation ----------
@router.post("/{scenario_id}/activate")
async def activate_scenario(
    scenario_id: str,
    request: Request,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """Load a DB scenario into this user's in-memory runtime.

    Called by the frontend when the user enters /play/:scenarioId so that
    MCP tools and /api/ai/command operate on the correct scenario.
    The operation is best-effort from the frontend's perspective: the
    browser-side game is already loaded from the DB payload; this call only
    keeps the server-side runtime in sync.
    """
    try:
        sc = await scenario_service.get_scenario(session, user, scenario_id)
    except ScenarioServiceError as exc:
        _raise_scenario_http(exc)

    bridge = _bridge_for_user(request, user, scenario_id=sc.id)

    # If the runtime already has this scenario loaded (same inner currentScenario.id),
    # skip the reload so MCP-deployed units and other in-memory changes are preserved.
    inner_id = (sc.data or {}).get("currentScenario", {}).get("id", "")
    runtime_id = str(getattr(bridge.runtime.game.current_scenario, "id", ""))
    if inner_id and inner_id == runtime_id:
        return {"ok": True, "scenario_id": sc.id, "scenario_name": sc.name, "loaded": False}

    scenario_json = json.dumps(sc.data, ensure_ascii=False)
    before_scenario = bridge.runtime.get_exported_scenario()
    await asyncio.to_thread(bridge.runtime.load_scenario_from_json, scenario_json)
    await save_runtime_state(session, user, bridge.runtime, scenario_id=sc.id)
    await record_runtime_event(
        session,
        user,
        event_type="scenario.activated",
        action="activate_scenario",
        actor="operator",
        summary=f"激活场景：{sc.name}",
        payload={"scenarioId": sc.id, "scenarioName": sc.name},
        runtime=bridge.runtime,
        before_scenario=before_scenario,
    )

    return {"ok": True, "scenario_id": sc.id, "scenario_name": sc.name, "loaded": True}
