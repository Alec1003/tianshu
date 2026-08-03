from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.agent_runtime.agents.capabilities import AgentCapability


MemoryScope = Literal["none", "workspace", "scenario", "global"]


@dataclass(frozen=True)
class AgentProfile:
    """Declarative agent definition registered inside a workspace."""

    name: str
    description: str = ""
    system_prompt: str = ""
    model_config: Any | None = None
    tool_permissions: dict[str, Any] = field(default_factory=dict)
    memory_scope: MemoryScope = "workspace"
    role: str = "default_assistant"
    capabilities: list[AgentCapability] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = ["AgentProfile", "MemoryScope"]
