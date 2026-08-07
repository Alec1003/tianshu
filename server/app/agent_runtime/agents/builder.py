from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import logging

from app.agent_runtime.agents.base import QwenPawTextAgent, last_user_text
from app.agent_runtime.agents.factory import AgentFactory
from app.agent_runtime.agents.model_factory import (
    AgentModelConfig,
    ModelFactory,
)
from app.agent_runtime.agents.prompt import PromptBuilder
from app.agent_runtime.agents.profile import AgentProfile
from app.agent_runtime.capabilities.resolver import CapabilityResolver
from app.agent_runtime.capabilities.selector import DynamicCapabilitySelector, last_user_message_text
from app.agent_runtime.tools.base import ToolContext
from app.agent_runtime.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class AgentBuildPlan:
    """Intermediate values resolved before creating a concrete agent."""

    model_config: AgentModelConfig
    system_prompt: str
    tool_registry: Any
    capability_registry: Any
    tool_context: ToolContext
    workspace_context: dict[str, Any]


class AgentBuilder:
    """Assemble a TianShu agent from model, prompt, tools, and context."""

    def __init__(
        self,
        *,
        model_factory: ModelFactory | None = None,
        prompt_builder: PromptBuilder | None = None,
        agent_factory: AgentFactory | None = None,
    ) -> None:
        self.model_factory = model_factory or ModelFactory()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.agent_factory = agent_factory or AgentFactory()

    async def build(self, request: Any) -> QwenPawTextAgent:
        return await self.build_with_profile(request, None)

    async def build_with_profile(
        self,
        request: Any,
        profile: AgentProfile | None,
    ) -> QwenPawTextAgent:
        profile = profile or AgentProfile(name="default")
        plan = await self.build_plan(request, profile)
        return self.agent_factory.create(
            profile,
            model_config=plan.model_config,
            system_prompt=plan.system_prompt,
            workspace_context=plan.workspace_context,
            tool_registry=plan.tool_registry,
            capability_registry=plan.capability_registry,
            tool_context=plan.tool_context,
        )

    async def build_plan(
        self,
        request: Any,
        profile: AgentProfile | None = None,
    ) -> AgentBuildPlan:
        model_config = self.resolve_model(request, profile)
        chat_mode = self._resolve_chat_mode(request)
        tool_registry = self.resolve_tools(request)
        workspace = getattr(request, "workspace", None)
        if workspace is not None:
            await tool_registry.load_driver_tools(workspace)
        tool_registry = CapabilityResolver.resolve_tools(tool_registry, chat_mode)
        tool_registry = self._apply_dynamic_selection(tool_registry, request, chat_mode)
        capability_registry = await self.resolve_capabilities(request)
        plan = AgentBuildPlan(
            model_config=model_config,
            system_prompt=self.resolve_prompt(request, profile),
            tool_registry=tool_registry,
            capability_registry=capability_registry,
            tool_context=self.resolve_tool_context(request),
            workspace_context=self.resolve_workspace_context(
                request,
                tool_registry,
                capability_registry,
            ),
        )
        logger.info(
            "AgentBuilder.build_plan mode=%s model=%s tools=%d [%s]",
            chat_mode,
            model_config.model or "none",
            tool_registry.tool_count,
            CapabilityResolver.tool_names_for_log(tool_registry),
        )
        return plan

    @staticmethod
    def _resolve_chat_mode(request: Any) -> str:
        return "command"

    def _apply_dynamic_selection(
        self,
        tool_registry: Any,
        request: Any,
        chat_mode: str,
    ) -> Any:
        if chat_mode != "command":
            return tool_registry
        query = last_user_message_text(getattr(request, "messages", []) or [])
        if not query:
            return tool_registry
        available = tool_registry.tool_names
        selected_names = DynamicCapabilitySelector.select(
            query, available, chat_mode
        )
        if len(selected_names) >= len(available):
            return tool_registry
        filtered = tool_registry.copy()
        filtered._tools = {
            name: tool_registry._tools[name]
            for name in selected_names
            if name in tool_registry._tools
        }
        logger.info(
            "AgentBuilder dynamic selection: query=%r tools %d -> %d [%s]",
            query[:80],
            tool_registry.tool_count,
            filtered.tool_count,
            ", ".join(selected_names) if len(selected_names) <= 10 else f"{len(selected_names)} tools",
        )
        return filtered

    def resolve_model(
        self,
        request: Any,
        profile: AgentProfile | None = None,
    ) -> AgentModelConfig:
        return self.model_factory.resolve(request, profile)

    def resolve_prompt(
        self,
        request: Any,
        profile: AgentProfile | None = None,
    ) -> str:
        return self.prompt_builder.build(request, profile)

    def resolve_tools(self, request: Any) -> ToolRegistry:
        existing = getattr(request, "tool_registry", None)
        if existing is not None:
            return existing
        workspace = getattr(request, "workspace", None)
        if workspace is not None:
            return ToolRegistry.from_workspace(workspace)
        return ToolRegistry()

    async def resolve_capabilities(self, request: Any) -> Any:
        workspace = getattr(request, "workspace", None)
        registry = getattr(request, "capability_registry", None) or getattr(
            workspace,
            "capability_registry",
            None,
        )
        if registry is not None:
            load = getattr(registry, "load_from_workspace", None)
            if callable(load) and workspace is not None:
                await load(workspace)
            return registry
        return None

    def resolve_workspace_context(
        self,
        request: Any,
        tool_registry: ToolRegistry | None = None,
        capability_registry: Any | None = None,
    ) -> dict[str, Any]:
        registry = tool_registry or self.resolve_tools(request)
        capability_schemas = (
            capability_registry.schemas()
            if capability_registry is not None and hasattr(capability_registry, "schemas")
            else []
        )
        return {
            "user_id": getattr(request, "user_id", "") or "",
            "scenario_id": getattr(request, "scenario_id", "") or "",
            "chat_mode": getattr(request, "chat_mode", "") or "",
            "tool_names": [tool["name"] for tool in registry.schemas()],
            "available_capabilities": capability_schemas,
            "capability_names": [
                capability["name"] for capability in capability_schemas
            ],
            "memory_summary": getattr(getattr(request, "agent_context", None), "memory_summary", ""),
        }

    def resolve_tool_context(self, request: Any) -> ToolContext:
        workspace = getattr(request, "workspace", None)
        return ToolContext(
            workspace=workspace,
            skill_registry=getattr(workspace, "skill_registry", None),
            capability_registry=getattr(workspace, "capability_registry", None),
            approval_queue=getattr(request, "approval_queue", None),
            user_id=getattr(request, "user_id", "") or "",
            scenario_id=getattr(request, "scenario_id", "") or "",
            source_command=last_user_text(getattr(request, "messages", []) or ""),
            proposal_recorder=(getattr(request, "metadata", {}) or {}).get(
                "proposal_recorder"
            ),
            metadata={
                **(getattr(request, "metadata", {}) or {}),
                "approval_mode": getattr(request, "approval_mode", "auto") or "auto",
            },
        )

    # Backward-compatible helper names used by older tests and call sites.
    def _resolve_model_config(self, request: Any) -> AgentModelConfig:
        return self.resolve_model(request)

    def _build_prompt(self, request: Any) -> str:
        return self.resolve_prompt(request)

    def _workspace_context(self, request: Any) -> dict[str, Any]:
        return self.resolve_workspace_context(request)

    def _tool_registry(self, request: Any) -> ToolRegistry:
        return self.resolve_tools(request)

    def _tool_context(self, request: Any) -> ToolContext:
        return self.resolve_tool_context(request)


__all__ = ["AgentBuildPlan", "AgentBuilder"]
