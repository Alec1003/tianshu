from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.ai.mcp_client import MCPClientSkeleton
from app.ai.models import AgentExecutionSummary, MCPCallTrace, SkillDefinition
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


class _FakeRuntime:
    def __init__(self, scenario_id: str = "demo") -> None:
        self.loaded_payload: str | None = None
        self.game = SimpleNamespace(
            scenario_paused=True,
            game_outcome={
                "ended": False,
                "winner_side_id": "",
                "reason": "",
                "ended_at": 0,
            },
            current_scenario=SimpleNamespace(
                id=scenario_id,
                start_time=100,
                current_time=100,
                duration=600,
                last_objective_destroyed=None,
            ),
        )

    def start_simulation(self) -> dict:
        self.game.scenario_paused = False
        return {"running": True}

    def pause_simulation(self) -> dict:
        self.game.scenario_paused = True
        return {"running": False}

    def reset_simulation(self) -> dict:
        self.game.scenario_paused = True
        self.game.current_scenario.current_time = self.game.current_scenario.start_time
        return {"reset": True}

    def step_simulation(self, steps: int = 1) -> dict:
        self.game.current_scenario.current_time += steps
        return {"steps": steps, "currentTime": self.game.current_scenario.current_time}

    def attack_unit(
        self,
        *,
        attacker_type: str,
        attacker_id: str,
        target_id: str,
        weapon_id: str = "",
        weapon_quantity: int = 1,
        auto: bool = False,
    ) -> dict:
        return {
            "attacked": True,
            "auto": auto,
            "attackerType": attacker_type,
            "attackerId": attacker_id,
            "targetId": target_id,
            "launched": [{"weaponId": weapon_id, "quantity": weapon_quantity}],
            "weaponCount": 1,
        }

    def add_weapon_to_unit(
        self,
        unit_type: str,
        unit_id: str,
        class_name: str,
        speed: float,
        max_fuel: float,
        fuel_rate: float,
        range_nm: float,
        lethality: float,
        quantity: int = 1,
    ) -> dict:
        return {
            "added": True,
            "unitType": unit_type,
            "unitId": unit_id,
            "weaponId": f"{class_name}:{quantity}",
        }

    def delete_weapon_from_unit(
        self, unit_type: str, unit_id: str, weapon_id: str
    ) -> dict:
        return {
            "deleted": True,
            "unitType": unit_type,
            "unitId": unit_id,
            "weaponId": weapon_id,
        }

    def update_weapon_quantity(
        self, unit_type: str, unit_id: str, weapon_id: str, increment: int
    ) -> dict:
        return {
            "updated": True,
            "unitType": unit_type,
            "unitId": unit_id,
            "weaponId": weapon_id,
            "currentQuantity": increment,
        }

    def load_scenario_from_json(self, scenario_json: str) -> dict:
        self.loaded_payload = scenario_json
        self.game.current_scenario.id = "loaded"
        return {"loaded": True}


class _FakeBridge:
    skill_registry = _FakeSkillRegistry()

    def __init__(self, scenario_id: str = "demo") -> None:
        self.runtime = _FakeRuntime(scenario_id)

    async def process_command_async(
        self,
        command: str,
        context: dict | None = None,
    ) -> AgentExecutionSummary:
        return AgentExecutionSummary(command=command, decomposition=[command])

    def exported_scenario(self) -> dict:
        return {"currentScenario": {"id": self.runtime.game.current_scenario.id}}


class _UserScopedFakeBridge(_FakeBridge):
    def __init__(self, user_id: str, scenario_id: str = "__default__") -> None:
        super().__init__(f"demo:{user_id}:{scenario_id}")
        self.user_id = user_id
        self.scenario_id = scenario_id

    def exported_scenario(self) -> dict:
        return {"currentScenario": {"id": self.runtime.game.current_scenario.id}}


