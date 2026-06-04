from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.ai.models import (
    CustomSkillCreateRequest,
    CustomSkillRead,
    CustomSkillUpdateRequest,
)
from app.config import get_settings

SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
logger = logging.getLogger(__name__)


class CustomSkillStoreError(ValueError):
    pass


class CustomSkillNotFoundError(CustomSkillStoreError):
    pass


def _now_iso() -> str:
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _safe_user_folder(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:32]


def _validate_skill_id(skill_id: str) -> str:
    normalized = skill_id.strip()
    if not SAFE_ID_RE.fullmatch(normalized):
        raise CustomSkillStoreError("Invalid custom skill id.")
    return normalized


class CustomSkillStore:
    """Folder-backed custom skills persistence.

    Custom prompt skills are app data, not executable Python modules. Files are
    scoped by authenticated user under one configured root folder so desktop/exe
    packaging can point the whole library at a writable directory.
    """

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir).expanduser().resolve()

    @classmethod
    def from_settings(cls) -> "CustomSkillStore":
        return cls(get_settings().skills_dir)

    def list(self, user_id: str) -> list[CustomSkillRead]:
        user_dir = self._user_dir(user_id)
        if not user_dir.exists():
            return []
        skills: list[CustomSkillRead] = []
        for path in sorted(user_dir.glob("*.json")):
            if path.name.startswith("."):
                continue
            try:
                with path.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
                skills.append(CustomSkillRead.model_validate(data))
            except (OSError, json.JSONDecodeError, ValidationError) as exc:
                logger.warning(
                    "custom_skill_store: skipping invalid custom skill file %s: %s",
                    path,
                    exc,
                )
        return skills

    def create(
        self,
        user_id: str,
        payload: CustomSkillCreateRequest,
        *,
        created_by: str = "",
    ) -> CustomSkillRead:
        now = _now_iso()
        skill = CustomSkillRead(
            id=self._new_skill_id(user_id),
            name=payload.name,
            description=payload.description,
            prompt=payload.prompt or payload.description,
            enabled=payload.enabled,
            inputSchema=payload.inputSchema,
            outputSchema=payload.outputSchema,
            createdBy=created_by,
            updatedAt=now,
        )
        self._write(user_id, skill)
        return skill

    def update(
        self,
        user_id: str,
        skill_id: str,
        payload: CustomSkillUpdateRequest,
    ) -> CustomSkillRead:
        skill = self.get(user_id, skill_id)
        changes = payload.model_dump(mode="json", exclude_unset=True)
        data = skill.model_dump(mode="json")
        for key, value in changes.items():
            if value is None:
                continue
            data[key] = value
        data["updatedAt"] = _now_iso()
        if not data.get("prompt"):
            data["prompt"] = data.get("description", "")
        skill = CustomSkillRead.model_validate(data)
        self._write(user_id, skill)
        return skill

    def delete(self, user_id: str, skill_id: str) -> None:
        path = self._skill_path(user_id, skill_id)
        if not path.exists():
            raise CustomSkillNotFoundError("Custom skill not found.")
        path.unlink()

    def get(self, user_id: str, skill_id: str) -> CustomSkillRead:
        path = self._skill_path(user_id, skill_id)
        if not path.exists():
            raise CustomSkillNotFoundError("Custom skill not found.")
        try:
            with path.open("r", encoding="utf-8") as handle:
                return CustomSkillRead.model_validate(json.load(handle))
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise CustomSkillStoreError("Invalid custom skill file.") from exc

    def _new_skill_id(self, user_id: str) -> str:
        while True:
            skill_id = f"skill-{uuid.uuid4().hex[:16]}"
            if not self._skill_path(user_id, skill_id).exists():
                return skill_id

    def _user_dir(self, user_id: str) -> Path:
        return self.root_dir / _safe_user_folder(str(user_id))

    def _skill_path(self, user_id: str, skill_id: str) -> Path:
        safe_id = _validate_skill_id(skill_id)
        path = (self._user_dir(user_id) / f"{safe_id}.json").resolve()
        user_dir = self._user_dir(user_id).resolve()
        if path.parent != user_dir:
            raise CustomSkillStoreError("Custom skill path escaped skills folder.")
        return path

    def _write(self, user_id: str, skill: CustomSkillRead) -> None:
        path = self._skill_path(user_id, skill.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = skill.model_dump(mode="json")
        temp_path = path.with_name(f".{path.stem}.{uuid.uuid4().hex}.tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
            temp_path.replace(path)
        finally:
            if temp_path.exists():
                temp_path.unlink()
