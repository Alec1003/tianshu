from __future__ import annotations

from typing import Any

from app.agent_runtime.tools.approval_tools import TacticalPlanOptionsTool
from app.agent_runtime.tools.base import ToolBase, ToolContext
from app.agent_runtime.tools.mcp_tools import MCPTool
from app.agent_runtime.tools.runtime_tools import RuntimeSkillTool


class ToolRegistry:
    """Agent-facing registry for tool discovery, schema export, and execution."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolBase] = {}

    def register(self, tool: ToolBase) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolBase:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ValueError(f"Tool not registered: {name}") from exc

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def tools(self) -> list[ToolBase]:
        return list(self._tools.values())

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
                "readonly": tool.readonly,
            }
            for tool in self.tools()
        ]

    async def load_driver_tools(self, workspace: Any) -> None:
        driver_registry = getattr(workspace, "driver_registry", None)
        if driver_registry is None:
            return
        for capability in await driver_registry.capabilities():
            if not self.has_tool(capability.name):
                self.register(MCPTool(capability))

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        return await self.get(name).execute(arguments, context)

    @classmethod
    def from_workspace(cls, workspace: Any) -> "ToolRegistry":
        existing = getattr(workspace, "tool_registry", None)
        if isinstance(existing, cls):
            return existing

        registry = cls()
        skill_registry = getattr(workspace, "skill_registry", None)
        if skill_registry is not None:
            for capability in skill_registry.capabilities():
                registry.register(
                    RuntimeSkillTool(
                        name=capability.name,
                        description=capability.description,
                        input_schema=_normalize_schema(capability.input_schema),
                        readonly=capability.readonly,
                    )
                )

        registry.register(
            RuntimeSkillTool(
                name="inspect_current_scenario",
                description="Read the current scenario summary without mutating runtime.",
                input_schema={"type": "object", "properties": {}},
                readonly=True,
            )
        )
        registry.register(
            RuntimeSkillTool(
                name="list_runtime_tools",
                description="List tools currently exposed to the agent.",
                input_schema={"type": "object", "properties": {}},
                readonly=True,
            )
        )
        registry.register(TacticalPlanOptionsTool())
        setattr(workspace, "tool_registry", registry)
        return registry


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