class _FakeBridgeRegistry:
    def __init__(self) -> None:
        self.bridges: dict[tuple[str, str], _UserScopedFakeBridge] = {}

    def get_bridge_for_user(
        self,
        user,
        scenario_id: str | None = None,
    ) -> _UserScopedFakeBridge:
        user_id = str(user.id)
        context_id = scenario_id or "__default__"
        bridge_key = (user_id, context_id)
        bridge = self.bridges.get(bridge_key)
        if bridge is None:
            bridge = _UserScopedFakeBridge(user_id, context_id)
            self.bridges[bridge_key] = bridge
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
        ("get", "/api/ai/runtime", None),
        ("get", "/api/ai/runtime/timeline", None),
        ("get", "/api/ai/runtime/scenario", None),
        ("put", "/api/ai/runtime/scenario", {"scenario": {"currentScenario": {"id": "x"}}}),
        ("post", "/api/ai/runtime/start", None),
        ("post", "/api/ai/runtime/pause", None),
        ("post", "/api/ai/runtime/reset", None),
        ("post", "/api/ai/runtime/step", {"steps": 1}),
        (
            "post",
            "/api/ai/runtime/units",
            {
                "unit_type": "aircraft",
                "class_name": "F-35A Lightning II",
                "latitude": 0,
                "longitude": 0,
            },
        ),
        ("delete", "/api/ai/runtime/units/aircraft/a-1", None),
        (
            "patch",
            "/api/ai/runtime/units/route",
            {"unit_type": "aircraft", "unit_id": "a-1", "route": []},
        ),
        (
            "patch",
            "/api/ai/runtime/units/position",
            {
                "unit_type": "aircraft",
                "unit_id": "a-1",
                "latitude": 0,
                "longitude": 0,
            },
        ),
        (
            "patch",
            "/api/ai/runtime/side/current",
            {"side": "blue"},
        ),
        ("post", "/api/ai/runtime/sides", {"name": "BLUE", "color": "blue"}),
        (
            "patch",
            "/api/ai/runtime/sides/blue",
            {"name": "BLUE", "color": "blue"},
        ),
        ("delete", "/api/ai/runtime/sides/blue", None),
        ("delete", "/api/ai/runtime/missions/mission-1", None),
        (
            "post",
            "/api/ai/runtime/missions/patrol",
            {"name": "Patrol", "assigned_unit_ids": [], "reference_point_ids": []},
        ),
        (
            "patch",
            "/api/ai/runtime/missions/patrol/mission-1",
            {"name": "Patrol", "assigned_unit_ids": [], "reference_point_ids": []},
        ),
        (
            "post",
            "/api/ai/runtime/missions/strike",
            {"name": "Strike", "assigned_unit_ids": [], "assigned_target_ids": []},
        ),
        (
            "patch",
            "/api/ai/runtime/missions/strike/mission-1",
            {"name": "Strike", "assigned_unit_ids": [], "assigned_target_ids": []},
        ),
        (
            "post",
            "/api/ai/runtime/weapons",
            {
                "unit_type": "aircraft",
                "unit_id": "a-1",
                "class_name": "AIM-120 AMRAAM",
                "quantity": 1,
            },
        ),
        (
            "delete",
            "/api/ai/runtime/weapons",
            {
                "unit_type": "aircraft",
                "unit_id": "a-1",
                "weapon_id": "w-1",
            },
        ),
        (
            "patch",
            "/api/ai/runtime/weapons/quantity",
            {
                "unit_type": "aircraft",
                "unit_id": "a-1",
                "weapon_id": "w-1",
                "increment": 1,
            },
        ),
        (
            "post",
            "/api/ai/runtime/attack",
            {
                "attacker_type": "aircraft",
                "attacker_id": "a-1",
                "target_id": "t-1",
                "weapon_id": "w-1",
                "weapon_quantity": 1,
            },
        ),
        ("get", "/api/ai/skills", None),
        ("get", "/api/ai/custom-skills", None),
        (
            "post",
            "/api/ai/custom-skills",
            {"name": "Skill", "description": "desc", "prompt": "prompt"},
        ),
        ("patch", "/api/ai/custom-skills/skill-1", {"enabled": False}),
        ("delete", "/api/ai/custom-skills/skill-1", None),
        ("post", "/api/ai/command", {"command": "pause"}),
        ("get", "/api/ai/command/proposals", None),
        ("post", "/api/ai/command/proposals/proposal-1/approve", None),
        ("post", "/api/ai/command/proposals/proposal-1/reject", None),
        (
            "post",
            "/api/ai/internal-skills/proposals",
            {"draft": {"name": "CAP", "missions": []}},
        ),
        (
            "post",
            "/api/ai/model/check",
            {"provider": "openai", "baseUrl": "https://example.test"},
        ),
        (
            "post",
            "/api/ai/mcp/validate",
            {"name": "planner", "transport": "stdio", "command": "python"},
        ),
        ("post", "/api/ai/chat", None),
    ]

    for method, path, body in cases:
        if method == "delete" and body is not None:
            response = client.request("DELETE", path, json=body)
        else:
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


