"""Persistence helpers for command approval proposals."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.command_models import CommandProposalRecord, CommandProposalStepRecord
from app.ai.models import (
    CommandAdjudicationResult,
    CommandProposal,
    SkillExecutionResult,
    StructuredCommandStep,
)
from app.tianshu_runtime.persistence import runtime_context_id
from app.auth.models import User


class CommandProposalNotFoundError(ValueError):
    """Raised when a proposal is absent or outside the current user's scope."""


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _dt_to_str(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _same_owner(record: CommandProposalRecord, user: User) -> bool:
    return str(record.owner_id) == str(user.id)


def _record_to_proposal(record: CommandProposalRecord) -> CommandProposal:
    return CommandProposal(
        id=record.id,
        command=record.command,
        source=record.source,
        status=record.status,
        created_at=_dt_to_str(record.created_at),
        updated_at=_dt_to_str(record.updated_at),
        steps=[
            StructuredCommandStep(
                id=step.step_id,
                skill=step.skill,
                parameters=step.parameters or {},
                source_text=step.source_text,
                summary=step.summary,
                risk=step.risk,
                writes_runtime=step.writes_runtime,
            )
            for step in sorted(record.steps, key=lambda item: item.position)
        ],
        adjudication=CommandAdjudicationResult.model_validate(
            record.adjudication or {}
        ),
        plan_metadata=record.plan_metadata or {},
        execution=[
            SkillExecutionResult.model_validate(item)
            for item in (record.execution or [])
        ],
        error=record.error,
    )


async def save_command_proposal(
    session: AsyncSession,
    user: User,
    proposal: CommandProposal,
    scenario_id: str | None = None,
) -> CommandProposal:
    """Create or update a proposal row scoped to ``user``."""

    context_id = runtime_context_id(scenario_id)
    record = await session.get(CommandProposalRecord, proposal.id)
    if record is None:
        record = CommandProposalRecord(
            id=proposal.id,
            owner_id=user.id,
            scenario_id=context_id,
            command=proposal.command,
            source=proposal.source,
            status=proposal.status,
            adjudication=proposal.adjudication.model_dump(mode="json"),
            plan_metadata=proposal.plan_metadata or {},
            execution=[
                item.model_dump(mode="json") for item in proposal.execution
            ],
            error=proposal.error,
            created_at=_parse_dt(proposal.created_at),
            updated_at=_parse_dt(proposal.updated_at),
        )
        session.add(record)
    else:
        if not _same_owner(record, user):
            raise CommandProposalNotFoundError(proposal.id)
        if record.scenario_id != context_id:
            raise CommandProposalNotFoundError(proposal.id)
        record.scenario_id = context_id
        record.command = proposal.command
        record.source = proposal.source
        record.status = proposal.status
        record.adjudication = proposal.adjudication.model_dump(mode="json")
        record.plan_metadata = proposal.plan_metadata or {}
        record.execution = [
            item.model_dump(mode="json") for item in proposal.execution
        ]
        record.error = proposal.error
        record.updated_at = _parse_dt(proposal.updated_at)

    await session.flush()
    await session.execute(
        delete(CommandProposalStepRecord).where(
            CommandProposalStepRecord.proposal_id == proposal.id
        )
    )
    for index, step in enumerate(proposal.steps):
        session.add(
            CommandProposalStepRecord(
                proposal_id=proposal.id,
                position=index,
                step_id=step.id,
                skill=step.skill,
                parameters=step.parameters,
                source_text=step.source_text,
                summary=step.summary,
                risk=step.risk,
                writes_runtime=step.writes_runtime,
            )
        )

    await session.commit()
    return await get_command_proposal(
        session,
        user,
        proposal.id,
        scenario_id=scenario_id,
    )


async def get_command_proposal(
    session: AsyncSession,
    user: User,
    proposal_id: str,
    scenario_id: str | None = None,
) -> CommandProposal:
    context_id = runtime_context_id(scenario_id)
    stmt = (
        select(CommandProposalRecord)
        .options(selectinload(CommandProposalRecord.steps))
        .where(
            CommandProposalRecord.id == proposal_id,
            CommandProposalRecord.owner_id == user.id,
            CommandProposalRecord.scenario_id == context_id,
        )
    )
    result = await session.execute(stmt)
    record = result.scalar_one_or_none()
    if record is None:
        raise CommandProposalNotFoundError(proposal_id)
    return _record_to_proposal(record)


async def list_command_proposals(
    session: AsyncSession,
    user: User,
    *,
    scenario_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> Sequence[CommandProposal]:
    context_id = runtime_context_id(scenario_id)
    stmt = (
        select(CommandProposalRecord)
        .options(selectinload(CommandProposalRecord.steps))
        .where(
            CommandProposalRecord.owner_id == user.id,
            CommandProposalRecord.scenario_id == context_id,
        )
    )
    if status:
        stmt = stmt.where(CommandProposalRecord.status == status)
    stmt = stmt.order_by(CommandProposalRecord.created_at.desc()).limit(
        max(1, min(limit, 200))
    )
    result = await session.execute(stmt)
    return [_record_to_proposal(record) for record in result.scalars().all()]
