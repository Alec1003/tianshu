from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agent_runtime.agents.base import QwenPawTextAgent
from app.agent_runtime.agents.lifecycle import AgentLifecycle
from app.agent_runtime.agents.model_factory import AgentModelConfig
from app.agent_runtime.agents.profile import AgentProfile
from app.agent_runtime.tools.base import ToolContext


@dataclass(frozen=True)
class AgentCreateSpec:
    model_config: AgentModelConfig
    system_prompt: str
    workspace_context: dict[str, Any]
    tool_registry: Any
    tool_context: ToolContext
    capability_registry: Any | None = None
    profile: AgentProfile | None = None


class AgentFactory:
    """Create concrete TianShu agent instances from declarative profiles."""

    def create(
        self,
        profile: AgentProfile | AgentCreateSpec,
        *,
        model_config: AgentModelConfig | None = None,
        system_prompt: str | None = None,
        workspace_context: dict[str, Any] | None = None,
        tool_registry: Any = None,
        capability_registry: Any = None,
        tool_context: ToolContext | None = None,
    ) -> QwenPawTextAgent:
        if isinstance(profile, AgentCreateSpec):
            spec = profile
        else:
            missing = [
                name
                for name, value in {
                    "model_config": model_config,
                    "system_prompt": system_prompt,
                    "workspace_context": workspace_context,
                    "tool_registry": tool_registry,
                    "tool_context": tool_context,
                }.items()
                if value is None
            ]
            if missing:
                raise TypeError(
                    "AgentFactory.create(profile) missing resolved values: "
                    + ", ".join(missing)
                )
            spec = AgentCreateSpec(
                model_config=model_config,
                system_prompt=system_prompt,
                workspace_context=workspace_context,
                tool_registry=tool_registry,
                capability_registry=capability_registry,
                tool_context=tool_context,
                profile=profile,
            )
        lifecycle = AgentLifecycle()
        lifecycle.initialize()
        agent = QwenPawTextAgent(
            model_config=spec.model_config,
            system_prompt=spec.system_prompt,
            workspace_context=spec.workspace_context,
            tool_registry=spec.tool_registry,
            capability_registry=spec.capability_registry,
            tool_context=spec.tool_context,
            lifecycle=lifecycle,
        )
        agent.profile = spec.profile
        return agent


__all__ = ["AgentCreateSpec", "AgentFactory"]