def test_validate_external_mcp_server_returns_tools_without_secrets(monkeypatch) -> None:
    client = _build_client(authenticated=True)
    captured = {}

    async def fake_list_tools(self, server_name=None):
        server = self.list_servers()[0]
        captured["server"] = server
        return (
            [
                MCPCallTrace(
                    action="list_tools",
                    target=server_name or server.name,
                    status="ok",
                    message="1 tools available",
                )
            ],
            [
                {
                    "server": server.name,
                    "name": "plan_route",
                    "description": "Plan a route.",
                    "inputSchema": {"type": "object"},
                }
            ],
        )

    monkeypatch.setattr(MCPClientSkeleton, "list_tools", fake_list_tools)

    response = client.post(
        "/api/ai/mcp/validate",
        json={
            "name": "planner",
            "transport": "stdio",
            "endpoint": "python -m planner_mcp",
            "env": {"PLANNER_TOKEN": "secret"},
            "headers": {"Authorization": "Bearer secret"},
            "timeoutSeconds": 60,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["transport"] == "stdio"
    assert payload["tools"][0]["name"] == "plan_route"
    assert "secret" not in response.text
    server = captured["server"]
    assert server.command == "python"
    assert server.args == ["-m", "planner_mcp"]
    assert server.timeout_seconds == 15.0


def test_ai_runtime_control_endpoints_return_authoritative_snapshot() -> None:
    client = _build_client(authenticated=True)

    start_response = client.post("/api/ai/runtime/start")
    assert start_response.status_code == 200
    start_payload = start_response.json()
    assert start_payload["action"] == "start"
    assert start_payload["running"] is True
    assert start_payload["paused"] is False
    assert start_payload["scenario"] == {"currentScenario": {"id": "demo"}}

    step_response = client.post("/api/ai/runtime/step", json={"steps": 3})
    assert step_response.status_code == 200
    step_payload = step_response.json()
    assert step_payload["action"] == "step"
    assert step_payload["current_time"] == 103
    assert step_payload["elapsed"] == 3
    assert step_payload["duration_left"] == 597
    assert step_payload["state"] == {"steps": 3, "currentTime": 103}

    pause_response = client.post("/api/ai/runtime/pause")
    assert pause_response.status_code == 200
    assert pause_response.json()["paused"] is True

    reset_response = client.post("/api/ai/runtime/reset")
    assert reset_response.status_code == 200
    reset_payload = reset_response.json()
    assert reset_payload["action"] == "reset"
    assert reset_payload["current_time"] == 100

    load_response = client.put(
        "/api/ai/runtime/scenario",
        json={"scenario": {"currentScenario": {"id": "loaded"}}},
    )
    assert load_response.status_code == 200
    load_payload = load_response.json()
    assert load_payload["action"] == "load_scenario"
    assert load_payload["scenario"] == {"currentScenario": {"id": "loaded"}}

    attack_response = client.post(
        "/api/ai/runtime/attack",
        json={
            "attacker_type": "aircraft",
            "attacker_id": "aircraft-1",
            "target_id": "target-1",
            "weapon_id": "weapon-1",
            "weapon_quantity": 2,
        },
    )
    assert attack_response.status_code == 200
    attack_payload = attack_response.json()
    assert attack_payload["action"] == "attack"
    assert attack_payload["state"] == {
        "attacked": True,
        "auto": False,
        "attackerType": "aircraft",
        "attackerId": "aircraft-1",
        "targetId": "target-1",
        "launched": [{"weaponId": "weapon-1", "quantity": 2}],
        "weaponCount": 1,
    }

    add_weapon_response = client.post(
        "/api/ai/runtime/weapons",
        json={
            "unit_type": "aircraft",
            "unit_id": "aircraft-1",
            "class_name": "AIM-120 AMRAAM",
            "quantity": 2,
        },
    )
    assert add_weapon_response.status_code == 200
    assert add_weapon_response.json()["action"] == "add_weapon"

    update_weapon_response = client.patch(
        "/api/ai/runtime/weapons/quantity",
        json={
            "unit_type": "aircraft",
            "unit_id": "aircraft-1",
            "weapon_id": "weapon-1",
            "increment": -1,
        },
    )
    assert update_weapon_response.status_code == 200
    assert update_weapon_response.json()["action"] == "update_weapon_quantity"

    delete_weapon_response = client.request(
        "DELETE",
        "/api/ai/runtime/weapons",
        json={
            "unit_type": "aircraft",
            "unit_id": "aircraft-1",
            "weapon_id": "weapon-1",
        },
    )
    assert delete_weapon_response.status_code == 200
    assert delete_weapon_response.json()["action"] == "delete_weapon"


def test_ai_runtime_step_rejects_invalid_step_count() -> None:
    client = _build_client(authenticated=True)

    too_large = client.post("/api/ai/runtime/step", json={"steps": 7201})
    assert too_large.status_code == 422


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
    assert user_a_response.json() == {
        "currentScenario": {"id": "demo:user-a:__default__"}
    }
    assert user_b_response.json() == {
        "currentScenario": {"id": "demo:user-b:__default__"}
    }
    assert set(registry.bridges) == {
        ("user-a", "__default__"),
        ("user-b", "__default__"),
    }


def test_ai_runtime_uses_scenario_scoped_bridge_registry() -> None:
    client, registry = _build_registry_client()

    alpha_response = client.get(
        "/api/ai/runtime/scenario",
        headers={"x-test-user": "user-a", "x-tianshu-scenario-id": "alpha"},
    )
    bravo_response = client.get(
        "/api/ai/runtime/scenario",
        headers={"x-test-user": "user-a", "x-tianshu-scenario-id": "bravo"},
    )

    assert alpha_response.status_code == 200
    assert bravo_response.status_code == 200
    assert alpha_response.json() == {"currentScenario": {"id": "demo:user-a:alpha"}}
    assert bravo_response.json() == {"currentScenario": {"id": "demo:user-a:bravo"}}
    assert set(registry.bridges) == {("user-a", "alpha"), ("user-a", "bravo")}
