from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4


MemoryType = Literal["global", "workspace", "scenario"]
MemoryStatus = Literal["candidate", "confirmed", "active", "archived"]
MemorySource = Literal["user", "system", "agent", "operator", "import"]


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class MemoryItem:
    id: str
    workspace_id: str
    scenario_id: str
    memory_type: MemoryType
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5
    confidence: float = 1.0
    source: MemorySource = "user"
    status: MemoryStatus = "active"
    tags: list[str] = field(default_factory=list)
    access_count: int = 0
    last_accessed: str | None = None
    expires_at: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    @classmethod
    def create(
        cls,
        *,
        workspace_id: str,
        scenario_id: str = "",
        memory_type: MemoryType,
        content: str,
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
        confidence: float = 1.0,
        source: MemorySource = "user",
        status: MemoryStatus = "active",
        tags: list[str] | None = None,
        expires_at: str | None = None,
    ) -> "MemoryItem":
        return cls(
            id=f"mem_{uuid4().hex}",
            workspace_id=workspace_id,
            scenario_id=scenario_id if memory_type == "scenario" else "",
            memory_type=memory_type,
            content=content,
            metadata=metadata or {},
            importance=_clamp(importance),
            confidence=_clamp(confidence),
            source=source,
            status=status,
            tags=tags or [],
            expires_at=expires_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "scenario_id": self.scenario_id,
            "memory_type": self.memory_type,
            "content": self.content,
            "metadata": self.metadata,
            "importance": self.importance,
            "confidence": self.confidence,
            "source": self.source,
            "status": self.status,
            "tags": self.tags,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryItem":
        return cls(
            id=str(data["id"]),
            workspace_id=str(data.get("workspace_id") or ""),
            scenario_id=str(data.get("scenario_id") or ""),
            memory_type=data.get("memory_type") or "workspace",
            content=str(data.get("content") or ""),
            metadata=dict(data.get("metadata") or {}),
            importance=_clamp(data.get("importance", 0.5)),
            confidence=_clamp(data.get("confidence", 1.0)),
            source=data.get("source") or "user",
            status=data.get("status") or "active",
            tags=[str(tag) for tag in data.get("tags") or []],
            access_count=int(data.get("access_count") or 0),
            last_accessed=data.get("last_accessed"),
            expires_at=data.get("expires_at"),
            created_at=str(data.get("created_at") or utc_now()),
            updated_at=str(data.get("updated_at") or utc_now()),
        )


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _clamp(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))
