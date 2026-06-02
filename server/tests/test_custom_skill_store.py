from __future__ import annotations

import json

import pytest

from app.ai.custom_skill_store import (
    CustomSkillNotFoundError,
    CustomSkillStore,
    CustomSkillStoreError,
)
from app.ai.models import CustomSkillCreateRequest, CustomSkillUpdateRequest


def test_custom_skill_store_crud_persists_json_files(tmp_path) -> None:
    store = CustomSkillStore(tmp_path)

    skill = store.create(
        "user-1",
        CustomSkillCreateRequest(
            name="Triage",
            description="Review operator intent.",
            prompt="Classify command risk before execution.",
            inputSchema=[
                {
                    "name": "operator_intent",
                    "type": "string",
                    "required": True,
                    "description": "Raw operator command.",
                }
            ],
            enabled=True,
        ),
        created_by="user@example.test",
    )

    assert skill.source == "custom"
    assert skill.readonly is False
    assert skill.createdBy == "user@example.test"
    files = list(tmp_path.rglob("*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text(encoding="utf-8"))["name"] == "Triage"

    assert store.list("user-2") == []
    assert store.list("user-1")[0].id == skill.id

    updated = store.update(
        "user-1",
        skill.id,
        CustomSkillUpdateRequest(enabled=False, name="Risk triage"),
    )

    assert updated.enabled is False
    assert updated.name == "Risk triage"
    assert updated.prompt == "Classify command risk before execution."
    assert store.get("user-1", skill.id).enabled is False

    store.delete("user-1", skill.id)
    assert store.list("user-1") == []
    with pytest.raises(CustomSkillNotFoundError):
        store.get("user-1", skill.id)


def test_custom_skill_store_rejects_unsafe_skill_ids(tmp_path) -> None:
    store = CustomSkillStore(tmp_path)

    with pytest.raises(CustomSkillStoreError):
        store.get("user-1", "../escape")

    with pytest.raises(CustomSkillStoreError):
        store.delete("user-1", "bad.json")
