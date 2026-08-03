from __future__ import annotations

from typing import Any


class TianShuLocalWorkspace:
    """Agent-facing local workspace facade for tool discovery."""

    def __init__(self, workspace: Any) -> None:
        self.workspace = workspace

    def get_tools(self) -> list[Any]:
        registry = getattr(self.workspace, "tool_registry", None)
        return registry.tools() if registry is not None else []

    def schemas(self) -> list[dict[str, Any]]:
        registry = getattr(self.workspace, "tool_registry", None)
        return registry.schemas() if registry is not None else []


__all__ = ["TianShuLocalWorkspace"]
