from __future__ import annotations

import pytest

from app.ai.command_governance import CommandApprovalQueue
from app.ai.command_service import (
    CommandProposalNotFoundError,
    get_command_proposal,
    list_command_proposals,
    save_command_proposal,
)
from app.ai.models import StructuredCommandStep

from .test_command_governance import FakeRegistry, FakeRuntime


@pytest.mark.asyncio
async def test_command_proposal_round_trips_through_database(db_session, user):
    queue = CommandApprovalQueue(FakeRuntime(), FakeRegistry())  # type: ignore[arg-type]
    proposal = queue.create_proposal(
        command="advance one second",
        source="mcp",
        steps=[
            StructuredCommandStep(
                id="s1",
                skill="simulation_step",
                parameters={"steps": 1},
                summary="Advance simulation 1 seconds",
            )
        ],
    )

    saved = await save_command_proposal(db_session, user, proposal)
    loaded = await get_command_proposal(db_session, user, saved.id)
    listed = await list_command_proposals(db_session, user)

    assert loaded.id == proposal.id
    assert loaded.source == "mcp"
    assert loaded.steps[0].skill == "simulation_step"
    assert [item.id for item in listed] == [proposal.id]


@pytest.mark.asyncio
async def test_persisted_proposal_can_be_hydrated_and_executed(db_session, user):
    registry = FakeRegistry()
    queue = CommandApprovalQueue(FakeRuntime(), registry)  # type: ignore[arg-type]
    proposal = queue.create_proposal(
        command="advance one second",
        source="regex",
        steps=[
            StructuredCommandStep(
                id="s1",
                skill="simulation_step",
                parameters={"steps": 1},
            )
        ],
    )
    saved = await save_command_proposal(db_session, user, proposal)

    fresh_queue = CommandApprovalQueue(FakeRuntime(), registry)  # type: ignore[arg-type]
    loaded = await get_command_proposal(db_session, user, saved.id)
    executed = fresh_queue.approve_and_execute_loaded(loaded)
    persisted = await save_command_proposal(db_session, user, executed)

    assert persisted.status == "executed"
    assert persisted.execution[0].skill == "simulation_step"
    assert registry.calls == [("simulation_step", {"steps": 1})]


@pytest.mark.asyncio
async def test_command_proposals_are_scoped_by_scenario(db_session, user):
    queue = CommandApprovalQueue(FakeRuntime(), FakeRegistry())  # type: ignore[arg-type]
    proposal = queue.create_proposal(
        command="advance one second",
        source="mcp",
        steps=[
            StructuredCommandStep(
                id="s1",
                skill="simulation_step",
                parameters={"steps": 1},
            )
        ],
    )

    saved = await save_command_proposal(
        db_session,
        user,
        proposal,
        scenario_id="scenario-alpha",
    )
    assert await get_command_proposal(
        db_session,
        user,
        saved.id,
        scenario_id="scenario-alpha",
    )
    assert [
        item.id
        for item in await list_command_proposals(
            db_session,
            user,
            scenario_id="scenario-alpha",
        )
    ] == [saved.id]
    assert (
        await list_command_proposals(
            db_session,
            user,
            scenario_id="scenario-bravo",
        )
        == []
    )

    with pytest.raises(CommandProposalNotFoundError):
        await get_command_proposal(
            db_session,
            user,
            saved.id,
            scenario_id="scenario-bravo",
        )
