from __future__ import annotations

import json
from pathlib import Path
from threading import RLock

from app.agent_runtime.memory.models import MemoryItem
from app.platform.paths import user_data_dir


class JsonMemoryStorage:
    """Small durable JSON store for Phase 5 memory."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or user_data_dir() / "agent_memory.json"
        self._lock = RLock()

    def list_items(self) -> list[MemoryItem]:
        with self._lock:
            return [MemoryItem.from_dict(item) for item in self._read()]

    def save_items(self, items: list[MemoryItem]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = [item.to_dict() for item in items]
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def _read(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []
