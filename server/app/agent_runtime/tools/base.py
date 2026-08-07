from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any, Protocol


@dataclass
class ToolContext:
    """Per-call context supplied by AgentRuntime tool adapters."""

    workspace: Any
    skill_registry: Any
    capability_registry: Any | None = None
    approval_queue: Any | None = None
    user_id: str = ""
    scenario_id: str = ""
    source_command: str = ""
    proposal_recorder: Callable[[Any], None] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def requires_approval(self, skill: str, risk: str = "medium") -> bool:
        if self.approval_queue is None:
            return False
        policy = getattr(self.approval_queue, "should_auto_execute", None)
        return not policy(skill, risk) if callable(policy) else True


class ToolBase(Protocol):
    name: str
    description: str
    input_schema: dict[str, Any]
    readonly: bool

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        """Execute the tool and return a JSON-serializable result."""
