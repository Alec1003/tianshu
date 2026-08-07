from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.agent_runtime.tools.base import ToolContext
from app.ai.models import StructuredCommandStep, TacticalPlanOptionDraft


PLAN_SKILL_ALIASES = {
    "航空侦察": "create_patrol_mission",
    "空中巡逻": "create_patrol_mission",
    "对海突击": "create_strike_mission",
    "对海袭击": "attack_unit",
    "对空轰击": "attack_unit",
}


def _plan_group_key(command: str) -> str:
    return " ".join(command.casefold().split())[:240]


def _option_key(option: TacticalPlanOptionDraft) -> str:
    label = option.label.strip().casefold()
    match = re.search(r"(?:方案|plan|option)\s*([a-z])", label)
    if match:
        return f"label:{match.group(1)}"
    return "title:" + " ".join(option.title.casefold().split())


def _unit_collections(scenario: Any) -> dict[str, list[Any]]:
    return {
        "aircraft": list(getattr(scenario, "aircraft", []) or []),
        "ship": list(getattr(scenario, "ships", []) or []),
        "facility": list(getattr(scenario, "facilities", []) or []),
        "airbase": list(getattr(scenario, "airbases", []) or []),
        "reference_point": list(getattr(scenario, "reference_points", []) or []),
    }


def _unit_id_matches(unit: Any, candidate: str) -> bool:
    token = candidate.strip().casefold()
    if not token:
        return False
    values = {
        str(getattr(unit, "id", "")),
        str(getattr(unit, "name", "")),
        str(getattr(unit, "class_name", "")),
        str(getattr(unit, "className", "")),
    }
    return any(value.strip().casefold() == token for value in values if value.strip())


def _resolve_unit_id(scenario: Any, unit_type: str, candidate: Any) -> str:
    raw = str(candidate or "").strip()
    if not raw:
        return raw
    matches = [
        unit
        for unit in _unit_collections(scenario).get(unit_type.strip().casefold(), [])
        if _unit_id_matches(unit, raw)
    ]
    return str(getattr(matches[0], "id", raw)) if len(matches) == 1 else raw


