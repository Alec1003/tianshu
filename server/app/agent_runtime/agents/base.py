from __future__ import annotations

import logging
from typing import Any

from app.agent_runtime.agents.interface import BaseAgent
from app.agent_runtime.agents.model_factory import AgentModelConfig, NoAgentModelConfiguredError
from app.agent_runtime.agents.lifecycle import AgentLifecycle
from app.agent_runtime.agents.llm_adapter import LLMAdapter
from app.agent_runtime.agents.tool_loop import ToolLoop
from app.agent_runtime.tools.base import ToolContext

logger = logging.getLogger(__name__)


class QwenPawTextAgent(BaseAgent):
    """QwenPaw-style agent with native LLM tool-calling via OpenAI-compatible API.

    Requires a configured model (AgentModelConfig.is_configured == True).
    Tool schemas are converted to OpenAI tools format; the LLM decides which
    tool(s) to call, we execute them through the capability/tool registry,
    feed the results back via a multi-round ToolLoop, and stream the final
    text response.

    Raises:
        NoAgentModelConfiguredError: if model_config.is_configured is False.
    """

    def __init__(
        self,
        *,
        model_config: AgentModelConfig,
        system_prompt: str,
        workspace_context: dict[str, Any],
        tool_registry: Any,
        tool_context: ToolContext,
        capability_registry: Any | None = None,
        lifecycle: AgentLifecycle | None = None,
    ) -> None:
        if not model_config.is_configured:
            raise NoAgentModelConfiguredError(
                "QwenPawTextAgent requires a configured LLM model. "
                "Use AgentBuilder to create agents with proper model configuration."
            )
        self.model_config = model_config
        self.system_prompt = system_prompt
        self.workspace_context = workspace_context
        self.tool_registry = tool_registry
        self.capability_registry = capability_registry
        self.tool_context = tool_context
        self.lifecycle = lifecycle or AgentLifecycle()
        self._openai_tools_cache: list[dict[str, Any]] | None = None
        self._llm_adapter: LLMAdapter | None = None

    async def initialize(self) -> None:
        self.lifecycle.initialize()

    async def run(self, messages: list[dict[str, Any]]):
        async for event in self.reply_stream(messages):
            yield event

    async def close(self) -> None:
        self.lifecycle.close()

    async def reply_stream(self, messages: list[dict[str, Any]]):
        async for event in self._run_tool_loop(messages):
            yield event

    # ------------------------------------------------------------------
    # ToolLoop-based native tool calling
    # ------------------------------------------------------------------

    async def _run_tool_loop(self, messages: list[dict[str, Any]]):
        tools = self._get_openai_tools()
        provider_messages = self._provider_messages(messages)
        llm = self._get_llm_adapter()
        loop = ToolLoop(
            llm_adapter=llm,
            capability_registry=self.capability_registry,
            tool_registry=self.tool_registry,
            tool_context=self.tool_context,
        )
        # ToolLoop now yields AgentAction; the AgentExecutor
        # translates AgentAction -> AgentEvent upstream.
        async for action in loop.run(provider_messages, tools=tools):
            yield action

    # ------------------------------------------------------------------
    # OpenAI tools conversion (cached)
    # ------------------------------------------------------------------

    def _get_openai_tools(self) -> list[dict[str, Any]]:
        """Convert ToolRegistry schemas to OpenAI tools format, cached."""
        if self._openai_tools_cache is not None:
            return self._openai_tools_cache
        schemas: list[dict[str, Any]] = []
        if self.tool_registry is not None:
            schemas = self.tool_registry.schemas()
        tools: list[dict[str, Any]] = []
        for s in schemas:
            params = s.get("inputSchema", s.get("input_schema", {}))
            if not isinstance(params, dict):
                params = {"type": "object", "properties": {}}
            tools.append({
                "type": "function",
                "function": {
                    "name": s["name"],
                    "description": s.get("description", ""),
                    "parameters": params,
                },
            })
        self._openai_tools_cache = tools
        return tools

    # ------------------------------------------------------------------
    # Message construction
    # ------------------------------------------------------------------

    def _provider_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        provider_messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt}
        ]
        workspace_hint = self._workspace_hint()
        if workspace_hint:
            provider_messages.append({"role": "system", "content": workspace_hint})
        for message in messages:
            role = str(message.get("role") or "user")
            if role not in {"system", "user", "assistant", "tool"}:
                role = "user"
            content = message_text(message)
            if content:
                provider_messages.append({"role": role, "content": content})
        return provider_messages

    def _workspace_hint(self) -> str:
        scenario_id = self.workspace_context.get("scenario_id") or ""
        user_id = self.workspace_context.get("user_id") or ""
        tool_names = self.workspace_context.get("tool_names") or []
        memory_summary = self.workspace_context.get("memory_summary") or ""
        if not scenario_id and not user_id and not tool_names and not memory_summary:
            return ""
        hint = (
            f"Workspace context: user_id={user_id}; scenario_id={scenario_id}; "
            f"tools={', '.join(tool_names)}."
        )
        if memory_summary:
            hint += f"\nMemory summary:\n{memory_summary}"
        return hint

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def _execute_capability(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if self.capability_registry is not None:
            try:
                return await self.capability_registry.execute(
                    name, arguments, self.tool_context
                )
            except ValueError:
                logger.debug(
                    "CapabilityRegistry has no adapter for %s, falling back to ToolRegistry",
                    name,
                )
        if self.tool_registry is not None:
            return await self.tool_registry.execute(
                name, arguments, self.tool_context
            )
        raise ValueError(f"No registry available to execute tool: {name}")

    def _get_llm_adapter(self) -> LLMAdapter:
        if self._llm_adapter is None:
            self._llm_adapter = LLMAdapter(self.model_config)
        return self._llm_adapter


def message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text") or part.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    parts = message.get("parts")
    if isinstance(parts, list):
        text_parts: list[str] = []
        for part in parts:
            if isinstance(part, dict) and part.get("type") == "text":
                text = part.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
        return "\n".join(text_parts)
    return ""


def last_user_text(messages: list[dict[str, Any]]) -> str:
    if not messages:
        return ""
    return message_text(messages[-1])


__all__ = ["QwenPawTextAgent", "last_user_text", "message_text"]
