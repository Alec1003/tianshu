from __future__ import annotations

from typing import Any

from app.agent_runtime.context.builder import ContextBuilder, runtime_state_from_workspace
from app.agent_runtime.context.models import AgentContext
from app.agent_runtime.memory.manager import MemoryManager


class ContextManager:
    """Workspace-scoped context manager for AgentRuntime requests."""

    def __init__(
        self,
        *,
        memory_manager: MemoryManager | None = None,
        builder: ContextBuilder | None = None,
    ) -> None:
        self.memory_manager = memory_manager or MemoryManager()
        self.builder = builder or ContextBuilder()

    async def build(self, request: Any) -> AgentContext:
        workspace = getattr(request, "workspace", None)
        workspace_id = _workspace_id(request, workspace)
        scenario_id = str(getattr(request, "scenario_id", "") or "")
        query = _last_user_text(list(getattr(request, "messages", []) or []))
        agent_name = (getattr(request, "metadata", {}) or {}).get("agent_name", "default")
        memories = self.memory_manager.retrieve_for_agent(
            workspace_id=workspace_id,
            scenario_id=scenario_id,
            agent_name=str(agent_name),
            query=query,
            limit=12,
        )
        available_tools = []
        available_capabilities = []
        capability_registry = getattr(request, "capability_registry", None) or getattr(
            workspace,
            "capability_registry",
            None,
        )
        if capability_registry is not None:
            await capability_registry.load_from_workspace(workspace)
            available_capabilities = capability_registry.schemas()
        tool_registry = getattr(request, "tool_registry", None) or getattr(
            workspace,
            "tool_registry",
            None,
        )
        if tool_registry is not None:
            available_tools = tool_registry.schemas()
        return AgentContext(
            user_id=str(getattr(request, "user_id", "") or ""),
            workspace_id=workspace_id,
            scenario_id=scenario_id,
            runtime_state=runtime_state_from_workspace(workspace),
            recent_messages=list(getattr(request, "messages", []) or [])[-8:],
            memory_items=memories,
            memory_summary=self._memory_summary(memories),
            available_tools=available_tools,
            available_capabilities=available_capabilities,
            metadata={"prompt_context": ""},
        )

    def prompt_context(self, context: AgentContext) -> str:
        return self.builder.build_prompt_context(context)

    @staticmethod
    def _memory_summary(memories) -> str:
        lines = []
        for item in memories[:12]:
            label = item.memory_type
            if item.scenario_id:
                label += f":{item.scenario_id}"
            lines.append(
                "- "
                f"[{label} importance={item.importance:.2f} "
                f"confidence={item.confidence:.2f}] {item.content}"
            )
        return "\n".join(lines)


def _workspace_id(request: Any, workspace: Any) -> str:
    explicit = getattr(request, "workspace_id", None)
    if explicit:
        return str(explicit)
    for attr in ("workspace_id", "id"):
        value = getattr(workspace, attr, None)
        if value:
            return str(value)
    return str(getattr(request, "user_id", "") or "default")


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if str(message.get("role") or "") == "user":
            content = message.get("content")
            if isinstance(content, str):
                return content
    return ""
