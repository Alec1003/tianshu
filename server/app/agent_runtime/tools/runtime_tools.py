from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

from app.agent_runtime.tools.base import ToolContext


READONLY_TOOL_NAMES = {
    "inspect_current_scenario",
    "list_runtime_tools",
}


@dataclass
class RuntimeSkillTool:
    """Agent-facing wrapper around a SkillRegistry capability."""

    name: str
    description: str
    input_schema: dict[str, Any]
    readonly: bool = False

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        effective_arguments = dict(arguments)
        if self.name == "doc-tools":
            folder = str(context.metadata.get("doc_folder") or "").strip()
            if folder:
                effective_arguments["project_id"] = folder
        if self.readonly:
            return await _execute_readonly(self.name, effective_arguments, context)

        risk_for_skill = getattr(context.approval_queue, "_risk_for_skill", None)
        risk = risk_for_skill(self.name) if callable(risk_for_skill) else "medium"
        if context.requires_approval(self.name, risk):
            proposal = context.approval_queue.create_single_step_proposal(
                command=context.source_command or self.name,
                skill=self.name,
                parameters=effective_arguments,
                source="llm_tool",
            )
            if context.proposal_recorder is not None:
                context.proposal_recorder(proposal)
            return {
                "proposalId": proposal.id,
                "proposalStatus": proposal.status,
                "requiresApproval": True,
                "adjudication": proposal.adjudication.model_dump(mode="json"),
            }

        result = context.skill_registry.execute(
            self.name,
            effective_arguments,
            source="agent",
            actor_id=context.user_id,
            scenario_id=context.scenario_id,
        )
        if inspect.isawaitable(result):
            result = await result
        return result if isinstance(result, dict) else {"value": result}


async def _execute_readonly(
    name: str,
    arguments: dict[str, Any],
    context: ToolContext,
) -> dict[str, Any]:
    if name == "inspect_current_scenario":
        scenario = context.workspace.exported_scenario()
        current = (
            scenario.get("currentScenario")
            if isinstance(scenario, dict)
            and isinstance(scenario.get("currentScenario"), dict)
            else scenario
        )
        return {
            "ok": True,
            "kind": "scenario_brief",
            "scenarioId": context.scenario_id,
            "scenarioName": str(current.get("name") or "")
            if isinstance(current, dict)
            else "",
            "counts": _scenario_counts(current),
            "entities": _scenario_entities(current),
        }

    if name == "list_runtime_tools":
        registry = getattr(context.workspace, "tool_registry", None)
        tools = registry.schemas() if registry is not None else []
        return {"ok": True, "tools": tools}

    return {"ok": False, "error": f"Unknown readonly tool: {name}"}


def _scenario_counts(current: Any) -> dict[str, int]:
    if not isinstance(current, dict):
        return {}
    return {
        "aircraft": len(current.get("aircraft") or []),
        "ships": len(current.get("ships") or []),
        "facilities": len(current.get("facilities") or []),
        "airbases": len(current.get("airbases") or []),
        "missions": len(current.get("missions") or []),
        "obstacles": len(current.get("obstacles") or []),
    }


def _scenario_entities(current: Any) -> list[dict[str, Any]]:
    if not isinstance(current, dict):
        return []
    entities: list[dict[str, Any]] = []
    for entity_type, keys in {
        "aircraft": ("aircraft",),
        "ship": ("ships", "ship"),
        "facility": ("facilities", "facility"),
        "airbase": ("airbases", "airbase"),
        "reference_point": ("referencePoints", "reference_points"),
    }.items():
        rows: list[Any] = []
        for key in keys:
            if isinstance(current.get(key), list):
                rows.extend(current[key])
        for row in rows:
            if not isinstance(row, dict):
                continue
            entities.append({
                "type": entity_type,
                "id": row.get("id"),
                "name": row.get("name") or row.get("className") or row.get("class_name"),
                "latitude": row.get("latitude"),
                "longitude": row.get("longitude"),
            })
    return entities[:128]
