from __future__ import annotations

from app.ai.skill_registry import AICCSkillRegistry


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
    registry = AICCSkillRegistry(runtime=FakeRuntime())
    definitions = {definition.name: definition for definition in registry.definitions()}

    assert "deploy_obstacle" in definitions
    assert definitions["deploy_obstacle"].description == "部署仿真环境障碍或约束区域。"
    assert definitions["simulation_start"].description == "启动或继续当前仿真推演。"
    assert "oneOf" in definitions["load_script"].parameters["script"]

    descriptions = [definition.description for definition in definitions.values()]
    assert not any("�" in description for description in descriptions)
    assert not any("鍚" in description for description in descriptions)