def _normalize_plan_parameters(skill: str, parameters: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    normalized = dict(parameters)
    scenario = getattr(getattr(context.approval_queue, "runtime", None), "game", None)
    scenario = getattr(scenario, "current_scenario", None)
    if scenario is None:
        return normalized

    if skill in {"move_unit", "update_unit_state"}:
        unit_type = str(normalized.get("unit_type") or "").strip()
        normalized["unit_id"] = _resolve_unit_id(
            scenario, unit_type, normalized.get("unit_id")
        )
        if skill == "move_unit" and not normalized.get("route"):
            collections = _unit_collections(scenario).get(unit_type.casefold(), [])
            unit = next(
                (item for item in collections if str(getattr(item, "id", "")) == normalized["unit_id"]),
                None,
            )
            latitude = getattr(unit, "latitude", None)
            longitude = getattr(unit, "longitude", None)
            if latitude is not None and longitude is not None:
                normalized["route"] = [[float(latitude), float(longitude)]]
    elif skill == "attack_unit":
        attacker_type = str(normalized.get("attacker_type") or "").strip()
        normalized["attacker_id"] = _resolve_unit_id(
            scenario, attacker_type, normalized.get("attacker_id")
        )
        target = str(normalized.get("target_id") or "").strip()
        all_units = [
            unit
            for key, values in _unit_collections(scenario).items()
            if key in {"aircraft", "ship", "facility", "airbase"}
            for unit in values
        ]
        target_matches = [unit for unit in all_units if _unit_id_matches(unit, target)]
        if len(target_matches) == 1:
            normalized["target_id"] = str(getattr(target_matches[0], "id", target))
    return normalized


@dataclass
class TacticalPlanOptionsTool:
    name: str = "propose_tactical_plan_options"
    description: str = "Create human-reviewable approval cards for tactical plan options."
    input_schema: dict[str, Any] = None  # type: ignore[assignment]
    readonly: bool = False

    def __post_init__(self) -> None:
        if self.input_schema is None:
            self.input_schema = {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "label": {"type": "string"},
                                "description": {"type": "string"},
                                "advantages": {"type": "array", "items": {"type": "string"}},
                                "risks": {"type": "array", "items": {"type": "string"}},
                                "steps": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "skill": {
                                                "type": "string",
                                                "enum": [
                                                    "move_unit",
                                                    "attack_unit",
                                                    "create_patrol_mission",
                                                    "create_strike_mission",
                                                    "simulation_step",
                                                ],
                                            },
                                            "parameters": {"type": "object"},
                                            "summary": {"type": "string"},
                                            "rationale": {"type": "string"},
                                            "risk": {"type": "string", "enum": ["low", "medium", "high"]},
                                        },
                                        "required": ["skill", "parameters"],
                                    },
                                },
                            },
                            "required": ["title", "steps"],
                        },
                    },
                },
                "required": ["options"],
            }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        if context.approval_queue is None:
            return {"ok": False, "error": "Approval queue is unavailable."}
        raw_options = arguments.get("options")
        if not isinstance(raw_options, list) or not raw_options:
            return {"ok": False, "error": "At least one tactical plan option is required."}

        proposals = []
        seen_options: set[str] = set()
        seen_option_keys: set[str] = set()
        command = str(arguments.get("command") or "生成作战方案").strip()
        plan_group_key = _plan_group_key(command)
        for raw_option in raw_options:
            option = TacticalPlanOptionDraft.model_validate(raw_option)
            fingerprint = json.dumps(
                option.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
            )
            option_key = _option_key(option)
            if fingerprint in seen_options or option_key in seen_option_keys:
                continue
            if context.approval_queue.find_active_plan_option(
                plan_group_key=plan_group_key,
                option_key=option_key,
            ) is not None:
                continue
            seen_options.add(fingerprint)
            seen_option_keys.add(option_key)
            option_index = len(proposals)
            steps = [
                StructuredCommandStep(
                    id=f"plan-{option_index + 1}-step-{step_index + 1}-{uuid4()}",
                    skill=PLAN_SKILL_ALIASES.get(step.skill.strip(), step.skill.strip()),
                    parameters=_normalize_plan_parameters(
                        PLAN_SKILL_ALIASES.get(step.skill.strip(), step.skill.strip()),
                        step.parameters,
                        context,
                    ),
                    source_text=step.rationale or option.description or step.summary,
                    summary=step.summary or step.skill.replace("_", " "),
                    risk=step.risk,
                    writes_runtime=True,
                )
                for step_index, step in enumerate(option.steps)
            ]
            proposal = context.approval_queue.create_proposal(
                command=command,
                steps=steps,
                source="llm_plan",
                plan_metadata={
                    "kind": "tactical_plan_option",
                    "title": option.title,
                    "label": f"方案 {chr(65 + option_index)}",
                    "description": option.description,
                    "advantages": option.advantages,
                    "risks": option.risks,
                    "optionIndex": option_index + 1,
                    "toolCount": len(steps),
                    "planGroupKey": plan_group_key,
                    "optionKey": option_key,
                },
            )
            if proposal.status == "blocked":
                continue
            # Approval mode ``off`` disables the human gate, but never the
            # rule adjudication.  A valid tactical option can therefore run
            # immediately; a blocked option remains blocked.
            if (
                getattr(context.approval_queue, "mode", "auto") == "off"
                and proposal.status != "blocked"
            ):
                proposal = context.approval_queue.approve_and_execute(proposal.id)
            if context.proposal_recorder is not None:
                context.proposal_recorder(proposal)
            proposals.append(
                {
                    "proposalId": proposal.id,
                    "proposalStatus": proposal.status,
                    "title": option.title,
                    "label": option.label,
                    "optionKey": option_key,
                    "stepCount": len(steps),
                    "adjudication": proposal.adjudication.model_dump(mode="json"),
                }
            )

        return {
            "ok": True,
            "kind": "tactical_plan_options",
            "requiresApproval": any(
                item["proposalStatus"] == "pending" for item in proposals
            ),
            "proposalCount": len(proposals),
            "proposals": proposals,
        }
