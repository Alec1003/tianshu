from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentMessage:
    sender: str
    receiver: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = ["AgentMessage"]
