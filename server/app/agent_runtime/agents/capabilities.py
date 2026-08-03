from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentCapability:
    """Declarative capability exposed by an agent profile."""

    name: str
    description: str = ""
    permissions: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = ["AgentCapability"]
