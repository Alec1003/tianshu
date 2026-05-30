"""Scenario business functions, transport-agnostic.

一句话：把当前在 ``router.py`` 里的 endpoint handler 中的业务部分提取成
普通 async 函数，让 HTTP / MCP / 未来的 CLI 都能复用同一份权限/数据/状态
机判断。

为什么 router.py 不立刻接入：本切片范围只做 MCP，不动 FastAPI 路由以保
证零回归风险；下一切片再让 router 走 service 去掉重复。
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.aicc_runtime.models import RuntimeEvent
from app.aicc_runtime.timeline import list_runtime_events, runtime_scenario_id
from app.auth.models import User
from app.scenarios.errors import (
    ScenarioForbiddenError,
    ScenarioInvalidError,
    ScenarioNotFoundError,
    ScenarioTemplateReadOnlyError,
)
from app.scenarios.models import (
    BRANCH_META_KEY,
    AarRecord,
    Scenario,
    ScenarioCompareReport,
    ScenarioCompareSession,
    TrainingScoreRecord,
    extract_branch_meta,
)
from app.scenarios.schemas import (
    VALID_STATUSES,
    ScenarioCompareItem,
    ScenarioCompareForkCreate,
    ScenarioCompareReportCreate,
    ScenarioCompareSessionCreate,
    ScenarioCompareSessionState,
    ScenarioCompareSessionUpdate,
    ScenarioCompareSnapshot,
    TrainingScoreResponse,
)
from app.scenarios.training_score import build_training_score


# ---------- helpers ----------------------------------------------------------


async def _load_or_404(session: AsyncSession, scenario_id: str) -> Scenario:
    sc = await session.get(Scenario, scenario_id)
    if sc is None:
        raise ScenarioNotFoundError(scenario_id)
    return sc


def _ensure_can_read(sc: Scenario, user: User) -> None:
    if not sc.is_template and str(sc.owner_id) != str(user.id):
        raise ScenarioForbiddenError(sc.id, "not the owner")


def _ensure_can_write(sc: Scenario, user: User) -> None:
    """Templates are read-only for non-superusers; otherwise must own the row."""
    if sc.is_template:
        if not user.is_superuser:
            raise ScenarioTemplateReadOnlyError(sc.id)
        return
    if str(sc.owner_id) != str(user.id):
        raise ScenarioForbiddenError(sc.id, "not the owner")


# ---------- list / detail ----------------------------------------------------


async def list_scenarios(
    session: AsyncSession,
    user: User,
    *,
    include_templates: bool = True,
) -> Sequence[Scenario]:
    """Return scenarios the user can see (own + system templates)."""
    stmt = select(Scenario)
    if include_templates:
        stmt = stmt.where(
            (Scenario.owner_id == user.id) | (Scenario.is_template == True)  # noqa: E712
        )
    else:
        stmt = stmt.where(Scenario.owner_id == user.id)
    stmt = stmt.order_by(Scenario.is_template.desc(), Scenario.updated_at.desc())
    rows = await session.execute(stmt)
    return rows.scalars().all()


async def get_scenario(
    session: AsyncSession, user: User, scenario_id: str
) -> Scenario:
    sc = await _load_or_404(session, scenario_id)
    _ensure_can_read(sc, user)
    return sc


# ---------- create / update / delete -----------------------------------------


async def create_scenario(
    session: AsyncSession,
    user: User,
    *,
    name: str,
    description: str = "",
    data: dict[str, Any],
    status: str = "draft",
) -> Scenario:
    """Create a user-owned scenario. ``status`` falls back to 'draft' if invalid
    so callers (incl. LLM tool) cannot persist garbage state."""
    name = (name or "").strip()
    if not name:
        raise ScenarioInvalidError("name", "must not be empty")
    if len(name) > 120:
        raise ScenarioInvalidError("name", "exceeds 120 chars")
    if not isinstance(data, dict):
        raise ScenarioInvalidError("data", "must be a JSON object")
    safe_status = status if status in VALID_STATUSES else "draft"

    sc = Scenario(
        name=name,
        description=description or "",
        data=data,
        is_template=False,
        owner_id=user.id,
        status=safe_status,
    )
    session.add(sc)
    await session.commit()
    await session.refresh(sc)
    return sc


def _scenario_name_default(source: Scenario, *, branch_depth: int) -> str:
    return f"{source.name} / 分支 {branch_depth}"


def _branch_payload(
    source: Scenario,
    *,
    branch_name: str,
    branch_label: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    payload = deepcopy(data)
    current = payload.get("currentScenario")
    if isinstance(current, dict):
        current["id"] = str(uuid4())
        current["name"] = branch_name

    source_meta = extract_branch_meta(source.data) or {}
    root_scenario_id = source_meta.get("root_scenario_id") or source.id
    root_scenario_name = source_meta.get("root_scenario_name") or source.name
    branch_depth = int(source_meta.get("branch_depth") or 0) + 1

    payload[BRANCH_META_KEY] = {
        "parent_scenario_id": source.id,
        "parent_scenario_name": source.name,
        "root_scenario_id": root_scenario_id,
        "root_scenario_name": root_scenario_name,
        "branch_label": branch_label,
        "branch_depth": branch_depth,
        "created_from_version": source.version,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return payload


async def create_branch_scenario(
    session: AsyncSession,
    user: User,
    source_scenario_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    branch_label: str | None = None,
    status: str = "draft",
    data: dict[str, Any] | None = None,
) -> Scenario:
    source = await get_scenario(session, user, source_scenario_id)
    payload = deepcopy(data if data is not None else source.data)
    if not isinstance(payload, dict):
        raise ScenarioInvalidError("data", "must be a JSON object")

    source_meta = extract_branch_meta(source.data) or {}
    next_branch_depth = int(source_meta.get("branch_depth") or 0) + 1
    safe_name = (name or "").strip() or _scenario_name_default(
        source,
        branch_depth=next_branch_depth,
    )
    safe_label = (branch_label or "").strip() or f"分支 {next_branch_depth}"
    safe_description = (
        description if description is not None else source.description or ""
    )
    branched_payload = _branch_payload(
        source,
        branch_name=safe_name,
        branch_label=safe_label,
        data=payload,
    )
    return await create_scenario(
        session,
        user,
        name=safe_name,
        description=safe_description,
        data=branched_payload,
        status=status,
    )


async def update_scenario(
    session: AsyncSession,
    user: User,
    scenario_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    data: dict[str, Any] | None = None,
    status: str | None = None,
) -> Scenario:
    """Patch semantics: only fields explicitly given are updated.

    Bumps ``version`` when ``data`` is replaced; touches ``updated_at`` via
    SQLAlchemy ``onupdate`` regardless.
    """
    sc = await _load_or_404(session, scenario_id)
    _ensure_can_write(sc, user)

    if name is not None:
        name = name.strip()
        if not name:
            raise ScenarioInvalidError("name", "must not be empty")
        if len(name) > 120:
            raise ScenarioInvalidError("name", "exceeds 120 chars")
        sc.name = name
    if description is not None:
        if len(description) > 2000:
            raise ScenarioInvalidError("description", "exceeds 2000 chars")
        sc.description = description
    if data is not None:
        if not isinstance(data, dict):
            raise ScenarioInvalidError("data", "must be a JSON object")
        sc.data = data
        sc.version += 1
    if status is not None:
        if status not in VALID_STATUSES:
            raise ScenarioInvalidError(
                "status",
                f"expected one of {sorted(VALID_STATUSES)}",
            )
        sc.status = status

    await session.commit()
    await session.refresh(sc)
    return sc


async def delete_scenario(
    session: AsyncSession, user: User, scenario_id: str
) -> None:
    sc = await _load_or_404(session, scenario_id)
    if sc.is_template:
        raise ScenarioForbiddenError(sc.id, "templates cannot be deleted")
    if str(sc.owner_id) != str(user.id):
        raise ScenarioForbiddenError(sc.id, "not the owner")
    await session.delete(sc)
    await session.commit()


# ---------- AAR --------------------------------------------------------------


async def list_aar_records(
    session: AsyncSession,
    user: User,
    scenario_id: str,
    *,
    limit: int = 50,
) -> Sequence[AarRecord]:
    sc = await _load_or_404(session, scenario_id)
    _ensure_can_read(sc, user)
    limit = max(1, min(int(limit), 200))
    stmt = (
        select(AarRecord)
        .where(AarRecord.scenario_id == scenario_id)
        .where(AarRecord.owner_id == user.id)
        .order_by(AarRecord.created_at.desc())
        .limit(limit)
    )
    rows = await session.execute(stmt)
    return rows.scalars().all()


async def create_aar_record(
    session: AsyncSession,
    user: User,
    scenario_id: str,
    *,
    outcome_reason: str,
    winner_side_id: str,
    summary: dict[str, Any],
    ended_at: datetime,
) -> AarRecord:
    """Mirror of router.create_aar_record: scenario_id is a free-form
    correlation tag (intentionally not gated on existence)."""
    if not outcome_reason or len(outcome_reason) > 40:
        raise ScenarioInvalidError(
            "outcome_reason", "must be 1..40 chars"
        )
    if winner_side_id and len(winner_side_id) > 80:
        raise ScenarioInvalidError("winner_side_id", "exceeds 80 chars")
    if not isinstance(summary, dict):
        raise ScenarioInvalidError("summary", "must be a JSON object")

    rec = AarRecord(
        scenario_id=scenario_id,
        owner_id=user.id,
        outcome_reason=outcome_reason,
        winner_side_id=winner_side_id or "",
        summary=summary,
        ended_at=ended_at,
    )
    session.add(rec)
    await session.commit()
    await session.refresh(rec)
    return rec


# ---------- Training score records ------------------------------------------


async def list_training_score_records(
    session: AsyncSession,
    user: User,
    scenario_id: str,
    *,
    limit: int = 20,
) -> Sequence[TrainingScoreRecord]:
    sc = await _load_or_404(session, scenario_id)
    _ensure_can_read(sc, user)
    limit = max(1, min(int(limit), 100))
    stmt = (
        select(TrainingScoreRecord)
        .where(TrainingScoreRecord.scenario_id == scenario_id)
        .where(TrainingScoreRecord.owner_id == user.id)
        .order_by(TrainingScoreRecord.created_at.desc())
        .limit(limit)
    )
    rows = await session.execute(stmt)
    return rows.scalars().all()


async def create_training_score_record(
    session: AsyncSession,
    user: User,
    scenario_id: str,
    *,
    score: TrainingScoreResponse,
    aar_record_id: str | None = None,
) -> TrainingScoreRecord:
    sc = await _load_or_404(session, scenario_id)
    _ensure_can_read(sc, user)
    payload = score.model_dump(mode="json")
    record = TrainingScoreRecord(
        scenario_id=sc.id,
        owner_id=user.id,
        runtime_scenario_id=score.runtime_scenario_id,
        aar_record_id=aar_record_id,
        overall_score=score.overall_score,
        grade=score.grade,
        confidence=score.confidence,
        score=payload,
        metrics=score.metrics,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


async def build_training_score_for_scenario(
    session: AsyncSession,
    user: User,
    sc: Scenario,
    scenario_id: str,
) -> TrainingScoreResponse:
    inner_id = runtime_scenario_id(sc.data)
    scenario_ids = [scenario_id]
    if inner_id and inner_id != scenario_id:
        scenario_ids.append(inner_id)
    events = await list_runtime_events(
        session,
        user,
        scenario_id=scenario_ids,
        limit=500,
    )
    aar_records = await list_aar_records(
        session,
        user,
        scenario_id,
        limit=50,
    )
    return build_training_score(sc, events, aar_records)


async def build_scenario_compare_items(
    session: AsyncSession,
    user: User,
    scenario_ids: Sequence[str],
) -> list[ScenarioCompareItem]:
    items: list[ScenarioCompareItem] = []
    for scenario_id in scenario_ids:
        sc = await get_scenario(session, user, scenario_id)
        score = await build_training_score_for_scenario(session, user, sc, scenario_id)
        inner_id = runtime_scenario_id(sc.data)
        timeline_ids = [scenario_id]
        if inner_id and inner_id != scenario_id:
            timeline_ids.append(inner_id)

        timeline_stmt = (
            select(
                func.count(RuntimeEvent.id),
                func.max(RuntimeEvent.created_at),
            )
            .where(RuntimeEvent.owner_id == user.id)
            .where(RuntimeEvent.scenario_id.in_(timeline_ids))
        )
        aar_stmt = (
            select(
                func.count(AarRecord.id),
                func.max(AarRecord.created_at),
            )
            .where(AarRecord.owner_id == user.id)
            .where(AarRecord.scenario_id == sc.id)
        )
        timeline_count, latest_event_at = (await session.execute(timeline_stmt)).one()
        aar_count, latest_aar_at = (await session.execute(aar_stmt)).one()

        items.append(
            ScenarioCompareItem(
                id=sc.id,
                name=sc.name,
                description=sc.description,
                is_template=sc.is_template,
                owner_id=sc.owner_id,
                version=sc.version,
                status=sc.status,
                branch_meta=sc.branch_meta,
                mission_count=sc.mission_count,
                unit_count=sc.unit_count,
                side_count=sc.side_count,
                created_at=sc.created_at,
                updated_at=sc.updated_at,
                training_score=score,
                timeline_event_count=int(timeline_count or 0),
                latest_event_at=latest_event_at,
                aar_count=int(aar_count or 0),
                latest_aar_at=latest_aar_at,
            )
        )
    return items


def _normalize_compare_ids(scenario_ids: Sequence[str]) -> list[str]:
    ordered_ids = [str(item).strip() for item in scenario_ids if str(item).strip()]
    deduped = list(dict.fromkeys(ordered_ids))
    if len(deduped) < 2:
        raise ScenarioInvalidError(
            "scenario_ids", "comparison requires at least two scenarios"
        )
    if len(deduped) > 4:
        raise ScenarioInvalidError(
            "scenario_ids", "comparison supports up to four scenarios"
        )
    return deduped


def _normalize_compare_session_state(
    *,
    baseline_id: str,
    scenario_ids: list[str],
    state: ScenarioCompareSessionState,
) -> ScenarioCompareSessionState:
    if state.baseline_id != baseline_id:
        raise ScenarioInvalidError(
            "state.baseline_id", "state baseline_id must match request baseline_id"
        )
    if baseline_id not in scenario_ids:
        raise ScenarioInvalidError(
            "baseline_id", "baseline must be included in scenario_ids"
        )

    normalized_sources: dict[str, str] = {}
    for scenario_id, source_id in state.selected_sources.items():
        normalized_scenario_id = str(scenario_id).strip()
        normalized_source_id = str(source_id).strip() or "live"
        if normalized_scenario_id not in scenario_ids:
            raise ScenarioInvalidError(
                "state.selected_sources",
                "state references scenario ids outside scenario_ids",
            )
        normalized_sources[normalized_scenario_id] = normalized_source_id

    for scenario_id in scenario_ids:
        normalized_sources.setdefault(scenario_id, "live")

    return ScenarioCompareSessionState(
        baseline_id=baseline_id,
        selected_sources=normalized_sources,
    )


def _default_compare_session_title(baseline: Scenario) -> str:
    return f"{baseline.name} 多方案对比"


def _validate_compare_snapshot(
    payload: ScenarioCompareReportCreate,
    scenario_ids: list[str],
) -> ScenarioCompareSnapshot:
    snapshot = payload.snapshot
    if snapshot.baseline_id != payload.baseline_id:
        raise ScenarioInvalidError(
            "baseline_id", "snapshot baseline_id must match request baseline_id"
        )
    snapshot_ids = [item.id for item in snapshot.items]
    if list(dict.fromkeys(snapshot_ids)) != snapshot_ids:
        raise ScenarioInvalidError(
            "snapshot.items", "snapshot scenario ids must be unique"
        )
    if set(snapshot_ids) != set(scenario_ids):
        raise ScenarioInvalidError(
            "snapshot.items", "snapshot scenario ids must match scenario_ids"
        )
    if payload.baseline_id not in snapshot_ids:
        raise ScenarioInvalidError(
            "baseline_id", "baseline must be included in scenario_ids"
        )
    return snapshot


async def create_compare_report(
    session: AsyncSession,
    user: User,
    *,
    payload: ScenarioCompareReportCreate,
) -> ScenarioCompareReport:
    scenario_ids = _normalize_compare_ids(payload.scenario_ids)
    _validate_compare_snapshot(payload, scenario_ids)

    scenarios_by_id: dict[str, Scenario] = {}
    for scenario_id in scenario_ids:
        scenarios_by_id[scenario_id] = await get_scenario(session, user, scenario_id)

    baseline = scenarios_by_id.get(payload.baseline_id)
    if baseline is None:
        raise ScenarioInvalidError(
            "baseline_id", "baseline must be included in scenario_ids"
        )

    title = (payload.title or "").strip() or f"{baseline.name} 对比报告"
    if len(title) > 120:
        raise ScenarioInvalidError("title", "exceeds 120 chars")

    report = ScenarioCompareReport(
        owner_id=user.id,
        title=title,
        baseline_scenario_id=payload.baseline_id,
        scenario_ids=scenario_ids,
        snapshot=payload.snapshot.model_dump(mode="json"),
    )
    session.add(report)
    await session.commit()
    await session.refresh(report)
    return report


async def create_compare_session(
    session: AsyncSession,
    user: User,
    *,
    payload: ScenarioCompareSessionCreate,
) -> ScenarioCompareSession:
    scenario_ids = _normalize_compare_ids(payload.scenario_ids)
    baseline_id = payload.baseline_id
    normalized_state = _normalize_compare_session_state(
        baseline_id=baseline_id,
        scenario_ids=scenario_ids,
        state=payload.state,
    )

    scenarios_by_id: dict[str, Scenario] = {}
    for scenario_id in scenario_ids:
        scenarios_by_id[scenario_id] = await get_scenario(session, user, scenario_id)

    baseline = scenarios_by_id.get(baseline_id)
    if baseline is None:
        raise ScenarioInvalidError(
            "baseline_id", "baseline must be included in scenario_ids"
        )

    source_scenario_id = None
    if payload.source_scenario_id:
        source_scenario_id = str(payload.source_scenario_id).strip()
        if not source_scenario_id:
            source_scenario_id = None
        else:
            await get_scenario(session, user, source_scenario_id)

    title = (payload.title or "").strip() or _default_compare_session_title(baseline)
    if len(title) > 120:
        raise ScenarioInvalidError("title", "exceeds 120 chars")

    compare_session = ScenarioCompareSession(
        owner_id=user.id,
        title=title,
        source_scenario_id=source_scenario_id,
        baseline_scenario_id=baseline_id,
        scenario_ids=scenario_ids,
        state=normalized_state.model_dump(mode="json"),
    )
    session.add(compare_session)
    await session.commit()
    await session.refresh(compare_session)
    return compare_session


async def list_compare_sessions(
    session: AsyncSession,
    user: User,
    *,
    limit: int = 50,
) -> Sequence[ScenarioCompareSession]:
    limit = max(1, min(int(limit), 100))
    stmt = (
        select(ScenarioCompareSession)
        .where(ScenarioCompareSession.owner_id == user.id)
        .order_by(ScenarioCompareSession.updated_at.desc())
        .limit(limit)
    )
    rows = await session.execute(stmt)
    return rows.scalars().all()


async def get_compare_session(
    session: AsyncSession,
    user: User,
    compare_session_id: str,
) -> ScenarioCompareSession:
    compare_session = await session.get(ScenarioCompareSession, compare_session_id)
    if compare_session is None:
        raise ScenarioNotFoundError(compare_session_id)
    if str(compare_session.owner_id) != str(user.id):
        raise ScenarioForbiddenError(compare_session.id, "not the owner")

    for scenario_id in compare_session.scenario_ids:
        await get_scenario(session, user, scenario_id)
    if compare_session.source_scenario_id:
        await get_scenario(session, user, compare_session.source_scenario_id)

    return compare_session


async def update_compare_session(
    session: AsyncSession,
    user: User,
    compare_session_id: str,
    *,
    payload: ScenarioCompareSessionUpdate,
) -> ScenarioCompareSession:
    compare_session = await get_compare_session(session, user, compare_session_id)

    next_scenario_ids = (
        _normalize_compare_ids(payload.scenario_ids)
        if payload.scenario_ids is not None
        else list(compare_session.scenario_ids)
    )
    next_baseline_id = payload.baseline_id or compare_session.baseline_scenario_id
    raw_state = payload.state or ScenarioCompareSessionState.model_validate(
        compare_session.state
    )
    normalized_state = _normalize_compare_session_state(
        baseline_id=next_baseline_id,
        scenario_ids=next_scenario_ids,
        state=raw_state,
    )

    scenarios_by_id: dict[str, Scenario] = {}
    for scenario_id in next_scenario_ids:
        scenarios_by_id[scenario_id] = await get_scenario(session, user, scenario_id)

    baseline = scenarios_by_id.get(next_baseline_id)
    if baseline is None:
        raise ScenarioInvalidError(
            "baseline_id", "baseline must be included in scenario_ids"
        )

    if payload.title is not None:
        title = payload.title.strip() or _default_compare_session_title(baseline)
        if len(title) > 120:
            raise ScenarioInvalidError("title", "exceeds 120 chars")
        compare_session.title = title

    compare_session.baseline_scenario_id = next_baseline_id
    compare_session.scenario_ids = next_scenario_ids
    compare_session.state = normalized_state.model_dump(mode="json")

    await session.commit()
    await session.refresh(compare_session)
    return compare_session


async def delete_compare_session(
    session: AsyncSession,
    user: User,
    compare_session_id: str,
) -> None:
    compare_session = await session.get(ScenarioCompareSession, compare_session_id)
    if compare_session is None:
        raise ScenarioNotFoundError(compare_session_id)
    if str(compare_session.owner_id) != str(user.id):
        raise ScenarioForbiddenError(compare_session.id, "not the owner")
    await session.delete(compare_session)
    await session.commit()


async def fork_compare_session(
    session: AsyncSession,
    user: User,
    source_scenario_id: str,
    *,
    payload: ScenarioCompareForkCreate,
) -> ScenarioCompareSession:
    source = await get_scenario(session, user, source_scenario_id)

    branch_count = int(payload.branch_count)
    branches: list[Scenario] = []
    for index in range(branch_count):
        branch = await create_branch_scenario(
            session,
            user,
            source.id,
            name=f"{source.name} / 分支 {index + 1}",
            branch_label=f"方案 {index + 1}",
            description=source.description,
            status="draft",
        )
        branches.append(branch)

    scenario_ids = [source.id, *[branch.id for branch in branches]]
    compare_session = await create_compare_session(
        session,
        user,
        payload=ScenarioCompareSessionCreate(
            title=f"{source.name} {branch_count}方案对比",
            source_scenario_id=source.id,
            baseline_id=source.id,
            scenario_ids=scenario_ids,
            state=ScenarioCompareSessionState(
                baseline_id=source.id,
                selected_sources={scenario_id: "live" for scenario_id in scenario_ids},
            ),
        ),
    )
    return compare_session


async def list_compare_reports(
    session: AsyncSession,
    user: User,
    *,
    limit: int = 50,
) -> Sequence[ScenarioCompareReport]:
    limit = max(1, min(int(limit), 100))
    stmt = (
        select(ScenarioCompareReport)
        .where(ScenarioCompareReport.owner_id == user.id)
        .order_by(ScenarioCompareReport.created_at.desc())
        .limit(limit)
    )
    rows = await session.execute(stmt)
    return rows.scalars().all()


async def delete_compare_report(
    session: AsyncSession,
    user: User,
    report_id: str,
) -> None:
    report = await session.get(ScenarioCompareReport, report_id)
    if report is None:
        raise ScenarioNotFoundError(report_id)
    if str(report.owner_id) != str(user.id):
        raise ScenarioForbiddenError(report.id, "not the owner")
    await session.delete(report)
    await session.commit()
