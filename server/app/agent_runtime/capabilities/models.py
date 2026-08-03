from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


CapabilityPermission = Literal["read", "write", "control"]


@dataclass(frozen=True)
class Capability:
    name: str
    description: str = ""
    source: Literal["skill", "driver"] = "skill"
    provider: str = ""
    permission: CapabilityPermission = "read"
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def readonly(self) -> bool:
        return self.permission == "read"

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "source": self.source,
            "provider": self.provider,
            "permission": self.permission,
            "inputSchema": self.input_schema,
            "outputSchema": self.output_schema,
            "readonly": self.readonly,
            "metadata": self.metadata,
        }


__all__ = ["Capability", "CapabilityPermission"]
