"""service 层关键路径回归（happy + 权限错 + 校验错）。

MCP tools 是 service 的薄壳；service 过这套测试 ≈ tools 业务正确。MCP
协议层（stdio JSON-RPC、CallTool 序列化）走 Claude Desktop 端到端验证。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.ai.bridge import TianShuOpenClawBridge
from app.tianshu_runtime.models import RuntimeEvent
from app.scenarios import service as svc
from app.scenarios.errors import (
    ScenarioForbiddenError,
    ScenarioInvalidError,
    ScenarioNotFoundError,
    ScenarioTemplateReadOnlyError,
)
from app.scenarios.models import Scenario
from app.scenarios.schemas import (
    ScenarioBatchSimulationRequest,
    ScenarioCompareForkCreate,
    ScenarioCompareReportCreate,
    ScenarioCompareSessionCreate,
    ScenarioCompareSessionState,
    ScenarioCompareSessionUpdate,
    ScenarioCompareSnapshot,
    ScenarioCompareSnapshotDeltas,
    ScenarioCompareSnapshotItem,
    ScenarioCompareSnapshotScore,
    ScenarioCompareSnapshotSource,
    ScenarioCompareSnapshotSummary,
    ScenarioPlanOption,
    ScenarioPlanSetCreate,
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


async def test_create_branch_scenario_preserves_lineage_and_regenerates_runtime_id(
    db_session,
    user,
):
    source = await svc.create_scenario(
        db_session,
        user,
        name="Base Plan",
        description="baseline",
        data={
            "currentScenario": {
                "id": "runtime-base",
                "name": "Base Plan",
                "sides": [],
                "missions": [],
                "aircraft": [],
                "ships": [],
                "facilities": [],
                "airbases": [],
            }
        },
    )

    branch = await svc.create_branch_scenario(
        db_session,
        user,
        source.id,
        name="Base Plan / Alpha",
    )

    assert branch.id != source.id
    assert branch.owner_id == user.id
    assert branch.branch_meta is not None
    assert branch.branch_meta["parent_scenario_id"] == source.id
    assert branch.branch_meta["root_scenario_id"] == source.id
    assert branch.branch_meta["created_from_version"] == source.version
    assert branch.branch_meta["branch_depth"] == 1
    assert branch.data["currentScenario"]["name"] == "Base Plan / Alpha"
    assert branch.data["currentScenario"]["id"] != source.data["currentScenario"]["id"]


async def test_build_scenario_compare_items_aggregates_score_timeline_and_aar(
    db_session,
    user,
):
    base = await svc.create_scenario(
        db_session,
        user,
        name="Base",
        data={
            "currentScenario": {
                "id": "runtime-base",
                "name": "Base",
                "sides": [],
                "missions": [],
                "aircraft": [],
                "ships": [],
                "facilities": [],
                "airbases": [],
            }
        },
    )
    branch = await svc.create_branch_scenario(
        db_session,
        user,
        base.id,
        name="Base / Beta",
    )
    db_session.add(
        RuntimeEvent(
            owner_id=user.id,
            scenario_id=base.id,
            event_type="command.executed",
            category="command",
            action="deploy",
            actor="operator",
            summary="deploy unit",
            payload={},
            unit_changes=[],
        )
    )
    await db_session.commit()
    await svc.create_aar_record(
        db_session,
        user,
        base.id,
        outcome_reason="timeout",
        winner_side_id="blue",
        summary={"scenarioName": "Base"},
        ended_at=datetime.now(tz=timezone.utc),
    )

    items = await svc.build_scenario_compare_items(
        db_session,
        user,
        [base.id, branch.id],
    )
    by_id = {item.id: item for item in items}

    assert set(by_id) == {base.id, branch.id}
    assert by_id[base.id].timeline_event_count == 1
    assert by_id[base.id].aar_count == 1
    assert by_id[base.id].training_score.scenario_id == base.id
    assert by_id[branch.id].branch_meta is not None
    assert by_id[branch.id].branch_meta.parent_scenario_id == base.id


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


def compare_snapshot(
    scenario_ids: list[str],
    baseline_id: str,
) -> ScenarioCompareSnapshot:
    return ScenarioCompareSnapshot(
        generated_at=datetime.now(tz=timezone.utc),
        baseline_id=baseline_id,
        baseline_name="Baseline",
        items=[
            ScenarioCompareSnapshotItem(
                id=scenario_id,
                name=f"Scenario {index + 1}",
                baseline=scenario_id == baseline_id,
                source=ScenarioCompareSnapshotSource(
                    id="live",
                    label="实时评分",
                    archived_record_id=None,
                ),
                score=ScenarioCompareSnapshotScore(
                    overall_score=80 + index,
                    grade="A-",
                    confidence="high",
                    generated_at=datetime.now(tz=timezone.utc),
                ),
                score_deltas=ScenarioCompareSnapshotDeltas(
                    versus_baseline=None if scenario_id == baseline_id else index,
                    versus_latest_archived=None,
                    versus_live=None,
                ),
                summary=ScenarioCompareSnapshotSummary(
                    mission_count=4 + index,
                    unit_count=10 + index,
                    timeline_event_count=20 + index,
                    aar_count=index,
                ),
            )
            for index, scenario_id in enumerate(scenario_ids)
        ],
    )


async def test_create_list_and_delete_compare_report(db_session, user):
    base = await svc.create_scenario(db_session, user, name="Base", data={})
    branch = await svc.create_scenario(db_session, user, name="Branch", data={})
    snapshot = compare_snapshot([base.id, branch.id], base.id)

    report = await svc.create_compare_report(
        db_session,
        user,
        payload=ScenarioCompareReportCreate(
            title="Base 对比报告",
            baseline_id=base.id,
            scenario_ids=[base.id, branch.id],
            snapshot=snapshot,
        ),
    )
    listed = await svc.list_compare_reports(db_session, user)

    assert report.id
    assert report.baseline_scenario_id == base.id
    assert report.scenario_ids == [base.id, branch.id]
    assert report.snapshot["baseline_name"] == "Baseline"
    assert [item.id for item in listed] == [report.id]

    await svc.delete_compare_report(db_session, user, report.id)
    assert await svc.list_compare_reports(db_session, user) == []


async def test_create_compare_report_rejects_snapshot_mismatch(db_session, user):
    base = await svc.create_scenario(db_session, user, name="Base", data={})
    branch = await svc.create_scenario(db_session, user, name="Branch", data={})
    snapshot = compare_snapshot([base.id], base.id)

    with pytest.raises(ScenarioInvalidError) as exc_info:
        await svc.create_compare_report(
            db_session,
            user,
            payload=ScenarioCompareReportCreate(
                title="Mismatch",
                baseline_id=base.id,
                scenario_ids=[base.id, branch.id],
                snapshot=snapshot,
            ),
        )

    assert exc_info.value.details.get("field") == "snapshot.items"


async def test_create_update_list_and_delete_compare_session(db_session, user):
    base = await svc.create_scenario(db_session, user, name="Base", data={})
    branch = await svc.create_scenario(db_session, user, name="Branch", data={})

    compare_session = await svc.create_compare_session(
        db_session,
        user,
        payload=ScenarioCompareSessionCreate(
            title="Base 对比会话",
            source_scenario_id=base.id,
            baseline_id=base.id,
            scenario_ids=[base.id, branch.id],
            state=ScenarioCompareSessionState(
                baseline_id=base.id,
                selected_sources={base.id: "live", branch.id: "archived-1"},
            ),
        ),
    )

    listed = await svc.list_compare_sessions(db_session, user)
    fetched = await svc.get_compare_session(db_session, user, compare_session.id)

    assert compare_session.id
    assert compare_session.source_scenario_id == base.id
    assert compare_session.baseline_scenario_id == base.id
    assert compare_session.state["selected_sources"][branch.id] == "archived-1"
    assert [item.id for item in listed] == [compare_session.id]
    assert fetched.id == compare_session.id

    updated = await svc.update_compare_session(
        db_session,
        user,
        compare_session.id,
        payload=ScenarioCompareSessionUpdate(
            baseline_id=branch.id,
            state=ScenarioCompareSessionState(
                baseline_id=branch.id,
                selected_sources={base.id: "live", branch.id: "live"},
            ),
        ),
    )
    assert updated.baseline_scenario_id == branch.id
    assert updated.state["baseline_id"] == branch.id
    assert updated.state["selected_sources"][branch.id] == "live"

    await svc.delete_compare_session(db_session, user, compare_session.id)
    assert await svc.list_compare_sessions(db_session, user) == []


async def test_create_compare_session_rejects_state_mismatch(db_session, user):
    base = await svc.create_scenario(db_session, user, name="Base", data={})
    branch = await svc.create_scenario(db_session, user, name="Branch", data={})

    with pytest.raises(ScenarioInvalidError) as exc_info:
        await svc.create_compare_session(
            db_session,
            user,
            payload=ScenarioCompareSessionCreate(
                title="Mismatch",
                source_scenario_id=base.id,
                baseline_id=base.id,
                scenario_ids=[base.id, branch.id],
                state=ScenarioCompareSessionState(
                    baseline_id=branch.id,
                    selected_sources={base.id: "live", branch.id: "live"},
                ),
            ),
        )

    assert exc_info.value.details.get("field") == "state.baseline_id"


async def test_fork_compare_session_creates_source_and_three_branches(
    db_session,
    user,
):
    source = await svc.create_scenario(
        db_session,
        user,
        name="Base Plan",
        description="baseline",
        data={
            "currentScenario": {
                "id": "runtime-base",
                "name": "Base Plan",
                "sides": [],
                "missions": [],
                "aircraft": [],
                "ships": [],
                "facilities": [],
                "airbases": [],
            }
        },
    )

    compare_session = await svc.fork_compare_session(
        db_session,
        user,
        source.id,
        payload=ScenarioCompareForkCreate(branch_count=3),
    )

    assert compare_session.source_scenario_id == source.id
    assert compare_session.baseline_scenario_id == source.id
    assert len(compare_session.scenario_ids) == 4
    assert compare_session.scenario_ids[0] == source.id

    branches = [
        await svc.get_scenario(db_session, user, scenario_id)
        for scenario_id in compare_session.scenario_ids[1:]
    ]
    assert [branch.branch_meta["branch_label"] for branch in branches] == [
        "方案 1",
        "方案 2",
        "方案 3",
    ]
    assert all(branch.branch_meta["parent_scenario_id"] == source.id for branch in branches)


async def test_create_plan_set_compare_session_persists_plan_summaries(
    db_session,
    user,
):
    source = await svc.create_scenario(
        db_session,
        user,
        name="Operational Base",
        data={
            "currentSideId": "BLUE",
            "currentScenario": {
                "id": "runtime-plan-base",
                "name": "Operational Base",
                "currentTime": 1000,
                "startTime": 1000,
                "duration": 3600,
                "currentSideId": "BLUE",
                "sides": [{"id": "BLUE", "name": "Blue"}],
                "missions": [],
                "aircraft": [],
                "ships": [],
                "facilities": [],
                "airbases": [],
                "obstacles": [],
            }
        },
    )

    plan_set = await svc.create_plan_set_compare_session(
        db_session,
        user,
        source.id,
        payload=ScenarioPlanSetCreate(
            title="Blue COAs",
            plans=[
                ScenarioPlanOption(
                    title="Stand-off strike",
                    concept="Use long-range assets first.",
                    key_actions=["EW opening", "long-range strike"],
                ),
                ScenarioPlanOption(
                    title="Escort penetration",
                    concept="Escort the strike package through contested airspace.",
                    key_actions=["fighter sweep", "escort strike"],
                ),
                ScenarioPlanOption(
                    title="Decoy and flank",
                    concept="Use a decoy axis and attack from a second bearing.",
                    key_actions=["decoy package", "flanking attack"],
                ),
            ],
        ),
    )

    assert plan_set.branch_count == 3
    assert plan_set.compare_session.source_scenario_id == source.id
    assert len(plan_set.compare_session.scenario_ids) == 4
    branch_ids = plan_set.compare_session.scenario_ids[1:]
    assert set(branch_ids) == set(plan_set.compare_session.state.plan_summaries)
    first_summary = plan_set.compare_session.state.plan_summaries[branch_ids[0]]
    assert first_summary["title"] == "Stand-off strike"


async def test_simulate_compare_session_batch_creates_score_records(
    db_session,
    user,
):
    source_data = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "client"
            / "src"
            / "scenarios"
            / "SCS.json"
        ).read_text(encoding="utf-8")
    )
    source_data["currentScenario"]["id"] = "runtime-batch-base"
    source_data["currentScenario"]["name"] = "Batch Base"
    source = await svc.create_scenario(
        db_session,
        user,
        name="Batch Base",
        data=source_data,
    )
    plan_set = await svc.create_plan_set_compare_session(
        db_session,
        user,
        source.id,
        payload=ScenarioPlanSetCreate(
            plans=[
                ScenarioPlanOption(title="COA-1", concept="First option"),
                ScenarioPlanOption(title="COA-2", concept="Second option"),
            ],
        ),
    )

    bridges: dict[str, TianShuOpenClawBridge] = {}

    def bridge_provider(owner, scenario_id):
        assert owner == user
        key = str(scenario_id or "")
        if key not in bridges:
            bridges[key] = TianShuOpenClawBridge()
        return bridges[key]

    result = await svc.simulate_compare_session_batch(
        db_session,
        user,
        plan_set.compare_session.id,
        payload=ScenarioBatchSimulationRequest(steps=5, include_baseline=False),
        bridge_provider=bridge_provider,
    )

    assert result.steps == 5
    assert result.include_baseline is False
    assert len(result.results) == 2
    assert all(item.training_score_record_id for item in result.results)

    updated = await svc.get_compare_session(db_session, user, plan_set.compare_session.id)
    state = ScenarioCompareSessionState.model_validate(updated.state)
    for item in result.results:
        assert state.selected_sources[item.scenario_id] == item.training_score_record_id
