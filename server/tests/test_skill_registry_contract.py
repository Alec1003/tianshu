from __future__ import annotations

import pytest

from app.ai.skill_registry import TianShuSkillRegistry


class FakeRuntime:
    def _ok(self, **kwargs):
        return {"ok": True, **kwargs}

    def start_simulation(self):
        return self._ok()

    def pause_simulation(self):
        return self._ok()

    def stop_simulation(self):
        return self._ok()

    def reset_simulation(self):
        return self._ok()

    def step_simulation(self, steps: int = 1):
        return self._ok(steps=steps)

    def deploy_aircraft(self, **kwargs):
        return self._ok(**kwargs)

    def deploy_ship(self, **kwargs):
        return self._ok(**kwargs)

    def deploy_facility(self, **kwargs):
        return self._ok(**kwargs)

    def deploy_airbase(self, **kwargs):
        return self._ok(**kwargs)

    def deploy_obstacle(self, **kwargs):
        return self._ok(**kwargs)

    def deploy_reference_point(self, **kwargs):
        return self._ok(**kwargs)

    def delete_unit(self, **kwargs):
        return self._ok(**kwargs)

    def move_unit(self, **kwargs):
        return self._ok(**kwargs)

    def update_unit_state(self, **kwargs):
        return self._ok(**kwargs)

    def attack_unit(self, **kwargs):
        return self._ok(**kwargs)

    def update_weapon_quantity(self, **kwargs):
        return self._ok(**kwargs)

    def add_weapon_to_unit(self, **kwargs):
        return self._ok(**kwargs)

    def delete_weapon_from_unit(self, **kwargs):
        return self._ok(**kwargs)

    def create_patrol_mission(self, **kwargs):
        return self._ok(**kwargs)

    def update_patrol_mission(self, **kwargs):
        return self._ok(**kwargs)

    def create_strike_mission(self, **kwargs):
        return self._ok(**kwargs)

    def update_strike_mission(self, **kwargs):
        return self._ok(**kwargs)

    def delete_mission(self, **kwargs):
        return self._ok(**kwargs)

    def trigger_tactical_event(self, **kwargs):
        return self._ok(**kwargs)

    def update_situation_layer(self, **kwargs):
        return self._ok(**kwargs)

    def load_script(self, **kwargs):
        return self._ok(**kwargs)

    def execute_script_step(self):
        return self._ok()

    def control_script_flow(self, **kwargs):
        return self._ok(**kwargs)

    def load_scenario_from_json(self, scenario_json: str):
        return self._ok(scenario_json=scenario_json)

    def load_scenario_from_file(self, scenario_path: str):
        return self._ok(scenario_path=scenario_path)


def test_skill_definitions_are_user_readable_and_complete():
    registry = TianShuSkillRegistry(runtime=FakeRuntime())
    definitions = {definition.name: definition for definition in registry.definitions()}

    assert "deploy_obstacle" in definitions
    assert definitions["deploy_obstacle"].description == "部署仿真环境障碍或约束区域。"
    assert definitions["simulation_start"].description == "启动或继续当前仿真推演。"
    assert "oneOf" in definitions["load_script"].parameters["script"]

    descriptions = [definition.description for definition in definitions.values()]
    assert not any("�" in description for description in descriptions)
    assert not any("鍚" in description for description in descriptions)


def test_skill_registry_exposes_harness_capabilities():
    registry = TianShuSkillRegistry(runtime=FakeRuntime())

    capability_names = {capability.name for capability in registry.capabilities()}

    assert "simulation_step" in capability_names
    assert "deploy_aircraft" in capability_names
    assert registry.harness.get_capability("simulation_step").access == "control"
    assert registry.harness.get_capability("deploy_aircraft").access == "write"


def test_skill_registry_execute_routes_through_harness():
    registry = TianShuSkillRegistry(runtime=FakeRuntime())

    output = registry.execute(
        "simulation_step",
        {"steps": 9},
        source="test",
        actor_id="operator-1",
        scenario_id="scenario-1",
        request_id="request-1",
    )

    assert output == {"ok": True, "steps": 9}
    stats = registry.harness.stats("simulation_step")
    assert stats.usage_count == 1
    assert stats.last_source == "test"
    assert stats.last_actor_id == "operator-1"
    assert stats.last_scenario_id == "scenario-1"
    assert stats.last_request_id == "request-1"


def test_skill_registry_rejects_unknown_skill_before_execution():
    registry = TianShuSkillRegistry(runtime=FakeRuntime())

    with pytest.raises(ValueError, match="Skill not registered"):
        registry.execute("missing_skill", {})
