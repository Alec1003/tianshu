"""/api/scenarios CRUD + AAR endpoints.

Permission model (v1, single-user-owned):
    list   -- own + system templates
    get    -- own OR system template
    create -- any logged-in user
    update -- only owner; system templates are read-only
    delete -- only owner; system templates are read-only
"""

from __future__ import annotations

from typing import Sequence

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.users import current_active_user
from app.db.session import get_async_session
from app.scenarios.models import AarRecord, Scenario
from app.scenarios.schemas import (
    AarRecordCreate,
    AarRecordRead,
    ScenarioCreate,
    ScenarioDetail,
    ScenarioListItem,
    ScenarioUpdate,
)

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


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
    stmt = select(Scenario)
    if include_templates:
        stmt = stmt.where(
            (Scenario.owner_id == str(user.id)) | (Scenario.is_template == True)  # noqa: E712
        )
    else:
        stmt = stmt.where(Scenario.owner_id == str(user.id))
    stmt = stmt.order_by(Scenario.is_template.desc(), Scenario.updated_at.desc())
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/{scenario_id}", response_model=ScenarioDetail)
async def get_scenario(
    scenario_id: str,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Scenario:
    sc = await session.get(Scenario, scenario_id)
    if sc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    # Visibility: owner OR template
    if not sc.is_template and sc.owner_id != str(user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return sc


# ---------- create / update / delete ----------
@router.post("", response_model=ScenarioDetail, status_code=status.HTTP_201_CREATED)
async def create_scenario(
    payload: ScenarioCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Scenario:
    sc = Scenario(
        name=payload.name,
        description=payload.description,
        data=payload.data,
        is_template=False,
        owner_id=str(user.id),
    )
    session.add(sc)
    await session.commit()
    await session.refresh(sc)
    return sc


@router.patch("/{scenario_id}", response_model=ScenarioDetail)
async def update_scenario(
    scenario_id: str,
    payload: ScenarioUpdate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Scenario:
    sc = await session.get(Scenario, scenario_id)
    if sc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    if sc.is_template:
        # Only superusers can edit system templates; regular users must "save
        # as" to fork. Keeping the DRY rule explicit avoids accidental edits.
        if not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="templates are read-only; use 'save as'",
            )
    elif sc.owner_id != str(user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    if payload.name is not None:
        sc.name = payload.name
    if payload.description is not None:
        sc.description = payload.description
    if payload.data is not None:
        sc.data = payload.data
        sc.version += 1
    await session.commit()
    await session.refresh(sc)
    return sc


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
    sc = await session.get(Scenario, scenario_id)
    if sc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    if sc.is_template:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="templates cannot be deleted",
        )
    if sc.owner_id != str(user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    await session.delete(sc)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- AAR records (per scenario) ----------
@router.get("/{scenario_id}/aar", response_model=list[AarRecordRead])
async def list_aar_records(
    scenario_id: str,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Sequence[AarRecord]:
    sc = await session.get(Scenario, scenario_id)
    if sc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    if not sc.is_template and sc.owner_id != str(user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    stmt = (
        select(AarRecord)
        .where(AarRecord.scenario_id == scenario_id)
        .where(AarRecord.owner_id == str(user.id))
        .order_by(AarRecord.created_at.desc())
        .limit(50)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


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
    rec = AarRecord(
        scenario_id=scenario_id,
        owner_id=str(user.id),
        outcome_reason=payload.outcome_reason,
        winner_side_id=payload.winner_side_id,
        summary=payload.summary,
        ended_at=payload.ended_at,
    )
    session.add(rec)
    await session.commit()
    await session.refresh(rec)
    return rec
