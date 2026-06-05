from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.custom_skill_store import CustomSkillStore
from app.api.ai import router as ai_router
from app.auth.users import current_active_user


def _build_client(tmp_path) -> TestClient:
    app = FastAPI()
    app.state.custom_skill_store = CustomSkillStore(tmp_path)
    app.include_router(ai_router)
    app.dependency_overrides[current_active_user] = lambda: SimpleNamespace(
        id="user-1",
        email="operator@example.test",
        is_active=True,
    )
    return TestClient(app)


def test_custom_skills_api_crud_uses_folder_store(tmp_path) -> None:
    client = _build_client(tmp_path)

    initial = client.get("/api/ai/custom-skills")
    assert initial.status_code == 200
    assert initial.json()["skills"] == []

    created_response = client.post(
        "/api/ai/custom-skills",
        json={
            "name": "Strike planner",
            "description": "Prepare a strike planning checklist.",
            "prompt": "Build a concise strike planning checklist.",
            "inputSchema": [
                {
                    "name": "objective",
                    "type": "string",
                    "required": True,
                    "description": "Mission objective.",
                }
            ],
            "enabled": True,
        },
    )
    assert created_response.status_code == 201
    created = created_response.json()
    assert created["source"] == "custom"
    assert created["readonly"] is False
    assert created["createdBy"] == "operator@example.test"
    assert len(list(tmp_path.rglob("*.json"))) == 1

    listed = client.get("/api/ai/custom-skills").json()["skills"]
    assert [item["id"] for item in listed] == [created["id"]]

    updated_response = client.patch(
        f"/api/ai/custom-skills/{created['id']}",
        json={"enabled": False, "prompt": "Updated prompt."},
    )
    assert updated_response.status_code == 200
    updated = updated_response.json()
    assert updated["enabled"] is False
    assert updated["prompt"] == "Updated prompt."

    delete_response = client.delete(f"/api/ai/custom-skills/{created['id']}")
    assert delete_response.status_code == 204
    assert client.get("/api/ai/custom-skills").json()["skills"] == []


def test_custom_skills_api_rejects_missing_skill(tmp_path) -> None:
    client = _build_client(tmp_path)

    response = client.patch(
        "/api/ai/custom-skills/missing-skill",
        json={"enabled": False},
    )

    assert response.status_code == 404


def test_custom_skills_api_skips_invalid_skill_file(tmp_path) -> None:
    client = _build_client(tmp_path)
    created_response = client.post(
        "/api/ai/custom-skills",
        json={"name": "Valid", "description": "Valid skill."},
    )
    assert created_response.status_code == 201
    skill_id = created_response.json()["id"]
    skill_path = next(tmp_path.rglob(f"{skill_id}.json"))
    (skill_path.parent / "broken.json").write_text("{not-json", encoding="utf-8")

    response = client.get("/api/ai/custom-skills")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["skills"]] == [skill_id]
