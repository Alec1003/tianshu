"""Deterministic training scoring for replay/AAR data."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from app.aicc_runtime.models import RuntimeEvent
from app.aicc_runtime.timeline import runtime_scenario_id
from app.scenarios.models import AarRecord, Scenario
from app.scenarios.schemas import TrainingScoreDimension, TrainingScoreResponse


DIMENSION_WEIGHTS: dict[str, float] = {
    "task_effectiveness": 0.30,
    "force_preservation": 0.20,
    "resource_efficiency": 0.15,
    "command_efficiency": 0.15,
    "tempo_control": 0.10,
    "rule_compliance": 0.10,
}

DIMENSION_LABELS: dict[str, str] = {
    "task_effectiveness": "任务达成",
    "force_preservation": "兵力保持",
    "resource_efficiency": "资源效率",
    "command_efficiency": "指挥效率",
    "tempo_control": "节奏控制",
    "rule_compliance": "规则合规",
}

NON_LOSS_UNIT_TYPES = {"weapon", "reference_point"}


def build_training_score(
    scenario: Scenario,
    events: Sequence[RuntimeEvent],
    aar_records: Sequence[AarRecord],
) -> TrainingScoreResponse:
    """Build an explainable 0-100 training score.

    The score is intentionally rule-based. AI can later turn this response into
    prose, but the numeric result should stay reproducible and auditable.
    """

    ordered_events = sorted(events, key=lambda event: (event.created_at, event.id))
    latest_aar = _latest_aar(aar_records)
    scenario_data = scenario.data if isinstance(scenario.data, dict) else {}
    metrics = _collect_metrics(scenario_data, ordered_events, latest_aar)

    dimensions = [
        _task_effectiveness(metrics),
        _force_preservation(metrics),
        _resource_efficiency(metrics),
        _command_efficiency(metrics),
        _tempo_control(metrics),
        _rule_compliance(metrics),
    ]
    overall = _weighted_score(dimensions)

    return TrainingScoreResponse(
        scenario_id=scenario.id,
        runtime_scenario_id=runtime_scenario_id(scenario_data),
        generated_at=datetime.now(tz=timezone.utc),
        overall_score=overall,
        grade=_grade(overall),
        confidence=_confidence(metrics),
        dimensions=dimensions,
        metrics=metrics,
        strengths=_strengths(dimensions),
        improvements=_improvements(dimensions, metrics),
    )


def _current_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    inner = scenario.get("currentScenario")
    return inner if isinstance(inner, dict) else scenario


def _latest_aar(aar_records: Sequence[AarRecord]) -> AarRecord | None:
    if not aar_records:
        return None
    return max(aar_records, key=lambda record: record.created_at)


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _side_matches(side_id: Any, trainee_side_id: str) -> bool:
    if not trainee_side_id:
        return True
    return str(side_id or "").casefold() == trainee_side_id.casefold()


def _positive_drop(diff: dict[str, Any]) -> tuple[float, float] | None:
    before = _num(diff.get("before"))
    after = _num(diff.get("after"))
    if before is None or after is None or before <= 0 or after >= before:
        return None
    return before - after, before


def _iter_unit_changes(events: Sequence[RuntimeEvent]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for event in events:
        if isinstance(event.unit_changes, list):
            changes.extend(
                change for change in event.unit_changes if isinstance(change, dict)
            )
    return changes


def _iter_initial_units(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    inner = _current_scenario(scenario)
    units: list[dict[str, Any]] = []
    for collection in ("aircraft", "ships", "facilities", "airbases"):
        rows = inner.get(collection)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            units.append(row)
            nested_rows = row.get("aircraft")
            if isinstance(nested_rows, list):
                units.extend(nested for nested in nested_rows if isinstance(nested, dict))
    return units


def _trainee_side_id(scenario: dict[str, Any]) -> str:
    inner = _current_scenario(scenario)
    value = scenario.get("currentSideId") or inner.get("currentSideId")
    if value:
        return str(value)
    sides = inner.get("sides")
    if isinstance(sides, list) and sides and isinstance(sides[0], dict):
        return str(sides[0].get("id") or "")
    return ""


def _adjudication_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    direct = payload.get("adjudication")
    if isinstance(direct, dict):
        return direct
    proposal = payload.get("proposal")
    if isinstance(proposal, dict) and isinstance(proposal.get("adjudication"), dict):
        return proposal["adjudication"]
    return None


def _collect_adjudication_counts(events: Sequence[RuntimeEvent]) -> tuple[int, int]:
    warnings = 0
    blockers = 0
    for event in events:
        payload = event.payload if isinstance(event.payload, dict) else {}
        adjudication = _adjudication_from_payload(payload)
        if not adjudication:
            continue
        issues = adjudication.get("issues")
        if not isinstance(issues, list):
            continue
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            severity = issue.get("severity")
            if severity == "blocking":
                blockers += 1
            elif severity == "warning":
                warnings += 1
    return warnings, blockers


def _collect_metrics(
    scenario: dict[str, Any],
    events: Sequence[RuntimeEvent],
    latest_aar: AarRecord | None,
) -> dict[str, Any]:
    inner = _current_scenario(scenario)
    trainee_side_id = _trainee_side_id(scenario)
    event_types = Counter(event.event_type for event in events)
    categories = Counter(event.category for event in events)
    actions = Counter(event.action for event in events)
    changes = _iter_unit_changes(events)

    initial_units = _iter_initial_units(scenario)
    trainee_initial_units = [
        unit for unit in initial_units if _side_matches(unit.get("sideId"), trainee_side_id)
    ]
    initial_unit_count = len(trainee_initial_units) or len(initial_units)

    removed_units = [
        change
        for change in changes
        if change.get("change_type") == "removed"
        and str(change.get("unit_type") or "") not in NON_LOSS_UNIT_TYPES
    ]
    trainee_losses = [
        change
        for change in removed_units
        if _side_matches(change.get("side_id"), trainee_side_id)
    ]
    enemy_losses = [
        change
        for change in removed_units
        if trainee_side_id and not _side_matches(change.get("side_id"), trainee_side_id)
    ]
    effective_losses = trainee_losses if trainee_side_id else removed_units

    fuel_drop = 0.0
    fuel_before = 0.0
    ammo_drop = 0.0
    ammo_before = 0.0
    refueling_event_count = 0
    refueled_amount = 0.0
    for change in changes:
        if not _side_matches(change.get("side_id"), trainee_side_id):
            continue
        fields = change.get("fields")
        if not isinstance(fields, dict):
            continue
        fuel = fields.get("currentFuel")
        if isinstance(fuel, dict) and (drop := _positive_drop(fuel)):
            fuel_drop += drop[0]
            fuel_before += drop[1]
        ammo = fields.get("currentQuantity")
        if isinstance(ammo, dict) and (drop := _positive_drop(ammo)):
            ammo_drop += drop[0]
            ammo_before += drop[1]
    for event in events:
        payload = event.payload if isinstance(event.payload, dict) else {}
        state = payload.get("state") if isinstance(payload, dict) else {}
        refueling_events = (
            state.get("refuelingEvents") if isinstance(state, dict) else None
        )
        if not isinstance(refueling_events, list):
            continue
        for refueling_event in refueling_events:
            if not isinstance(refueling_event, dict):
                continue
            refueling_event_count += 1
            refueled_amount += float(refueling_event.get("fuelTransferred") or 0)

    warnings, blockers = _collect_adjudication_counts(events)
    elapsed_seconds = _aar_elapsed(latest_aar)
    duration = _num(inner.get("duration"))
    current_times = [
        event.current_time for event in events if isinstance(event.current_time, int)
    ]
    replay_span = max(current_times) - min(current_times) if len(current_times) >= 2 else 0

    return {
        "event_count": len(events),
        "aar_count": 1 if latest_aar else 0,
        "runtime_event_count": categories.get("runtime", 0),
        "command_event_count": categories.get("command", 0),
        "unit_change_count": len(changes),
        "loss_count": len(effective_losses),
        "enemy_loss_count": len(enemy_losses),
        "initial_unit_count": initial_unit_count,
        "fuel_drop": round(fuel_drop, 3),
        "fuel_before": round(fuel_before, 3),
        "ammo_drop": round(ammo_drop, 3),
        "ammo_before": round(ammo_before, 3),
        "refueling_event_count": refueling_event_count,
        "refueled_amount": round(refueled_amount, 3),
        "tanker_count": sum(1 for unit in initial_units if unit.get("isTanker")),
        "obstacle_count": len(inner.get("obstacles") or []),
        "warning_count": warnings,
        "blocking_count": blockers,
        "proposal_count": event_types.get("command.proposed", 0),
        "approved_count": event_types.get("command.approved", 0),
        "rejected_count": event_types.get("command.rejected", 0),
        "executed_count": event_types.get("command.executed", 0)
        + actions.get("approved_execution", 0),
        "runtime_step_count": event_types.get("runtime.step", 0),
        "runtime_reset_count": event_types.get("runtime.reset", 0),
        "outcome_reason": latest_aar.outcome_reason if latest_aar else "",
        "winner_side_id": latest_aar.winner_side_id if latest_aar else "",
        "trainee_side_id": trainee_side_id,
        "elapsed_seconds": elapsed_seconds,
        "scenario_duration": int(duration) if duration else 0,
        "replay_span_seconds": replay_span,
    }


def _aar_elapsed(latest_aar: AarRecord | None) -> int:
    if latest_aar is None or not isinstance(latest_aar.summary, dict):
        return 0
    value = latest_aar.summary.get("elapsedSeconds")
    parsed = _num(value)
    return max(0, int(parsed)) if parsed is not None else 0


def _dimension(
    key: str,
    score: float,
    summary: str,
    evidence: list[str],
) -> TrainingScoreDimension:
    return TrainingScoreDimension(
        key=key,
        label=DIMENSION_LABELS[key],
        score=_clamp_score(score),
        weight=DIMENSION_WEIGHTS[key],
        summary=summary,
        evidence=evidence[:4],
    )


def _task_effectiveness(metrics: dict[str, Any]) -> TrainingScoreDimension:
    winner = str(metrics["winner_side_id"] or "")
    trainee = str(metrics["trainee_side_id"] or "")
    outcome = str(metrics["outcome_reason"] or "")

    if metrics["aar_count"]:
        if winner and trainee and winner.casefold() == trainee.casefold():
            score = 96
            summary = "AAR 显示训练方达成主要目标。"
        elif winner:
            score = 45
            summary = "AAR 显示训练方未取得最终优势。"
        elif outcome:
            score = 68
            summary = "AAR 已归档，但未形成明确胜负优势。"
        else:
            score = 60
            summary = "AAR 信息不足，按部分达成处理。"
    elif metrics["runtime_event_count"]:
        score = 55
        summary = "已有推演过程，但尚未归档 AAR。"
    else:
        score = 40
        summary = "缺少推演结果和 AAR，无法证明任务达成。"

    return _dimension(
        "task_effectiveness",
        score,
        summary,
        [
            f"训练方={trainee or '未标注'}",
            f"胜方={winner or '未记录'}",
            f"结果={outcome or '未记录'}",
        ],
    )


def _force_preservation(metrics: dict[str, Any]) -> TrainingScoreDimension:
    losses = int(metrics["loss_count"])
    initial_units = max(1, int(metrics["initial_unit_count"] or 0))
    loss_ratio = losses / initial_units
    score = 100 - loss_ratio * 90
    if losses == 0:
        summary = "未记录训练方单位损失，兵力保持良好。"
    else:
        summary = f"记录 {losses} 个训练方单位损失，需要复盘暴露与撤收时机。"
    return _dimension(
        "force_preservation",
        score,
        summary,
        [
            f"初始训练方单位={initial_units}",
            f"训练方损失={losses}",
            f"对方损失={metrics['enemy_loss_count']}",
        ],
    )


def _resource_efficiency(metrics: dict[str, Any]) -> TrainingScoreDimension:
    fuel_before = float(metrics["fuel_before"] or 0)
    ammo_before = float(metrics["ammo_before"] or 0)
    fuel_ratio = float(metrics["fuel_drop"] or 0) / fuel_before if fuel_before else 0
    ammo_ratio = float(metrics["ammo_drop"] or 0) / ammo_before if ammo_before else 0
    refueling_events = int(metrics["refueling_event_count"] or 0)
    obstacle_count = int(metrics["obstacle_count"] or 0)

    if fuel_before == 0 and ammo_before == 0:
        score = 70 if metrics["event_count"] else 55
        summary = "暂无可量化油弹消耗，按中性区间评分。"
    else:
        score = 100 - fuel_ratio * 35 - ammo_ratio * 45
        summary = "油弹消耗处于可解释区间。"
        if fuel_ratio > 0.45 or ammo_ratio > 0.45:
            summary = "资源消耗偏高，需要优化任务路径和火力分配。"
    if refueling_events:
        score += min(6, refueling_events * 2)
        summary = "已记录空中加油补给，资源调度具备可追踪证据。"
    if obstacle_count and not refueling_events and fuel_ratio > 0.35:
        summary = "存在障碍/约束区且油料消耗偏高，需要复盘航路与补给计划。"

    return _dimension(
        "resource_efficiency",
        score,
        summary,
        [
            f"油料消耗={metrics['fuel_drop']}",
            f"弹药消耗={metrics['ammo_drop']}",
            f"空中加油事件={refueling_events}",
            f"障碍/约束区={obstacle_count}",
        ],
    )


def _command_efficiency(metrics: dict[str, Any]) -> TrainingScoreDimension:
    command_events = int(metrics["command_event_count"])
    approved = int(metrics["approved_count"])
    executed = int(metrics["executed_count"])
    rejected = int(metrics["rejected_count"])
    proposals = int(metrics["proposal_count"])

    if command_events == 0:
        score = 55 if metrics["runtime_event_count"] else 40
        summary = "缺少结构化命令事件，指挥效率证据不足。"
    else:
        useful = approved + executed
        score = 65 + min(25, useful * 8) - rejected * 18
        if proposals and useful == 0:
            score -= 8
        summary = "命令链路具备可追踪记录。"
        if rejected:
            summary = "存在被驳回命令，需要复盘意图表达和约束检查。"

    return _dimension(
        "command_efficiency",
        score,
        summary,
        [
            f"提案={proposals}",
            f"审批={approved}",
            f"执行={executed}",
            f"驳回={rejected}",
        ],
    )


def _tempo_control(metrics: dict[str, Any]) -> TrainingScoreDimension:
    elapsed = int(metrics["elapsed_seconds"] or metrics["replay_span_seconds"] or 0)
    duration = int(metrics["scenario_duration"] or 0)
    steps = int(metrics["runtime_step_count"])
    resets = int(metrics["runtime_reset_count"])

    if not elapsed or not duration:
        score = 62 + min(12, steps * 2) - resets * 6
        summary = "缺少完整时长基线，按过程推进节奏评分。"
    else:
        ratio = elapsed / max(1, duration)
        score = 96 - min(45, ratio * 35) - resets * 6
        summary = "推演节奏处于计划时间内。"
        if ratio > 1:
            summary = "推演超过计划时长，需要压缩决策循环。"

    return _dimension(
        "tempo_control",
        score,
        summary,
        [
            f"用时={elapsed}s",
            f"计划={duration}s",
            f"推进={steps}",
            f"重置={resets}",
        ],
    )


def _rule_compliance(metrics: dict[str, Any]) -> TrainingScoreDimension:
    warnings = int(metrics["warning_count"])
    blockers = int(metrics["blocking_count"])
    rejected = int(metrics["rejected_count"])
    score = 100 - blockers * 25 - warnings * 8 - rejected * 10
    if blockers or warnings or rejected:
        summary = "存在规则或审批风险，需要复核命令合法性。"
    elif metrics["command_event_count"]:
        summary = "未发现阻断级规则冲突。"
    else:
        summary = "暂无命令裁决样本，合规评分证据有限。"
        score = min(score, 72)

    return _dimension(
        "rule_compliance",
        score,
        summary,
        [f"阻断={blockers}", f"警告={warnings}", f"驳回={rejected}"],
    )


def _weighted_score(dimensions: Sequence[TrainingScoreDimension]) -> int:
    total_weight = sum(d.weight for d in dimensions) or 1
    return _clamp_score(sum(d.score * d.weight for d in dimensions) / total_weight)


def _clamp_score(value: float) -> int:
    return int(round(max(0, min(100, value))))


def _grade(score: int) -> str:
    if score >= 90:
        return "优秀"
    if score >= 80:
        return "良好"
    if score >= 70:
        return "合格"
    if score >= 60:
        return "待改进"
    return "不合格"


def _confidence(metrics: dict[str, Any]) -> str:
    if metrics["aar_count"] and metrics["event_count"] >= 5:
        return "high"
    if metrics["aar_count"] or metrics["event_count"] >= 3:
        return "medium"
    return "low"


def _strengths(dimensions: Sequence[TrainingScoreDimension]) -> list[str]:
    items = [
        f"{dimension.label}表现稳定：{dimension.summary}"
        for dimension in dimensions
        if dimension.score >= 85
    ]
    return items[:3] or ["已建立可回放评分基线，可继续沉淀更多事件样本。"]


def _improvements(
    dimensions: Sequence[TrainingScoreDimension],
    metrics: dict[str, Any],
) -> list[str]:
    items = [
        f"提升{dimension.label}：{dimension.summary}"
        for dimension in dimensions
        if dimension.score < 70
    ]
    if metrics["event_count"] < 3:
        items.insert(0, "增加命令、审批、单步推演和 AAR 样本后，评分会更稳定。")
    return items[:4] or ["继续保持当前流程，并在 AAR 中补充人工点评。"]
