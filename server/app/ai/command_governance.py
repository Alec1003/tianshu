from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from threading import RLock
from typing import Any
from uuid import uuid4

from app.ai.models import (
    CommandAdjudicationIssue,
    CommandAdjudicationResult,
    CommandProposal,
    SkillExecutionResult,
    StructuredCommandStep,
)
from app.ai.skill_registry import TianShuSkillRegistry
from app.tianshu_runtime.matching import resolve_side_id as resolve_side_reference_id
from app.tianshu_runtime.runtime import TianShuRuntime

ALLOWED_SKILLS = {
    "simulation_start",
    "simulation_pause",
    "simulation_stop",
    "simulation_reset",
    "simulation_step",
    "deploy_aircraft",
    "deploy_ship",
    "deploy_facility",
    "deploy_airbase",
    "deploy_obstacle",
    "deploy_reference_point",
    "delete_unit",
    "move_unit",
    "update_unit_state",
    "attack_unit",
    "update_weapon_quantity",
    "create_patrol_mission",
    "create_strike_mission",
    "trigger_tactical_event",
    "update_situation_layer",
    "load_script",
    "execute_script_step",
    "control_script_flow",
    "load_scenario_snapshot",
}

BLOCKED_SKILLS = {
    "load_scenario_file",
    "load_scenario_json",
}

HIGH_RISK_SKILLS = {
    "simulation_stop",
    "simulation_reset",
    "delete_unit",
    "update_unit_state",
    "attack_unit",
    "load_script",
    "control_script_flow",
    "load_scenario_snapshot",
}

LOW_RISK_SKILLS = {
    "simulation_pause",
    "simulation_step",
    "deploy_reference_point",
    "update_situation_layer",
}

