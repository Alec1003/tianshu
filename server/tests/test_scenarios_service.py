"""service 层关键路径回归（happy + 权限错 + 校验错）。

MCP tools 是 service 的薄壳；service 过这套测试 ≈ tools 业务正确。MCP
协议层（stdio JSON-RPC、CallTool 序列化）走 Claude Desktop 端到端验证。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.scenarios import service as svc
from app.scenarios.errors import (
    ScenarioForbiddenError,
    ScenarioInvalidError,
    ScenarioNotFoundError,
    ScenarioTemplateReadOnlyError,
)
from app.scenarios.models import Scenario
from app.scenarios.schemas import (
    TrainingScoreDimension,
    TrainingScoreResponse,
)


pytestmark = pytest.mark.asyncio


# ---------- create + get -----------------------------------------------------


async def test_create_then_get_happy(db_session, user):
    sc = await svc.create_scenario(
        db_session,
        user,
        name="My Drill",
        description="quick test",
        data={"currentScenario": {"id": "demo", "sides": []}},
    )
    assert sc.id
    assert sc.is_template is False
    assert sc.owner_id == user.id

    fetched = await svc.get_scenario(db_session, user, sc.id)
    assert fetched.id == sc.id
    assert fetched.name == "My Drill"


async def test_create_strips_name_whitespace(db_session, user):
    sc = await svc.create_scenario(
        db_session, user, name="   trimmed  ", data={}
    )
    assert sc.name == "trimmed"


async def test_create_rejects_empty_name(db_session, user):
    with pytest.raises(ScenarioInvalidError) as exc_info:
        await svc.create_scenario(db_session, user, name="   ", data={})
    assert exc_info.value.code == "scenario_invalid"
    assert exc_info.value.details.get("field") == "name"


async def test_create_rejects_non_dict_data(db_session, user):
    with pytest.raises(ScenarioInvalidError):
        await svc.create_scenario(
            db_session, user, name="x", data="not-a-dict"  # type: ignore[arg-type]
        )


async def test_create_falls_back_to_draft_for_unknown_status(db_session, user):
    sc = await svc.create_scenario(
        db_session, user, name="x", data={}, status="bogus"
    )
    assert sc.status == "draft"


# ---------- get permissions --------------------------------------------------


async def test_get_404_when_missing(db_session, user):
    with pytest.raises(ScenarioNotFoundError):
        await svc.get_scenario(db_session, user, "nope")


async def test_get_forbidden_for_other_user(db_session, user, other_user):
    sc = await svc.create_scenario(
        db_session, user, name="private", data={"k": 1}
    )
    with pytest.raises(ScenarioForbiddenError):
        await svc.get_scenario(db_session, other_user, sc.id)


async def test_get_allows_template_for_anyone(db_session, user, other_user):
    # Hand-build a template row (not via create_scenario which forces
    # owner_id and is_template=False).
    tpl = Scenario(
        id="tpl-test",
        name="System Template",
        description="",
        data={"currentScenario": {"sides": []}},
        is_template=True,
        owner_id=None,
        status="draft",
    )
    db_session.add(tpl)
    await db_session.commit()

    # Both users can fetch it.
    fetched_user = await svc.get_scenario(db_session, user, tpl.id)
    fetched_other = await svc.get_scenario(db_session, other_user, tpl.id)
    assert fetched_user.is_template is True
    assert fetched_other.is_template is True


# ---------- update -----------------------------------------------------------


async def test_update_data_bumps_version(db_session, user):
    sc = await svc.create_scenario(db_session, user, name="x", data={"a": 1})
    assert sc.version == 1
    sc2 = await svc.update_scenario(
        db_session, user, sc.id, data={"a": 2}
    )
    assert sc2.version == 2
    assert sc2.data == {"a": 2}


async def test_update_meta_only_no_version_bump(db_session, user):
    sc = await svc.create_scenario(db_session, user, name="x", data={})
    sc2 = await svc.update_scenario(
        db_session, user, sc.id, name="renamed", description="new"
    )
    assert sc2.version == 1
    assert sc2.name == "renamed"
    assert sc2.description == "new"


async def test_update_rejects_invalid_status(db_session, user):
    sc = await svc.create_scenario(db_session, user, name="x", data={})
    with pytest.raises(ScenarioInvalidError) as exc_info:
        await svc.update_scenario(db_session, user, sc.id, status="dead")
    assert exc_info.value.details.get("field") == "status"


async def test_update_forbidden_for_other_user(db_session, user, other_user):
    sc = await svc.create_scenario(db_session, user, name="x", data={})
    with pytest.raises(ScenarioForbiddenError):
        await svc.update_scenario(
            db_session, other_user, sc.id, name="hijacked"
        )


async def test_update_template_readonly_for_non_superuser(db_session, user):
    tpl = Scenario(
        id="tpl-readonly",
        name="t",
        description="",
        data={},
        is_template=True,
        owner_id=None,
        status="draft",
    )
    db_session.add(tpl)
    await db_session.commit()
    with pytest.raises(ScenarioTemplateReadOnlyError):
        await svc.update_scenario(db_session, user, tpl.id, name="hack")


async def test_update_template_allowed_for_superuser(db_session, superuser):
    tpl = Scenario(
        id="tpl-edit",
        name="t",
        description="",
        data={},
        is_template=True,
        owner_id=None,
        status="draft",
    )
    db_session.add(tpl)
    await db_session.commit()
    sc2 = await svc.update_scenario(
        db_session, superuser, tpl.id, description="curated"
    )
    assert sc2.description == "curated"


# ---------- delete -----------------------------------------------------------


async def test_delete_own_ok(db_session, user):
    sc = await svc.create_scenario(db_session, user, name="x", data={})
    await svc.delete_scenario(db_session, user, sc.id)
    with pytest.raises(ScenarioNotFoundError):
        await svc.get_scenario(db_session, user, sc.id)


async def test_delete_template_forbidden_even_for_superuser(db_session, superuser):
    tpl = Scenario(
        id="tpl-nodelete",
        name="t",
        description="",
        data={},
        is_template=True,
        owner_id=None,
        status="draft",
    )
    db_session.add(tpl)
    await db_session.commit()
    with pytest.raises(ScenarioForbiddenError):
        await svc.delete_scenario(db_session, superuser, tpl.id)


# ---------- list -------------------------------------------------------------


async def test_list_includes_own_and_templates(db_session, user, other_user):
    own = await svc.create_scenario(db_session, user, name="mine", data={})
    await svc.create_scenario(db_session, other_user, name="theirs", data={})
    tpl = Scenario(
        id="tpl-list",
        name="t",
        description="",
        data={},
        is_template=True,
        owner_id=None,
        status="draft",
    )
    db_session.add(tpl)
    await db_session.commit()

    rows = await svc.list_scenarios(db_session, user, include_templates=True)
    ids = {r.id for r in rows}
    assert own.id in ids
    assert tpl.id in ids
    # Other user's scenario must NOT leak.
    assert all(r.owner_id != other_user.id for r in rows if not r.is_template)


async def test_list_excludes_templates_when_flag_off(db_session, user):
    await svc.create_scenario(db_session, user, name="mine", data={})
    tpl = Scenario(
        id="tpl-excluded",
        name="t",
        description="",
        data={},
        is_template=True,
        owner_id=None,
        status="draft",
    )
    db_session.add(tpl)
    await db_session.commit()

    rows = await svc.list_scenarios(db_session, user, include_templates=False)
    assert all(not r.is_template for r in rows)


# ---------- AAR --------------------------------------------------------------


async def test_create_aar_record_and_list(db_session, user):
    sc = await svc.create_scenario(db_session, user, name="game", data={})
    rec = await svc.create_aar_record(
        db_session,
        user,
        sc.id,
        outcome_reason="annihilation",
        winner_side_id="BLUE",
        summary={"score": 1},
        ended_at=datetime.now(tz=timezone.utc),
    )
    assert rec.id
    records = await svc.list_aar_records(db_session, user, sc.id)
    assert len(records) == 1
    assert records[0].id == rec.id


async def test_create_aar_rejects_long_outcome_reason(db_session, user):
    sc = await svc.create_scenario(db_session, user, name="x", data={})
    with pytest.raises(ScenarioInvalidError):
        await svc.create_aar_record(
            db_session,
            user,
            sc.id,
            outcome_reason="x" * 50,
            winner_side_id="",
            summary={},
            ended_at=datetime.now(tz=timezone.utc),
        )


# ---------- Training score records -----------------------------------------


async def test_create_and_list_training_score_records(db_session, user):
    sc = await svc.create_scenario(db_session, user, name="score", data={})
    score = TrainingScoreResponse(
        scenario_id=sc.id,
        runtime_scenario_id="runtime-score",
        generated_at=datetime.now(tz=timezone.utc),
        overall_score=86,
        grade="良好",
        confidence="high",
        dimensions=[
            TrainingScoreDimension(
                key="task_effectiveness",
                label="任务达成",
                score=86,
                weight=1,
                summary="ok",
                evidence=[],
            )
        ],
        metrics={"event_count": 5},
        strengths=["stable"],
        improvements=[],
    )

    record = await svc.create_training_score_record(
        db_session,
        user,
        sc.id,
        score=score,
    )
    records = await svc.list_training_score_records(db_session, user, sc.id)

    assert record.id
    assert record.overall_score == 86
    assert record.score["overall_score"] == 86
    assert record.metrics == {"event_count": 5}
    assert [item.id for item in records] == [record.id]
