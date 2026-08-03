from __future__ import annotations

import inspect
from typing import Any

from app.agent_runtime.capabilities.models import Capability
from app.agent_runtime.tools.base import ToolContext


class SkillCapabilityAdapter:
    """Expose TianShu SkillRegistry capabilities through the unified layer."""

    source = "skill"

    def __init__(self, skill_registry: Any) -> None:
        self.skill_registry = skill_registry

    async def discover(self) -> list[Capability]:
        capabilities = []
        for item in self.skill_registry.capabilities():
            permission = "read" if getattr(item, "readonly", False) else "write"
            capabilities.append(
                Capability(
                    name=item.name,
                    description=getattr(item, "description", ""),
                    source="skill",
                    provider="tianshu",
                    permission=permission,
                    input_schema=_normalize_schema(getattr(item, "input_schema", {}) or {}),
                    metadata={"readonly": getattr(item, "readonly", False)},
                )
            )
        capabilities.extend(_builtin_readonly_capabilities())
        return capabilities

    async def execute(
        self,
        capability: Capability,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        if capability.name == "inspect_current_scenario":
            return _inspect_current_scenario(context)
        if capability.name == "list_capabilities":
            registry = getattr(context.workspace, "capability_registry", None)
            schemas = registry.schemas() if registry is not None else []
            return {"ok": True, "capabilities": schemas}
        if capability.readonly:
            return {"ok": False, "error": f"Unknown readonly capability: {capability.name}"}
        if context.approval_queue is not None:
            proposal = context.approval_queue.create_single_step_proposal(
                command=context.source_command or capability.name,
                skill=capability.name,
                parameters=arguments,
                source="llm_capability",
            )
            if context.proposal_recorder is not None:
                context.proposal_recorder(proposal)
            return {
                "proposalId": proposal.id,
                "proposalStatus": proposal.status,
                "requiresApproval": True,
                "adjudication": proposal.adjudication.model_dump(mode="json"),
            }
        result = self.skill_registry.execute(
            capability.name,
            arguments,
            source="agent",
            actor_id=context.user_id,
            scenario_id=context.scenario_id,
        )
        if inspect.isawaitable(result):
            result = await result
        return result if isinstance(result, dict) else {"value": result}


class DriverCapabilityAdapter:
    """Expose external DriverRegistry capabilities through the unified layer."""

    source = "driver"

    def __init__(self, driver_registry: Any) -> None:
        self.driver_registry = driver_registry

    async def discover(self) -> list[Capability]:
        capabilities = []
        for item in await self.driver_registry.capabilities():
            capabilities.append(
                Capability(
                    name=item.name,
                    description=getattr(item, "description", ""),
                    source="driver",
                    provider=getattr(item, "provider", ""),
                    permission=getattr(item, "permission", "read"),
                    input_schema=getattr(item, "input_schema", {}) or {},
                    output_schema=getattr(item, "output_schema", {}) or {},
                    metadata=getattr(item, "metadata", {}) or {},
                )
            )
        return capabilities

    async def execute(
        self,
        capability: Capability,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        if not capability.readonly and context.approval_queue is not None:
            proposal = context.approval_queue.create_single_step_proposal(
                command=context.source_command or capability.name,
                skill=capability.name,
                parameters=arguments,
                source="llm_capability",
            )
            if context.proposal_recorder is not None:
                context.proposal_recorder(proposal)
            return {
                "proposalId": proposal.id,
                "proposalStatus": proposal.status,
                "requiresApproval": True,
                "adjudication": proposal.adjudication.model_dump(mode="json"),
            }
        return await self.driver_registry.execute(
            capability.provider,
            capability.name,
            arguments,
        )


def _builtin_readonly_capabilities() -> list[Capability]:
    return [
        Capability(
            name="inspect_current_scenario",
            description="Read the current scenario summary without mutating runtime.",
            source="skill",
            provider="tianshu",
            permission="read",
            input_schema={"type": "object", "properties": {}},
        ),
        Capability(
            name="list_capabilities",
            description="List capabilities currently exposed to the agent.",
            source="skill",
            provider="tianshu",
            permission="read",
            input_schema={"type": "object", "properties": {}},
        ),
    ]


def _inspect_current_scenario(context: ToolContext) -> dict[str, Any]:
    scenario = context.workspace.exported_scenario()
    current = (
        scenario.get("currentScenario")
        if isinstance(scenario, dict) and isinstance(scenario.get("currentScenario"), dict)
        else scenario
    )
    return {
        "ok": True,
        "kind": "scenario_brief",
        "scenarioId": context.scenario_id,
        "scenarioName": str(current.get("name") or "") if isinstance(current, dict) else "",
        "counts": _scenario_counts(current),
    }


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


def _normalize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    if schema.get("type") == "object":
        return schema
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, field_schema in schema.items():
        if not isinstance(field_schema, dict):
            properties[name] = {"type": "string"}
            required.append(name)
            continue
        normalized = {k: v for k, v in field_schema.items() if k != "required"}
        properties[name] = normalized or {"type": "string"}
        if field_schema.get("required", True) is not False:
            required.append(name)
    output: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        output["required"] = required
    return output


__all__ = ["DriverCapabilityAdapter", "SkillCapabilityAdapter"]
