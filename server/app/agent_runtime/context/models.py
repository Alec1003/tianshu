from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.agent_runtime.memory.models import MemoryItem


@dataclass
class AgentContext:
    user_id: str
    workspace_id: str
    scenario_id: str
    runtime_state: dict[str, Any] = field(default_factory=dict)
    recent_messages: list[dict[str, Any]] = field(default_factory=list)
    memory_items: list[MemoryItem] = field(default_factory=list)
    memory_summary: str = ""
    available_tools: list[dict[str, Any]] = field(default_factory=list)
    available_capabilities: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_prompt_context(self) -> str:
        sections = [
            "Workspace Context",
            f"- user_id: {self.user_id}",
            f"- workspace_id: {self.workspace_id}",
            f"- scenario_id: {self.scenario_id}",
        ]
        if self.runtime_state:
            sections.append(f"- runtime_state: {self.runtime_state}")
        if self.memory_summary:
            sections.append("Memory Summary:\n" + self.memory_summary)
        if self.available_tools:
            tool_names = ", ".join(str(tool.get("name")) for tool in self.available_tools[:40])
            sections.append("Available Tools:\n" + tool_names)
        if self.available_capabilities:
            capability_names = ", ".join(
                str(capability.get("name"))
                for capability in self.available_capabilities[:60]
            )
            sections.append("Available Capabilities:\n" + capability_names)
        if self.recent_messages:
            sections.append("Recent Messages:\n" + _messages_summary(self.recent_messages))
        return "\n".join(sections)


def _messages_summary(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for message in messages[-8:]:
        role = str(message.get("role") or "user")
        text = _message_text(message)
        if text:
            lines.append(f"{role}: {text[:500]}")
    return "\n".join(lines)


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    parts = message.get("parts")
    if isinstance(parts, list):
        texts = [
            str(part.get("text"))
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        return "\n".join(texts)
    return ""
