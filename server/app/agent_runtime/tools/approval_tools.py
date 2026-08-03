from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.agent_runtime.tools.base import ToolContext
from app.ai.models import StructuredCommandStep, TacticalPlanOptionDraft


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
                    "options": {"type": "array"},
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
        for option_index, raw_option in enumerate(raw_options):
            option = TacticalPlanOptionDraft.model_validate(raw_option)
            steps = [
                StructuredCommandStep(
                    id=f"plan-{option_index + 1}-step-{step_index + 1}-{uuid4()}",
                    skill=step.skill,
                    parameters=step.parameters,
                    source_text=step.rationale or option.description or step.summary,
                    summary=step.summary or step.skill.replace("_", " "),
                    risk=step.risk,
                    writes_runtime=True,
                )
                for step_index, step in enumerate(option.steps)
            ]
            proposal = context.approval_queue.create_proposal(
                command=str(arguments.get("command") or option.title),
                steps=steps,
                source="llm_plan",
                plan_metadata={
                    "kind": "tactical_plan_option",
                    "title": option.title,
                    "label": option.label,
                    "description": option.description,
                    "advantages": option.advantages,
                    "risks": option.risks,
                    "optionIndex": option_index + 1,
                    "toolCount": len(steps),
                },
            )
            if context.proposal_recorder is not None:
                context.proposal_recorder(proposal)
            proposals.append(
                {
                    "proposalId": proposal.id,
                    "proposalStatus": proposal.status,
                    "title": option.title,
                    "label": option.label,
                    "stepCount": len(steps),
                    "adjudication": proposal.adjudication.model_dump(mode="json"),
                }
            )

        return {
            "ok": True,
            "kind": "tactical_plan_options",
            "requiresApproval": True,
            "proposalCount": len(proposals),
            "proposals": proposals,
        }
