from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


CapabilityPermission = Literal["read", "write", "control"]


@dataclass(frozen=True)
class Capability:
    """Unified capability surfaced from Skill providers or external drivers."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    source: Literal["skill", "driver"] = "driver"
    provider: str = ""
    permission: CapabilityPermission = "read"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def readonly(self) -> bool:
        return self.permission == "read"
