from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Keyword-based category mapping: keyword_prefix -> tool_name_patterns
_CATEGORY_KEYWORDS: list[tuple[list[str], list[str]]] = [
    (
        ["查询", "列出", "查看", "检查", "当前", "单位", "list", "get", "inspect", "show", "scenario", "态势", "状态"],
        ["inspect_current_scenario", "list_runtime_tools", "list_units", "get_unit_detail",
         "get_scenario", "get_scenario_statistics", "list_scenarios", "runtime_status",
         "runtime_export_scenario", "runtime_get_outcome", "query_threats"],
    ),
    (
        ["部署", "创建", "新增", "添加", "deploy", "create", "add", "new", "飞机", "舰船", "单位",
         "aircraft", "ship", "unit", "facility", "obstacle", "airbase"],
        ["deploy_aircraft", "deploy_ship", "deploy_facility", "deploy_obstacle",
         "deploy_airbase", "create_scenario", "list_units", "inspect_current_scenario"],
    ),
    (
        ["移动", "转移", "调整", "位置", "路线", "move", "reposition", "route", "set_position"],
        ["move_unit", "set_unit_position", "list_units", "inspect_current_scenario"],
    ),
    (
        ["攻击", "打击", "威胁", "武器", "attack", "strike", "threat", "weapon", "评估", "分析"],
        ["query_threats", "attack_unit", "create_strike_mission", "add_weapon",
         "inspect_current_scenario", "list_units"],
    ),
    (
        ["审批", "approve", "proposal", "计划", "方案", "plan", "战术", "tactical", "提案"],
        ["propose_tactical_plan_options", "list_command_proposals",
         "inspect_current_scenario", "list_runtime_tools"],
    ),
    (
        ["保存", "加载", "导出", "导入", "save", "load", "export", "import", "场景", "档案"],
        ["runtime_save_to_db", "runtime_load_scenario_from_db",
         "runtime_export_scenario", "inspect_current_scenario"],
    ),
    (
        ["删除", "移除", "清除", "delete", "remove", "clear", "destroy"],
        ["delete_unit", "delete_scenario", "delete_mission", "delete_weapon",
         "inspect_current_scenario", "list_units"],
    ),
    (
        ["推演", "仿真", "运行", "暂停", "开始", "重置", "步进", "sim", "run", "pause", "start", "reset", "step"],
        ["runtime_start", "runtime_pause", "runtime_reset", "runtime_step",
         "runtime_status", "inspect_current_scenario"],
    ),
    (
        ["文档", "资料", "doc", "document", "报告", "简报", "总结", "态势报告",
         "生成报告", "生成文档", "导出说明", "report", "brief", "summary"],
        ["doc-tools", "inspect_current_scenario", "list_runtime_tools"],
    ),
    (
        ["关系", "阵营", "编辑", "修改", "更新", "side", "edit", "update", "set", "relationship"],
        ["set_side_relationship", "update_side", "create_side",
         "inspect_current_scenario", "list_units"],
    ),
    (
        ["复盘", "AAR", "战报", "记录", "战绩", "统计", "评估", "outcome"],
        ["list_aar_records", "post_aar_record", "runtime_get_outcome",
         "get_scenario_statistics", "inspect_current_scenario"],
    ),
    (
        ["MCP", "外部工具", "external"],
        ["list_runtime_tools", "inspect_current_scenario"],
    ),
]

# Fallback tools always included regardless of matching
_ALWAYS_INCLUDE: set[str] = {"inspect_current_scenario", "list_runtime_tools"}


class DynamicCapabilitySelector:
    """Select a relevant subset of capabilities based on user query keywords."""

    @staticmethod
    def select(
        user_message: str,
        available_tools: list[str],
        chat_mode: str = "command",
    ) -> list[str]:
        if not user_message or not user_message.strip():
            return available_tools

        query_lower = user_message.strip().lower()
        selected: set[str] = set(_ALWAYS_INCLUDE)

        for keywords, tool_names in _CATEGORY_KEYWORDS:
            if any(kw in query_lower for kw in keywords):
                selected.update(tool_names)

        # Intersect with actually available tools
        available_set = set(available_tools)
        result = [t for t in selected if t in available_set]

        logger.info(
            "DynamicCapabilitySelector: query=%r selected=%d (from %d) => %s",
            user_message[:80],
            len(result),
            len(available_tools),
            result,
        )

        # Fallback: if only defaults (no category matched), return all
        if not result or set(result) == _ALWAYS_INCLUDE:
            logger.debug(
                "DynamicCapabilitySelector: no match, falling back to all %d tools",
                len(available_tools),
            )
            return available_tools

        return result


def last_user_message_text(messages: list[dict[str, Any]]) -> str:
    """Extract text from the last user message in a conversation."""
    for msg in reversed(messages):
        role = str(msg.get("role", "")).lower()
        if role == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = []
                for p in content:
                    if isinstance(p, dict):
                        t = p.get("text") or p.get("content") or ""
                        if isinstance(t, str):
                            parts.append(t)
                return " ".join(parts)
    return ""


__all__ = ["DynamicCapabilitySelector", "last_user_message_text"]
