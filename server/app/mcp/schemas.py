"""Pydantic v2 input/output models for MCP tools.

为什么把 schema 抽出来：
- FastMCP 会从函数签名自动生成 JSON schema 给 LLM，因此每个公共字段必须
  有明确类型和 docstring（pyd 技能"公共边界默认有类型"）。
- 结构化输出（return type 是 BaseModel）让客户端自动 validate，模型不会
  拿到漂移的字段（api 反例 8 "OpenAPI 与真实返回不一致"）。
- 错误模型走 ``ToolError`` 稳定 code + retryable + details（api 反例 3）。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------- Common --------------------------------------------------------


class ToolError(BaseModel):
    """Stable error envelope returned by write tools when business rules
    reject the request. Read tools also use this for consistent shape.

    LLM 客户端应只解析 ``code`` 字段做分支；``message`` 仅用于展示。
    """

    ok: Literal[False] = False
    code: str = Field(..., description="稳定业务码：scenario_not_found / forbidden / invalid / ...")
    message: str = Field(..., description="人类可读的错误描述，禁止据此做分支判断")
    retryable: bool = Field(default=False, description="瞬时故障，客户端可在退避后重试")
    details: dict[str, Any] = Field(default_factory=dict, description="结构化补充信息")


# ---------- Scenario projections -----------------------------------------


class ScenarioSummary(BaseModel):
    """轻量 scenario 元信息，列表场景使用，不带巨型 ``data``。"""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    description: str = ""
    is_template: bool
    owner_id: uuid.UUID | None = None
    version: int = 1
    status: str = "draft"
    created_at: datetime
    updated_at: datetime


class ScenarioFull(ScenarioSummary):
    """带完整 ``data`` JSON 的 scenario 详情。"""

    data: dict[str, Any]


class ScenarioStatistics(BaseModel):
    """快速概览：side / 单位类型计数 / 时间窗。"""

    scenario_id: str
    name: str
    start_time: int | None = None
    current_time: int | None = None
    duration: int | None = None
    sides: list[dict[str, Any]] = Field(default_factory=list)
    counts: dict[str, int] = Field(
        default_factory=dict,
        description="单位类型 → 数量：aircraft / ship / facility / airbase / weapon / referencePoint",
    )
    mission_count: int = 0


# ---------- Units / threats ----------------------------------------------


class UnitBrief(BaseModel):
    id: str | None = None
    name: str | None = None
    type: str | None = Field(default=None, description="aircraft / ship / facility / airbase / weapon / referencePoint")
    side_id: str | None = None
    class_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None
    heading: float | None = None
    speed: float | None = None
    current_fuel: float | None = None
    max_fuel: float | None = None
    is_objective: bool | None = None


class ListUnitsResult(BaseModel):
    scenario_id: str
    total: int
    units: list[UnitBrief]


class UnitDetail(BaseModel):
    """单单位详情，比 ``UnitBrief`` 多了 weapons 与原始字段透传。"""

    brief: UnitBrief
    weapons: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] = Field(
        default_factory=dict,
        description="单位原始 JSON（透传），后续字段演进可由 LLM 自取",
    )


class ThreatItem(BaseModel):
    unit: UnitBrief
    distance_km: float | None = Field(
        default=None,
        description="到最近的己方单位的大圆距离（公里）；无己方单位则为 null",
    )


class QueryThreatsResult(BaseModel):
    scenario_id: str
    from_side_id: str
    total: int
    threats: list[ThreatItem] = Field(
        ...,
        description="按 distance_km 升序排序；距离未知者排在末尾",
    )


# ---------- AAR -----------------------------------------------------------


class AarRecordOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    scenario_id: str | None = None
    owner_id: uuid.UUID | None = None
    outcome_reason: str
    winner_side_id: str = ""
    summary: dict[str, Any]
    ended_at: datetime
    created_at: datetime


# ---------- Runtime (AICCRuntime) ----------------------------------


class RuntimeSideStat(BaseModel):
    id: str
    name: str
    color: str | None = None
    total_score: float = 0


class RuntimeStatus(BaseModel):
    """正在跑的内存活想定的态势快照。

    注意：这是 ``AICCRuntime.game.current_scenario`` 的实时状态，
    与 ``Scenario.data``（DB 静态快照）不同源；二者通过 ``runtime_load_*`` /
    ``runtime_save_to_db`` 桥接，不会自动同步。
    """

    ok: Literal[True] = True
    scenario_id: str | None = None
    scenario_name: str
    paused: bool
    start_time: int
    current_time: int
    duration: int
    elapsed: int = Field(..., description="current_time - start_time")
    duration_left: int = Field(..., description="max(0, start_time + duration - current_time)")
    counts: dict[str, int] = Field(
        ...,
        description="按单位类型聚合的活单位数：aircraft / ship / facility / airbase / weapon / referencePoint",
    )
    sides: list[RuntimeSideStat]


class RuntimeStepResult(BaseModel):
    ok: Literal[True] = True
    steps_executed: int
    current_time: int
    elapsed: int
    duration_left: int


class RuntimeDeployResult(BaseModel):
    ok: Literal[True] = True
    unit_type: str
    unit_id: str
    name: str
    side_id: str


class RuntimeSimpleResult(BaseModel):
    """生命周期 / 事件触发等无单独结构数据的工具统一响应。"""

    ok: Literal[True] = True
    action: str
    state: dict[str, Any] = Field(default_factory=dict)


class RuntimeOutcome(BaseModel):
    """Authoritative runtime outcome plus supporting survival signals.

    ``ended`` / ``winner_side_id`` / ``reason`` come from the Python simulation
    engine. ``annihilated_side_ids`` and ``surviving_side_ids`` remain status
    signals only; annihilation is not a victory condition.
    """

    ok: Literal[True] = True
    ended: bool = False
    winner_side_id: str | None = None
    reason: str = ""
    ended_at: int = 0
    objective_destroyed: dict[str, Any] | None = None
    time_up: bool
    annihilated_side_ids: list[str]
    surviving_side_ids: list[str]
    inferred_winner_side_id: str | None = Field(
        default=None,
        description="只在恰好一方存活时给出；多方/时间到的情况返回 null 由 LLM 判",
    )
    current_time: int
    duration_left: int


class RuntimeSavedScenario(BaseModel):
    """runtime → DB 桥接的返回：新建的 scenario 行的摘要。"""

    ok: Literal[True] = True
    saved_scenario_id: str
    name: str
    version: int
    current_time: int
