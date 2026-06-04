"""Scenario business functions, transport-agnostic.

一句话：把当前在 ``router.py`` 里的 endpoint handler 中的业务部分提取成
普通 async 函数，让 HTTP / MCP / 未来的 CLI 都能复用同一份权限/数据/状态
机判断。

为什么 router.py 不立刻接入：本切片范围只做 MCP，不动 FastAPI 路由以保
证零回归风险；下一切片再让 router 走 service 去掉重复。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.tianshu_runtime.timeline import (
    list_runtime_events,
    runtime_scenario_id,
)
from app.auth.models import User
from app.scenarios.errors import (
    ScenarioForbiddenError,
    ScenarioInvalidError,
    ScenarioNotFoundError,
    ScenarioTemplateReadOnlyError,
)
from app.scenarios.models import (
    AarRecord,
    Scenario,
    TrainingScoreRecord,
)
from app.scenarios.schemas import (
    VALID_STATUSES,
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
    try:
        sc = await _load_or_404(session, scenario_id)
        _ensure_can_read(sc, user)
    except ScenarioNotFoundError:
        # AAR creation intentionally supports runtime-only/imported scenario ids
        # as correlation tags. Listing keeps the same owner scope, so it can
        # safely return the caller's own free-form records.
        pass
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
