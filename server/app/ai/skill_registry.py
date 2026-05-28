from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.ai.models import SkillDefinition
from app.aicc_runtime.runtime import AICCRuntime


SkillFunc = Callable[..., dict[str, Any]]


@dataclass
class RegisteredSkill:
    name: str
    description: str
    parameters: dict[str, Any]
    func: SkillFunc

    def as_definition(self) -> SkillDefinition:
        return SkillDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )


class AICCSkillRegistry:
    """Skill registry for mapping AI tool calls to native AICC runtime APIs."""

    def __init__(self, runtime: AICCRuntime) -> None:
        self.runtime = runtime
        self._skills: dict[str, RegisteredSkill] = {}
        self._register_all()

    def _register(self, skill: RegisteredSkill) -> None:
        self._skills[skill.name] = skill

    def _register_all(self) -> None:
        # --------------------------- simulation lifecycle skills ---------------------------
        self._register(
            RegisteredSkill(
                name="simulation_start",
                description="启动或继续当前仿真推演。",
                parameters={},
                func=self.runtime.start_simulation,
            )
        )
        self._register(
            RegisteredSkill(
                name="simulation_pause",
                description="暂停当前仿真推演。",
                parameters={},
                func=self.runtime.pause_simulation,
            )
        )
        self._register(
            RegisteredSkill(
                name="simulation_stop",
                description="停止仿真并恢复到初始状态。",
                parameters={},
                func=self.runtime.stop_simulation,
            )
        )
        self._register(
            RegisteredSkill(
                name="simulation_reset",
                description="重置当前仿真状态。",
                parameters={},
                func=self.runtime.reset_simulation,
            )
        )
        self._register(
            RegisteredSkill(
                name="simulation_step",
                description="按指定步数推进后端权威仿真。",
                parameters={"steps": {"type": "integer", "default": 1}},
                func=self.runtime.step_simulation,
            )
        )

        # --------------------------- unit control skills ---------------------------
        self._register(
            RegisteredSkill(
                name="deploy_aircraft",
                description="在指定经纬度部署飞机单位。",
                parameters={
                    "class_name": {"type": "string"},
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                    "side": {"type": "string", "required": False},
                    "name": {"type": "string", "required": False},
                },
                func=self.runtime.deploy_aircraft,
            )
        )
        self._register(
            RegisteredSkill(
                name="deploy_ship",
                description="在指定经纬度部署舰艇单位。",
                parameters={
                    "class_name": {"type": "string"},
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                    "side": {"type": "string", "required": False},
                    "name": {"type": "string", "required": False},
                },
                func=self.runtime.deploy_ship,
            )
        )
        self._register(
            RegisteredSkill(
                name="deploy_facility",
                description="在指定经纬度部署地面设施单位。",
                parameters={
                    "class_name": {"type": "string"},
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                    "side": {"type": "string", "required": False},
                    "name": {"type": "string", "required": False},
                },
                func=self.runtime.deploy_facility,
            )
        )
        self._register(
            RegisteredSkill(
                name="deploy_airbase",
                description="在指定经纬度部署机场或空军基地。",
                parameters={
                    "class_name": {"type": "string"},
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                    "side": {"type": "string", "required": False},
                    "name": {"type": "string", "required": False},
                },
                func=self.runtime.deploy_airbase,
            )
        )
        self._register(
            RegisteredSkill(
                name="deploy_obstacle",
                description="部署仿真环境障碍或约束区域。",
                parameters={
                    "class_name": {"type": "string"},
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                    "side": {"type": "string", "required": False},
                    "name": {"type": "string", "required": False},
                    "radius_nm": {"type": "number", "required": False},
                    "obstacle_type": {"type": "string", "required": False},
                    "movement_penalty": {"type": "number", "required": False},
                    "detection_penalty": {"type": "number", "required": False},
                    "communication_penalty": {"type": "number", "required": False},
                    "affected_domains": {"type": "array", "required": False},
                },
                func=self.runtime.deploy_obstacle,
            )
        )
        self._register(
            RegisteredSkill(
                name="deploy_reference_point",
                description="新增地图参考点或航路点。",
                parameters={
                    "name": {"type": "string"},
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                    "side": {"type": "string", "required": False},
                },
                func=self.runtime.deploy_reference_point,
            )
        )
        self._register(
            RegisteredSkill(
                name="delete_unit",
                description="删除指定仿真单位。",
                parameters={
                    "unit_type": {"type": "string"},
                    "unit_id": {"type": "string"},
                },
                func=self.runtime.delete_unit,
            )
        )
        self._register(
            RegisteredSkill(
                name="move_unit",
                description="为飞机或舰艇设置机动航线。",
                parameters={
                    "unit_type": {"type": "string", "enum": ["aircraft", "ship"]},
                    "unit_id": {"type": "string"},
                    "route": {"type": "array"},
                },
                func=self.runtime.move_unit,
            )
        )
        self._register(
            RegisteredSkill(
                name="update_unit_state",
                description="更新指定单位的状态或参数。",
                parameters={
                    "unit_type": {"type": "string"},
                    "unit_id": {"type": "string"},
                    "patch": {"type": "object"},
                },
                func=self.runtime.update_unit_state,
            )
        )

        # --------------------------- situation and event skills ---------------------------
        self._register(
            RegisteredSkill(
                name="trigger_tactical_event",
                description="触发指定战术事件。",
                parameters={
                    "event_name": {"type": "string"},
                    "payload": {"type": "object", "required": False},
                },
                func=self.runtime.trigger_tactical_event,
            )
        )
        self._register(
            RegisteredSkill(
                name="update_situation_layer",
                description="更新态势图层，例如参考点或障碍区域。",
                parameters={
                    "layer_name": {"type": "string"},
                    "operation": {"type": "string"},
                    "payload": {"type": "object", "required": False},
                },
                func=self.runtime.update_situation_layer,
            )
        )

        # --------------------------- scripted playback skills ---------------------------
        self._register(
            RegisteredSkill(
                name="load_script",
                description="加载脚本化推演动作序列。",
                parameters={
                    "script": {
                        "oneOf": [
                            {"type": "array", "items": {"type": "string"}},
                            {"type": "string"},
                        ]
                    }
                },
                func=self.runtime.load_script,
            )
        )
        self._register(
            RegisteredSkill(
                name="execute_script_step",
                description="执行当前脚本的下一步动作。",
                parameters={},
                func=self.runtime.execute_script_step,
            )
        )
        self._register(
            RegisteredSkill(
                name="control_script_flow",
                description="控制脚本流程，支持 pause、resume、reset。",
                parameters={"action": {"type": "string"}},
                func=self.runtime.control_script_flow,
            )
        )
        self._register(
            RegisteredSkill(
                name="load_scenario_snapshot",
                description="加载已授权的想定 JSON 快照。",
                parameters={
                    "scenario_json": {"type": "string"},
                    "scenario_id": {"type": "string", "required": False},
                    "name": {"type": "string", "required": False},
                },
                func=self._load_scenario_snapshot,
            )
        )
        self._register(
            RegisteredSkill(
                name="load_scenario_file",
                description="从服务端文件路径加载想定文件。",
                parameters={"scenario_path": {"type": "string"}},
                func=self.runtime.load_scenario_from_file,
            )
        )
        self._register(
            RegisteredSkill(
                name="load_scenario_json",
                description="加载完整想定 JSON 文本。",
                parameters={"scenario_json": {"type": "string"}},
                func=self.runtime.load_scenario_from_json,
            )
        )

    def definitions(self) -> list[SkillDefinition]:
        return [skill.as_definition() for skill in self._skills.values()]

    def has_skill(self, skill_name: str) -> bool:
        return skill_name in self._skills

    def _load_scenario_snapshot(
        self,
        scenario_json: str,
        scenario_id: str = "",
        name: str = "",
    ) -> dict[str, Any]:
        state = self.runtime.load_scenario_from_json(scenario_json)
        return {
            **state,
            "scenarioId": scenario_id,
            "name": name,
        }

    def execute(self, skill_name: str, parameters: dict[str, Any]) -> dict[str, Any]:
        if skill_name not in self._skills:
            raise ValueError(f"Skill not registered: {skill_name}")
        skill = self._skills[skill_name]
        return skill.func(**parameters)
