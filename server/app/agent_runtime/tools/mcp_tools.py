from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agent_runtime.drivers.models import Capability
from app.agent_runtime.tools.base import ToolContext


@dataclass
class MCPTool:
    """Agent-facing adapter for an external MCP driver capability."""

    capability: Capability

    @property
    def name(self) -> str:
        return self.capability.name

    @property
    def description(self) -> str:
        return self.capability.description

    @property
    def input_schema(self) -> dict[str, Any]:
        return self.capability.input_schema

    @property
    def readonly(self) -> bool:
        return self.capability.readonly

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        if not self.readonly and context.approval_queue is not None:
            proposal = context.approval_queue.create_single_step_proposal(
                command=context.source_command or self.name,
                skill=self.name,
                parameters=arguments,
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

        driver_registry = getattr(context.workspace, "driver_registry", None)
        if driver_registry is None:
            return {"ok": False, "error": "Driver registry is unavailable."}
        return await driver_registry.execute(
            self.capability.provider,
            self.capability.name,
            arguments,
        )
