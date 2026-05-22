from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.ai.models import AgentExecutionSummary, SkillDefinition
from app.api.ai import router as ai_router
from app.auth.users import current_active_user


class _FakeSkillRegistry:
    def definitions(self) -> list[SkillDefinition]:
        return [
            SkillDefinition(
                name="simulation_pause",
                description="Pause the current simulation.",
            )
        ]


class _FakeBridge:
    skill_registry = _FakeSkillRegistry()

    async def process_command_async(
        self,
        command: str,
        context: dict | None = None,
    ) -> AgentExecutionSummary:
        return AgentExecutionSummary(command=command, decomposition=[command])

    def exported_scenario(self) -> dict:
        return {"currentScenario": {"id": "demo"}}


class _UserScopedFakeBridge(_FakeBridge):
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id

    def exported_scenario(self) -> dict:
        return {"currentScenario": {"id": f"demo:{self.user_id}"}}


class _FakeBridgeRegistry:
    def __init__(self) -> None:
        self.bridges: dict[str, _UserScopedFakeBridge] = {}

    def get_bridge_for_user(self, user) -> _UserScopedFakeBridge:
        user_id = str(user.id)
        bridge = self.bridges.get(user_id)
        if bridge is None:
            bridge = _UserScopedFakeBridge(user_id)
            self.bridges[user_id] = bridge
        return bridge


def _build_client(authenticated: bool = False) -> TestClient:
    app = FastAPI()
    app.state.bridge = _FakeBridge()
    app.include_router(ai_router)

    if authenticated:
        app.dependency_overrides[current_active_user] = lambda: SimpleNamespace(
            id="user-1",
            email="u@example.test",
            is_active=True,
        )

    return TestClient(app)


def _build_registry_client() -> tuple[TestClient, _FakeBridgeRegistry]:
    app = FastAPI()
    registry = _FakeBridgeRegistry()
    app.state.bridge_registry = registry
    app.include_router(ai_router)

    def _current_user(request: Request):
        user_id = request.headers.get("x-test-user", "user-1")
        return SimpleNamespace(
            id=user_id,
            email=f"{user_id}@example.test",
            is_active=True,
        )

    app.dependency_overrides[current_active_user] = _current_user
    return TestClient(app), registry


def test_ai_routes_reject_unauthenticated_requests() -> None:
    client = _build_client()

    cases = [
        ("get", "/api/ai/runtime/scenario", None),
        ("get", "/api/ai/skills", None),
        ("post", "/api/ai/command", {"command": "pause"}),
        (
            "post",
            "/api/ai/model/check",
            {"provider": "openai", "baseUrl": "https://example.test"},
        ),
        ("post", "/api/ai/chat", None),
    ]

    for method, path, body in cases:
        request = getattr(client, method)
        response = request(path, json=body) if body is not None else request(path)
        assert response.status_code == 401, path


def test_ai_command_and_runtime_work_for_authenticated_user() -> None:
    client = _build_client(authenticated=True)

    command_response = client.post("/api/ai/command", json={"command": "pause"})
    assert command_response.status_code == 200
    command_payload = command_response.json()
    assert command_payload["status"] == "ok"
    assert command_payload["scenario"] == {"currentScenario": {"id": "demo"}}

    runtime_response = client.get("/api/ai/runtime/scenario")
    assert runtime_response.status_code == 200
    assert runtime_response.json() == {"currentScenario": {"id": "demo"}}


def test_ai_runtime_uses_user_scoped_bridge_registry() -> None:
    client, registry = _build_registry_client()

    user_a_response = client.get(
        "/api/ai/runtime/scenario",
        headers={"x-test-user": "user-a"},
    )
    user_b_response = client.get(
        "/api/ai/runtime/scenario",
        headers={"x-test-user": "user-b"},
    )

    assert user_a_response.status_code == 200
    assert user_b_response.status_code == 200
    assert user_a_response.json() == {"currentScenario": {"id": "demo:user-a"}}
    assert user_b_response.json() == {"currentScenario": {"id": "demo:user-b"}}
    assert set(registry.bridges) == {"user-a", "user-b"}