UNIT_LOOKUP = {
    "aircraft": "get_aircraft",
    "ship": "get_ship",
    "facility": "get_facility",
    "airbase": "get_airbase",
    "reference_point": "get_reference_point",
    "obstacle": "get_obstacle",
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _haversine_nm(
    start_latitude: float,
    start_longitude: float,
    destination_latitude: float,
    destination_longitude: float,
) -> float:
    earth_radius_km = 6371.0088
    lat1 = math.radians(start_latitude)
    lat2 = math.radians(destination_latitude)
    dlat = math.radians(destination_latitude - start_latitude)
    dlon = math.radians(destination_longitude - start_longitude)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    distance_km = earth_radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return distance_km * 0.539956803


class CommandRuleEngine:
    """Deterministic guardrails for AI-generated runtime mutations.

    The LLM can propose actions, but this rule engine decides whether the
    proposal can enter the human approval queue. It never mutates runtime state.
    """

    def __init__(self, runtime: TianShuRuntime, registry: TianShuSkillRegistry) -> None:
        self.runtime = runtime
        self.registry = registry

    def adjudicate(self, steps: list[StructuredCommandStep]) -> CommandAdjudicationResult:
        issues: list[CommandAdjudicationIssue] = []
        if not steps:
            issues.append(
                self._issue(
                    "blocking",
                    "empty_proposal",
                    "未识别到可执行的结构化命令。",
                )
            )

        for step in steps:
            issues.extend(self._adjudicate_step(step))

        has_blocking = any(issue.severity == "blocking" for issue in issues)
        return CommandAdjudicationResult(
            status="blocked" if has_blocking else "needs_review",
            requires_human_approval=True,
            summary=(
                "规则裁决未通过，禁止进入执行审批。"
                if has_blocking
                else "规则裁决通过，等待人工审批后执行。"
            ),
            issues=issues,
        )

    def _adjudicate_step(
        self, step: StructuredCommandStep
    ) -> list[CommandAdjudicationIssue]:
        issues: list[CommandAdjudicationIssue] = []
        skill = step.skill
        params = step.parameters

        if skill in BLOCKED_SKILLS:
            return [
                self._issue(
                    "blocking",
                    "blocked_skill",
                    "AI 不允许通过审批队列加载服务端文件或整包想定；请使用人工导入入口。",
                    step.id,
                    "skill",
                )
            ]
        if skill not in ALLOWED_SKILLS or not self.registry.has_skill(skill):
            return [
                self._issue(
                    "blocking",
                    "unknown_skill",
                    f"未注册或不允许的仿真动作：{skill}",
                    step.id,
                    "skill",
                )
            ]

        if skill == "simulation_step":
            steps = int(params.get("steps") or 1)
            if steps < 1 or steps > 7200:
                issues.append(
                    self._issue(
                        "blocking",
                        "steps_out_of_range",
                        "单次仿真推进必须在 1 到 7200 秒之间。",
                        step.id,
                        "steps",
                    )
                )

        if skill.startswith("deploy_"):
            issues.extend(self._validate_deploy(step))

        if skill in {"delete_unit", "move_unit", "update_unit_state"}:
            issues.extend(self._validate_unit_target(step))

        if skill == "attack_unit":
            issues.extend(self._validate_attack(step))

        if skill == "update_weapon_quantity":
            issues.extend(self._validate_weapon_quantity(step))

        if skill in {"create_patrol_mission", "create_strike_mission"}:
            issues.extend(self._validate_mission(step))

        if skill == "move_unit":
            issues.extend(self._validate_route(step))

        if skill == "update_unit_state":
            patch = params.get("patch")
            if not isinstance(patch, dict) or not patch:
                issues.append(
                    self._issue(
                        "blocking",
                        "empty_patch",
                        "状态更新命令必须包含非空 patch。",
                        step.id,
                        "patch",
                    )
                )

        if skill == "load_scenario_snapshot":
            issues.extend(self._validate_scenario_snapshot(step))

        if skill in HIGH_RISK_SKILLS:
            issues.append(
                self._issue(
                    "warning",
                    "high_risk_action",
                    "该动作会显著改变仿真状态，审批前请复核意图与影响范围。",
                    step.id,
                    "skill",
                )
            )

        return issues

    def _validate_scenario_snapshot(
        self, step: StructuredCommandStep
    ) -> list[CommandAdjudicationIssue]:
        scenario_json = step.parameters.get("scenario_json")
        if not isinstance(scenario_json, str) or not scenario_json.strip():
            return [
                self._issue(
                    "blocking",
                    "missing_scenario_json",
                    "想定加载提案必须包含已授权的 scenario_json 快照。",
                    step.id,
                    "scenario_json",
                )
            ]
        try:
            parsed = json.loads(scenario_json)
        except json.JSONDecodeError:
            return [
                self._issue(
                    "blocking",
                    "invalid_scenario_json",
                    "scenario_json 必须是合法 JSON。",
                    step.id,
                    "scenario_json",
                )
            ]
        if not isinstance(parsed, dict):
            return [
                self._issue(
                    "blocking",
                    "invalid_scenario_shape",
                    "scenario_json 必须表示一个想定 JSON 对象。",
                    step.id,
                    "scenario_json",
                )
            ]
        return []

    def _validate_deploy(
        self, step: StructuredCommandStep
    ) -> list[CommandAdjudicationIssue]:
        issues: list[CommandAdjudicationIssue] = []
        params = step.parameters
        latitude = _to_float(params.get("latitude"))
        longitude = _to_float(params.get("longitude"))
        class_name = str(params.get("class_name") or params.get("name") or "").strip()
        if not class_name:
            issues.append(
                self._issue(
                    "blocking",
                    "missing_class_name",
                    "部署命令必须包含单位型号或名称。",
                    step.id,
                    "class_name",
                )
            )
        else:
            known_check_names = {
                "deploy_aircraft": ("aircraft", "is_known_aircraft_class"),
                "deploy_ship": ("ship", "is_known_ship_class"),
                "deploy_facility": ("facility", "is_known_facility_class"),
                "deploy_airbase": ("airbase", "is_known_airbase_class"),
            }
            check = known_check_names.get(step.skill)
            check_fn = getattr(self.runtime, check[1], None) if check else None
            if (
                check is not None
                and check_fn is not None
                and not isinstance(params.get("template"), dict)
                and not check_fn(class_name)
            ):
                unit_type = check[0]
                issues.append(
                    self._issue(
                        "blocking",
                        f"unknown_{unit_type}_class",
                        "Unit type is not present in the asset database; placeholder deployment is forbidden.",
                        step.id,
                        "class_name",
                    )
                )
        issues.extend(self._validate_coordinates(step.id, latitude, longitude))
        side = params.get("side")
        if side:
            issues.extend(self._validate_side(step.id, str(side)))
        else:
            message = (
                "未指定阵营，将创建中立环境约束区。"
                if step.skill == "deploy_obstacle"
                else "未指定阵营，将使用当前后端 runtime 激活阵营。"
            )
            issues.append(
                self._issue(
                    "info",
                    "default_side",
                    message,
                    step.id,
                    "side",
                )
            )
        return issues

    def _validate_unit_target(
        self, step: StructuredCommandStep
    ) -> list[CommandAdjudicationIssue]:
        params = step.parameters
        unit_type = str(params.get("unit_type") or "").strip()
        unit_id = str(params.get("unit_id") or "").strip()
        if unit_type not in UNIT_LOOKUP:
            return [
                self._issue(
                    "blocking",
                    "invalid_unit_type",
                    "单位类型必须是 aircraft、ship、facility、airbase、reference_point 或 obstacle。",
                    step.id,
                    "unit_type",
                )
            ]
        if not unit_id:
            return [
                self._issue(
                    "blocking",
                    "missing_unit_id",
                    "命令必须包含目标单位 ID。",
                    step.id,
                    "unit_id",
                )
            ]
        scenario = self.runtime.game.current_scenario
        getter = getattr(scenario, UNIT_LOOKUP[unit_type], None)
        unit = getter(unit_id) if callable(getter) else None
        if unit is None:
            return [
                self._issue(
                    "blocking",
                    "unit_not_found",
                    f"当前 runtime 中找不到 {unit_type} 单位：{unit_id}",
                    step.id,
                    "unit_id",
                )
            ]
        return []

    def _validate_route(
        self, step: StructuredCommandStep
    ) -> list[CommandAdjudicationIssue]:
        issues: list[CommandAdjudicationIssue] = []
        params = step.parameters
        route = params.get("route")
        if not isinstance(route, list) or not route:
            return [
                self._issue(
                    "blocking",
                    "empty_route",
                    "机动命令必须包含至少一个航点。",
                    step.id,
                    "route",
                )
            ]
        if len(route) > 32:
            issues.append(
                self._issue(
                    "blocking",
                    "route_too_long",
                    "单条 AI 机动命令最多支持 32 个航点。",
                    step.id,
                    "route",
                )
            )
        normalized: list[tuple[float, float]] = []
        for index, point in enumerate(route):
            if not isinstance(point, list | tuple) or len(point) != 2:
                issues.append(
                    self._issue(
                        "blocking",
                        "invalid_route_point",
                        "航点必须是 [latitude, longitude]。",
                        step.id,
                        f"route[{index}]",
                    )
                )
                continue
            latitude = _to_float(point[0])
            longitude = _to_float(point[1])
            issues.extend(
                self._validate_coordinates(
                    step.id, latitude, longitude, field=f"route[{index}]"
                )
            )
            if latitude is not None and longitude is not None:
                normalized.append((latitude, longitude))

        if issues:
            return issues

        unit_type = str(params.get("unit_type") or "")
        unit_id = str(params.get("unit_id") or "")
        scenario = self.runtime.game.current_scenario
        unit = None
        if unit_type == "aircraft":
            unit = scenario.get_aircraft(unit_id)
        elif unit_type == "ship":
            unit = scenario.get_ship(unit_id)
        if unit is not None:
            points = [(float(unit.latitude), float(unit.longitude)), *normalized]
            distance_nm = sum(
                _haversine_nm(a[0], a[1], b[0], b[1])
                for a, b in zip(points, points[1:], strict=False)
            )
            unit_range = _to_float(getattr(unit, "range", None)) or 0.0
            if unit_range > 0 and distance_nm > unit_range:
                issues.append(
                    self._issue(
                        "warning",
                        "route_exceeds_nominal_range",
                        (
                            f"规划航程约 {distance_nm:.0f} NM，超过该单位标称航程 "
                            f"{unit_range:.0f} NM。"
                        ),
                        step.id,
                        "route",
                    )
                )
        return issues

    def _validate_mission(
        self, step: StructuredCommandStep
    ) -> list[CommandAdjudicationIssue]:
        issues: list[CommandAdjudicationIssue] = []
        params = step.parameters
        name = str(params.get("name") or "").strip()
        assigned_unit_ids = params.get("assigned_unit_ids")
        if not name:
            issues.append(
                self._issue(
                    "blocking",
                    "missing_mission_name",
                    "Mission proposal must include a mission name.",
                    step.id,
                    "name",
                )
            )
        if not isinstance(assigned_unit_ids, list) or not assigned_unit_ids:
            issues.append(
                self._issue(
                    "blocking",
                    "missing_assigned_units",
                    "Mission proposal must assign at least one unit.",
                    step.id,
                    "assigned_unit_ids",
                )
            )
        else:
            for index, unit_id in enumerate(assigned_unit_ids):
                if self._find_any_unit(str(unit_id)) is None:
                    issues.append(
                        self._issue(
                            "blocking",
                            "assigned_unit_not_found",
                            f"Assigned unit not found: {unit_id}",
                            step.id,
                            f"assigned_unit_ids[{index}]",
                        )
                    )

        if step.skill == "create_patrol_mission":
            reference_point_ids = params.get("reference_point_ids")
            if not isinstance(reference_point_ids, list) or len(reference_point_ids) < 3:
                issues.append(
                    self._issue(
                        "blocking",
                        "missing_patrol_area",
                        "Patrol mission requires at least three reference points.",
                        step.id,
                        "reference_point_ids",
                    )
                )
            else:
                scenario = self.runtime.game.current_scenario
                for index, point_id in enumerate(reference_point_ids):
                    if scenario.get_reference_point(str(point_id)) is None:
                        issues.append(
                            self._issue(
                                "blocking",
                                "reference_point_not_found",
                                f"Reference point not found: {point_id}",
                                step.id,
                                f"reference_point_ids[{index}]",
                            )
                        )

        if step.skill == "create_strike_mission":
            target_ids = params.get("assigned_target_ids")
            if not isinstance(target_ids, list) or not target_ids:
                issues.append(
                    self._issue(
                        "blocking",
                        "missing_strike_targets",
                        "Strike mission requires at least one target.",
                        step.id,
                        "assigned_target_ids",
                    )
                )
            else:
                for index, target_id in enumerate(target_ids):
                    if self._find_any_unit(str(target_id)) is None:
                        issues.append(
                            self._issue(
                                "blocking",
                                "strike_target_not_found",
                                f"Strike target not found: {target_id}",
                                step.id,
                                f"assigned_target_ids[{index}]",
                            )
                        )
        return issues

    def _validate_attack(
        self, step: StructuredCommandStep
    ) -> list[CommandAdjudicationIssue]:
        issues: list[CommandAdjudicationIssue] = []
        params = step.parameters
        attacker_type = str(params.get("attacker_type") or "").strip()
        attacker_id = str(params.get("attacker_id") or "").strip()
        target_id = str(params.get("target_id") or "").strip()
        if attacker_type not in {"aircraft", "ship"}:
            issues.append(
                self._issue(
                    "blocking",
                    "invalid_attacker_type",
                    "打击命令的 attacker_type 必须是 aircraft 或 ship。",
                    step.id,
                    "attacker_type",
                )
            )
        if attacker_type and attacker_id:
            issues.extend(
                self._validate_unit_target(
                    step.model_copy(
                        update={
                            "parameters": {
                                "unit_type": attacker_type,
                                "unit_id": attacker_id,
                            }
                        }
                    )
                )
            )
        else:
            issues.append(
                self._issue(
                    "blocking",
                    "missing_attacker",
                    "打击命令必须包含 attacker_type 和 attacker_id。",
                    step.id,
                    "attacker_id",
                )
            )
        scenario = self.runtime.game.current_scenario
        target_getter = getattr(scenario, "get_target", None)
        target = target_getter(target_id) if callable(target_getter) else self._find_any_unit(target_id)
        if not target_id or target is None:
            issues.append(
                self._issue(
                    "blocking",
                    "target_not_found",
                    f"当前 runtime 中找不到打击目标：{target_id}",
                    step.id,
                    "target_id",
                )
            )
        if not bool(params.get("auto")) and not str(params.get("weapon_id") or "").strip():
            issues.append(
                self._issue(
                    "warning",
                    "manual_attack_without_weapon",
                    "未指定 weapon_id 时建议将 auto 设为 true，由后端选择可发射武器。",
                    step.id,
                    "weapon_id",
                )
            )
        return issues

    def _validate_weapon_quantity(
        self, step: StructuredCommandStep
    ) -> list[CommandAdjudicationIssue]:
        issues = self._validate_unit_target(step)
        params = step.parameters
        weapon_id = str(params.get("weapon_id") or "").strip()
        if not weapon_id:
            issues.append(
                self._issue(
                    "blocking",
                    "missing_weapon_id",
                    "武器数量调整必须包含 weapon_id。",
                    step.id,
                    "weapon_id",
                )
            )
        increment = _to_float(params.get("increment"))
        if increment is None:
            issues.append(
                self._issue(
                    "blocking",
                    "invalid_weapon_increment",
                    "武器数量调整必须包含数字 increment。",
                    step.id,
                    "increment",
                )
            )
        return issues

    def _find_any_unit(self, unit_id: str) -> Any | None:
        scenario = self.runtime.game.current_scenario
        for getter_name in (
            "get_aircraft",
            "get_ship",
            "get_facility",
            "get_airbase",
        ):
            getter = getattr(scenario, getter_name, None)
            unit = getter(unit_id) if callable(getter) else None
            if unit is not None:
                return unit
        return None

    def _validate_coordinates(
        self,
        step_id: str,
        latitude: float | None,
        longitude: float | None,
        *,
        field: str = "coordinates",
    ) -> list[CommandAdjudicationIssue]:
        issues: list[CommandAdjudicationIssue] = []
        if latitude is None or latitude < -90 or latitude > 90:
            issues.append(
                self._issue(
                    "blocking",
                    "latitude_out_of_range",
                    "纬度必须在 -90 到 90 之间。",
                    step_id,
                    field,
                )
            )
        if longitude is None or longitude < -180 or longitude > 180:
            issues.append(
                self._issue(
                    "blocking",
                    "longitude_out_of_range",
                    "经度必须在 -180 到 180 之间。",
                    step_id,
                    field,
                )
            )
        return issues

    def _validate_side(
        self, step_id: str, side_ref: str
    ) -> list[CommandAdjudicationIssue]:
        if (
            resolve_side_reference_id(self.runtime.game.current_scenario.sides, side_ref)
            is not None
        ):
            return []
        return [
            self._issue(
                "blocking",
                "side_not_found",
                f"当前想定中找不到阵营：{side_ref}",
                step_id,
                "side",
            )
        ]

    @staticmethod
    def _issue(
        severity: str,
        code: str,
        message: str,
        step_id: str | None = None,
        field: str | None = None,
    ) -> CommandAdjudicationIssue:
        return CommandAdjudicationIssue(
            severity=severity, code=code, message=message, step_id=step_id, field=field
        )


class CommandApprovalQueue:
    """In-memory, runtime-local command approval queue."""

    def __init__(self, runtime: TianShuRuntime, registry: TianShuSkillRegistry) -> None:
        self.runtime = runtime
        self.registry = registry
        self.rules = CommandRuleEngine(runtime, registry)
        self._lock = RLock()
        self._proposals: dict[str, CommandProposal] = {}

    def create_proposal(
        self,
        *,
        command: str,
        steps: list[StructuredCommandStep],
        source: str,
        plan_metadata: dict[str, Any] | None = None,
    ) -> CommandProposal:
        now = _utc_now()
        adjudication = self.rules.adjudicate(steps)
        proposal = CommandProposal(
            id=str(uuid4()),
            command=command,
            source=source,
            status="blocked" if adjudication.status == "blocked" else "pending",
            created_at=now,
            updated_at=now,
            steps=steps,
            adjudication=adjudication,
            plan_metadata=plan_metadata or {},
        )
        with self._lock:
            self._proposals[proposal.id] = proposal
        return proposal

    def create_single_step_proposal(
        self,
        *,
        command: str,
        skill: str,
        parameters: dict[str, Any],
        source: str = "llm_tool",
        source_text: str = "",
    ) -> CommandProposal:
        step = StructuredCommandStep(
            id=str(uuid4()),
            skill=skill,
            parameters=parameters,
            source_text=source_text or command,
            summary=self._step_summary(skill, parameters),
            risk=self._risk_for_skill(skill),
            writes_runtime=True,
        )
        return self.create_proposal(command=command, steps=[step], source=source)

    def list_proposals(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[CommandProposal]:
        with self._lock:
            proposals = list(self._proposals.values())
        if status:
            proposals = [proposal for proposal in proposals if proposal.status == status]
        proposals.sort(key=lambda item: item.created_at, reverse=True)
        return proposals[: max(1, min(limit, 200))]

    def get(self, proposal_id: str) -> CommandProposal | None:
        with self._lock:
            return self._proposals.get(proposal_id)

    def hydrate(self, proposal: CommandProposal) -> CommandProposal:
        """Put a persisted proposal back into the runtime-local queue."""
        with self._lock:
            self._proposals[proposal.id] = proposal
            return proposal

    def reject(self, proposal_id: str, reason: str = "") -> CommandProposal:
        with self._lock:
            proposal = self._require(proposal_id)
            if proposal.status in {"executed", "partial"}:
                raise ValueError("已执行的命令提案不能驳回。")
            proposal.status = "rejected"
            proposal.error = reason or "Rejected by human operator."
            proposal.updated_at = _utc_now()
            self._proposals[proposal_id] = proposal
            return proposal

    def reject_loaded(
        self, proposal: CommandProposal, reason: str = ""
    ) -> CommandProposal:
        self.hydrate(proposal)
        return self.reject(proposal.id, reason=reason)

    def approve_and_execute(self, proposal_id: str) -> CommandProposal:
        with self._lock:
            proposal = self._require(proposal_id)
            if proposal.status == "blocked":
                raise ValueError("规则裁决未通过的命令提案不能审批执行。")
            if proposal.status not in {"pending", "approved", "failed"}:
                raise ValueError(f"当前状态不能审批执行：{proposal.status}")
            proposal.status = "approved"
            proposal.updated_at = _utc_now()

        execution: list[SkillExecutionResult] = []
        has_error = False
        for step in proposal.steps:
            try:
                output = self.registry.execute(step.skill, step.parameters)
                execution.append(
                    SkillExecutionResult(
                        skill=step.skill,
                        status="ok",
                        parameters=step.parameters,
                        output=output,
                    )
                )
            except Exception as exc:
                has_error = True
                execution.append(
                    SkillExecutionResult(
                        skill=step.skill,
                        status="error",
                        parameters=step.parameters,
                        error=str(exc),
                    )
                )
                break

        with self._lock:
            proposal = self._require(proposal_id)
            proposal.execution = execution
            if has_error and any(result.status == "ok" for result in execution):
                proposal.status = "partial"
                proposal.error = "部分命令已执行，后续步骤失败。"
            elif has_error:
                proposal.status = "failed"
                proposal.error = execution[-1].error if execution else "Execution failed."
            else:
                proposal.status = "executed"
                proposal.error = None
            proposal.updated_at = _utc_now()
            self._proposals[proposal_id] = proposal
            return proposal

    def approve_and_execute_loaded(
        self, proposal: CommandProposal
    ) -> CommandProposal:
        self.hydrate(proposal)
        return self.approve_and_execute(proposal.id)

    def _require(self, proposal_id: str) -> CommandProposal:
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            raise ValueError("命令提案不存在或已过期。")
        return proposal

    @staticmethod
    def _risk_for_skill(skill: str) -> str:
        if skill in HIGH_RISK_SKILLS:
            return "high"
        if skill in LOW_RISK_SKILLS:
            return "low"
        return "medium"

    @staticmethod
    def _step_summary(skill: str, parameters: dict[str, Any]) -> str:
        if skill.startswith("deploy_"):
            return f"部署 {parameters.get('class_name') or parameters.get('name') or '单位'}"
        if skill == "move_unit":
            return f"机动 {parameters.get('unit_type')} {parameters.get('unit_id')}"
        if skill == "delete_unit":
            return f"删除 {parameters.get('unit_type')} {parameters.get('unit_id')}"
        if skill == "simulation_step":
            return f"推进仿真 {parameters.get('steps', 1)} 秒"
        if skill == "attack_unit":
            return f"打击目标 {parameters.get('target_id') or ''}".strip()
        if skill == "update_weapon_quantity":
            return f"调整武器 {parameters.get('weapon_id') or ''}".strip()
        if skill == "load_scenario_snapshot":
            return f"Load scenario {parameters.get('name') or parameters.get('scenario_id') or ''}".strip()
        if skill in {"create_patrol_mission", "create_strike_mission"}:
            return f"Create mission {parameters.get('name') or ''}".strip()
        return skill.replace("_", " ")
