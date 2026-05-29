from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.ai.mcp_client import MCPClientSkeleton
from app.ai.models import AgentExecutionSummary, SkillExecutionResult
from app.ai.openclaw_sdk_adapter import OpenClawSDKAdapter
from app.ai.skill_registry import AICCSkillRegistry


UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
NON_ACTION_CHAT_RE = re.compile(
    r"^\s*(hi|hello|hey|help|what can you do|commands?)\s*[!.?]*\s*$",
    flags=re.I,
)
QUOTED_RE = re.compile(r"[\"'“”]([^\"'“”]+)[\"'“”]")


@dataclass
class PlannedSkillCall:
    name: str
    parameters: dict[str, Any]
    source_text: str


class AICCCommanderAgent:
    """天枢平台指挥智能体（OpenClaw 嵌入式适配层）。"""

    SYSTEM_PROMPT = """
你是天枢平台指挥智能体。你的任务：
1) 解析自然语言作战控制指令
2) 识别意图并提取参数
3) 映射到已注册 Skill
4) 支持批量执行与复杂指令拆解

约束：
- 只调用已注册 Skill
- 参数尽量结构化
- 无法解析时返回明确错误
- 保留后续错误恢复与审计扩展位
""".strip()

    def __init__(
        self,
        skill_registry: AICCSkillRegistry,
        mcp_client: MCPClientSkeleton,
        sdk_adapter: OpenClawSDKAdapter | None = None,
    ) -> None:
        self.skill_registry = skill_registry
        self.mcp_client = mcp_client
        self.sdk_adapter = sdk_adapter

    def process_command(
        self, command: str, context: dict[str, Any] | None = None
    ) -> AgentExecutionSummary:
        summary = AgentExecutionSummary(command=command)
        summary.decomposition = self._decompose(command)
        planned_calls = self.plan_command(command)

        if not planned_calls:
            summary.status = "error"
            summary.error = self._build_no_skill_message(command)
            return summary

        has_error = False
        for call in planned_calls:
            try:
                output = self.skill_registry.execute(call.name, call.parameters)
                summary.skill_calls.append(
                    SkillExecutionResult(
                        skill=call.name,
                        status="ok",
                        parameters=call.parameters,
                        output=output,
                    )
                )
            except Exception as exc:
                has_error = True
                summary.skill_calls.append(
                    SkillExecutionResult(
                        skill=call.name,
                        status="error",
                        parameters=call.parameters,
                        error=str(exc),
                    )
                )

        if has_error and summary.skill_calls:
            summary.status = "partial"
        elif has_error:
            summary.status = "error"
        else:
            summary.status = "ok"
        return summary

    def plan_command(self, command: str) -> list[PlannedSkillCall]:
        """Convert natural language into structured skill calls without executing."""
        planned_calls: list[PlannedSkillCall] = []

        sdk_calls = self._plan_with_sdk(command)
        if sdk_calls:
            planned_calls.extend(sdk_calls)

        for segment in self._decompose(command):
            planned_calls.extend(self._plan_segment(segment))

        return planned_calls

    def _plan_with_sdk(self, command: str) -> list[PlannedSkillCall]:
        if self.sdk_adapter is None:
            return []
        sdk_plan = self.sdk_adapter.plan_skill_calls(
            system_prompt=self.SYSTEM_PROMPT,
            command=command,
            skill_definitions=self.skill_registry.definitions(),
        )
        if not sdk_plan:
            return []
        calls: list[PlannedSkillCall] = []
        for item in sdk_plan:
            name = str(item.get("name", "")).strip()
            params = item.get("parameters", {})
            if not name or not isinstance(params, dict):
                continue
            if self.skill_registry.has_skill(name):
                calls.append(
                    PlannedSkillCall(name=name, parameters=params, source_text=command)
                )
        return calls

    def _decompose(self, command: str) -> list[str]:
        parts = re.split(r"(?:\n|;|；|然后|并且| and then | then )", command, flags=re.I)
        normalized = [part.strip() for part in parts if part and part.strip()]
        return normalized if normalized else [command.strip()]

    def _plan_segment(self, text: str) -> list[PlannedSkillCall]:
        text_norm = text.strip()
        text_l = text_norm.lower()
        calls: list[PlannedSkillCall] = []

        # ---------------------- OpenClaw SDK扩展区（嵌入模式） ----------------------
        # If your in-process OpenClaw SDK becomes available, add planning logic here
        # to replace/augment the rule planner below.
        # -------------------------------------------------------------------------

        # 仿真生命周期
        if any(keyword in text_l for keyword in ["启动", "开始", "继续", "start", "resume"]):
            calls.append(
                PlannedSkillCall("simulation_start", {}, source_text=text_norm)
            )
        if any(keyword in text_l for keyword in ["暂停", "pause"]):
            calls.append(
                PlannedSkillCall("simulation_pause", {}, source_text=text_norm)
            )
        if any(keyword in text_l for keyword in ["停止", "终止", "stop"]):
            calls.append(PlannedSkillCall("simulation_stop", {}, source_text=text_norm))
        if any(keyword in text_l for keyword in ["重置", "reset"]):
            calls.append(
                PlannedSkillCall("simulation_reset", {}, source_text=text_norm)
            )
        if any(keyword in text_l for keyword in ["单步", "推演", "step"]):
            calls.append(
                PlannedSkillCall(
                    "simulation_step",
                    {"steps": self._extract_steps(text_norm)},
                    source_text=text_norm,
                )
            )

        # 剧本控制
        if any(keyword in text_l for keyword in ["加载剧本", "load script"]):
            script_data = self._extract_json_array(text_norm)
            if script_data is not None:
                calls.append(
                    PlannedSkillCall(
                        "load_script", {"script": script_data}, source_text=text_norm
                    )
                )
        if any(keyword in text_l for keyword in ["剧本下一步", "script step"]):
            calls.append(
                PlannedSkillCall("execute_script_step", {}, source_text=text_norm)
            )
        if any(keyword in text_l for keyword in ["剧本暂停", "script pause"]):
            calls.append(
                PlannedSkillCall(
                    "control_script_flow",
                    {"action": "pause"},
                    source_text=text_norm,
                )
            )
        if any(keyword in text_l for keyword in ["剧本继续", "script resume"]):
            calls.append(
                PlannedSkillCall(
                    "control_script_flow",
                    {"action": "resume"},
                    source_text=text_norm,
                )
            )

        # 部署
        if any(keyword in text_l for keyword in ["部署", "添加", "deploy", "add"]):
            unit_type = self._detect_unit_type(text_l)
            side = self._extract_side(text_l)
            lat, lon = self._extract_coordinates(text_norm, default=(0.0, 0.0))
            class_name = self._extract_class_name(text_norm, unit_type)

            if unit_type == "aircraft":
                calls.append(
                    PlannedSkillCall(
                        "deploy_aircraft",
                        {
                            "class_name": class_name,
                            "latitude": lat,
                            "longitude": lon,
                            "side": side,
                        },
                        source_text=text_norm,
                    )
                )
            elif unit_type == "ship":
                calls.append(
                    PlannedSkillCall(
                        "deploy_ship",
                        {
                            "class_name": class_name,
                            "latitude": lat,
                            "longitude": lon,
                            "side": side,
                        },
                        source_text=text_norm,
                    )
                )
            elif unit_type == "facility":
                calls.append(
                    PlannedSkillCall(
                        "deploy_facility",
                        {
                            "class_name": class_name,
                            "latitude": lat,
                            "longitude": lon,
                            "side": side,
                        },
                        source_text=text_norm,
                    )
                )
            elif unit_type == "airbase":
                calls.append(
                    PlannedSkillCall(
                        "deploy_airbase",
                        {
                            "class_name": class_name,
                            "latitude": lat,
                            "longitude": lon,
                            "side": side,
                        },
                        source_text=text_norm,
                    )
                )
            elif unit_type == "obstacle":
                calls.append(
                    PlannedSkillCall(
                        "deploy_obstacle",
                        {
                            "class_name": class_name,
                            "latitude": lat,
                            "longitude": lon,
                            "side": side,
                            "radius_nm": self._extract_radius_nm(text_norm),
                            "obstacle_type": self._detect_obstacle_type(text_l),
                        },
                        source_text=text_norm,
                    )
                )
            elif unit_type == "reference_point":
                calls.append(
                    PlannedSkillCall(
                        "deploy_reference_point",
                        {
                            "name": class_name or "Reference Point",
                            "latitude": lat,
                            "longitude": lon,
                            "side": side,
                        },
                        source_text=text_norm,
                    )
                )

        # 删除
        if any(keyword in text_l for keyword in ["删除", "移除", "delete", "remove"]):
            unit_type = self._detect_unit_type(text_l)
            unit_id = self._extract_uuid(text_norm)
            if unit_type and unit_id:
                calls.append(
                    PlannedSkillCall(
                        "delete_unit",
                        {"unit_type": unit_type, "unit_id": unit_id},
                        source_text=text_norm,
                    )
                )

        # 机动
        if any(keyword in text_l for keyword in ["机动", "移动", "move"]):
            unit_type = self._detect_unit_type(text_l)
            unit_id = self._extract_uuid(text_norm)
            lat, lon = self._extract_coordinates(text_norm, default=(None, None))
            if unit_type in {"aircraft", "ship"} and unit_id and lat is not None and lon is not None:
                calls.append(
                    PlannedSkillCall(
                        "move_unit",
                        {
                            "unit_type": unit_type,
                            "unit_id": unit_id,
                            "route": [[lat, lon]],
                        },
                        source_text=text_norm,
                    )
                )

        # 状态更新
        if any(keyword in text_l for keyword in ["状态", "修改", "update"]):
            unit_type = self._detect_unit_type(text_l)
            unit_id = self._extract_uuid(text_norm)
            patch = self._extract_patch(text_norm)
            if unit_type and unit_id and patch:
                calls.append(
                    PlannedSkillCall(
                        "update_unit_state",
                        {"unit_type": unit_type, "unit_id": unit_id, "patch": patch},
                        source_text=text_norm,
                    )
                )

        # 战术事件 / 图层
        if any(keyword in text_l for keyword in ["事件", "event", "触发"]):
            event_name = self._extract_event_name(text_norm)
            calls.append(
                PlannedSkillCall(
                    "trigger_tactical_event",
                    {"event_name": event_name, "payload": {}},
                    source_text=text_norm,
                )
            )
        if any(keyword in text_l for keyword in ["图层", "layer", "态势"]):
            operation = "add" if any(
                keyword in text_l for keyword in ["添加", "新增", "add"]
            ) else "update"
            layer_name = (
                "reference_points"
                if any(keyword in text_l for keyword in ["参考点", "reference"])
                else "situation"
            )
            lat, lon = self._extract_coordinates(text_norm, default=(0.0, 0.0))
            payload = {"latitude": lat, "longitude": lon, "name": "AI-Layer-Point"}
            calls.append(
                PlannedSkillCall(
                    "update_situation_layer",
                    {
                        "layer_name": layer_name,
                        "operation": operation,
                        "payload": payload,
                    },
                    source_text=text_norm,
                )
            )

        # 场景加载（文件）
        if any(keyword in text_l for keyword in ["加载场景", "load scenario"]):
            quoted = self._extract_quoted(text_norm)
            if quoted:
                calls.append(
                    PlannedSkillCall(
                        "load_scenario_file",
                        {"scenario_path": quoted},
                        source_text=text_norm,
                    )
                )

        return calls

    @staticmethod
    def _extract_steps(text: str) -> int:
        match = re.search(r"(\d+)\s*(?:步|step)", text, flags=re.I)
        if match:
            return max(1, int(match.group(1)))
        return 1

    @staticmethod
    def _extract_uuid(text: str) -> str | None:
        match = UUID_RE.search(text)
        return match.group(0) if match else None

    @staticmethod
    def _extract_side(text: str) -> str | None:
        if any(keyword in text for keyword in ["蓝", "blue"]):
            return "BLUE"
        if any(keyword in text for keyword in ["红", "red"]):
            return "RED"
        if any(keyword in text for keyword in ["盟", "ally"]):
            return "ALLY"
        return None

    @staticmethod
    def _detect_unit_type(text: str) -> str | None:
        if any(keyword in text for keyword in ["加油机", "飞机", "aircraft", "plane"]):
            return "aircraft"
        if any(keyword in text for keyword in ["舰", "ship"]):
            return "ship"
        if any(
            keyword in text
            for keyword in ["障碍", "禁行", "禁飞", "地形", "天气", "遮蔽", "obstacle"]
        ):
            return "obstacle"
        if any(keyword in text for keyword in ["设施", "雷达", "sam", "facility"]):
            return "facility"
        if any(keyword in text for keyword in ["机场", "airbase", "基地"]):
            return "airbase"
        if any(keyword in text for keyword in ["参考点", "reference"]):
            return "reference_point"
        return None

    @staticmethod
    def _detect_obstacle_type(text: str) -> str:
        if any(keyword in text for keyword in ["禁飞", "禁行", "no-go", "no_go"]):
            return "no_go"
        if any(keyword in text for keyword in ["地形", "terrain"]):
            return "terrain"
        if any(keyword in text for keyword in ["天气", "weather"]):
            return "weather"
        if any(keyword in text for keyword in ["遮蔽", "雷达盲区", "sensor"]):
            return "sensor_shadow"
        return "no_go"

    @staticmethod
    def _extract_radius_nm(text: str) -> float:
        match = re.search(
            r"(?:半径|radius)\D*(\d+(?:\.\d+)?)\s*(?:nm|海里)?",
            text,
            flags=re.I,
        )
        return float(match.group(1)) if match else 15.0

    @staticmethod
    def _extract_quoted(text: str) -> str | None:
        match = QUOTED_RE.search(text)
        if not match:
            return None
        return match.group(1).strip()

    def _extract_class_name(self, text: str, unit_type: str | None) -> str:
        quoted = self._extract_quoted(text)
        if quoted:
            return quoted
        defaults = {
            "aircraft": "F-16C",
            "ship": "Destroyer",
            "facility": "MIM-104 Patriot",
            "airbase": "Andersen Air Force Base",
            "reference_point": "Reference Point",
            "obstacle": "No-go zone",
        }
        if unit_type == "aircraft" and "加油机" in text:
            return "KC-135R Stratotanker"
        return defaults.get(unit_type or "", "Unknown")

    @staticmethod
    def _extract_coordinates(
        text: str, default: tuple[float | None, float | None] = (None, None)
    ) -> tuple[float | None, float | None]:
        numbers = NUMBER_RE.findall(text)
        if len(numbers) >= 2:
            return float(numbers[0]), float(numbers[1])
        return default

    @staticmethod
    def _extract_patch(text: str) -> dict[str, Any]:
        patch: dict[str, Any] = {}
        speed_match = re.search(r"(?:速度|speed)\D*(-?\d+(?:\.\d+)?)", text, flags=re.I)
        fuel_match = re.search(
            r"(?:油量|fuel)\D*(-?\d+(?:\.\d+)?)", text, flags=re.I
        )
        range_match = re.search(
            r"(?:航程|探测范围|range)\D*(-?\d+(?:\.\d+)?)", text, flags=re.I
        )
        name_match = QUOTED_RE.search(text)
        if speed_match:
            patch["speed"] = float(speed_match.group(1))
        if fuel_match:
            patch["current_fuel"] = float(fuel_match.group(1))
        if range_match:
            patch["range"] = float(range_match.group(1))
        if name_match:
            patch["name"] = name_match.group(1)
        return patch

    @staticmethod
    def _extract_json_array(text: str) -> list[str] | None:
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            raw = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
        if not isinstance(raw, list):
            return None
        return [str(item) for item in raw]

    @staticmethod
    def _extract_event_name(text: str) -> str:
        quoted = QUOTED_RE.search(text)
        if quoted:
            return quoted.group(1)
        return "custom_action"

    def _build_no_skill_message(self, command: str) -> str:
        if NON_ACTION_CHAT_RE.match(command.strip()):
            return (
                "I can execute 天枢平台 control skills. Try one of these commands:\n"
                "1) start simulation\n"
                "2) step simulation 3 steps\n"
                "3) deploy BLUE aircraft F-16 at 22.1 121.5\n"
                "4) pause simulation"
            )
        return (
            "No executable skill identified from command. Try commands like:\n"
            "1) start simulation\n"
            "2) step simulation 3 steps\n"
            "3) deploy BLUE aircraft F-16 at 22.1 121.5\n"
            "4) pause simulation"
        )
