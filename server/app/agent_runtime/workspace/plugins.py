from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkspacePlugins:
    """Per-workspace extension container.

    Phase 6.2 only establishes ownership. Tool, driver, memory, and hook
    migration remain in their existing implementations.
    """

    tool_registry: Any | None = None
    driver_registry: Any | None = None
    hook_registry: Any | None = None
    prompt_manager: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = ["WorkspacePlugins"]
