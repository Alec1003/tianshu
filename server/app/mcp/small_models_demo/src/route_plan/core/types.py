"""核心数据类型 — 场景、路径结果等纯数据结构。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

class Platform:
    id: str
    type: str  # 型号, e.g. "JH7A", "YJ18", "J11B"
    position_llh: Tuple[float, float, float]  # (lon, lat, alt_m)
    position_local: Tuple[float, float, float] = (0, 0, 0)  # 由 build_scenario 填充
    cls: str = "aircraft"  # "aircraft" | "missile"
    speed_ms: float = 250.0
    range_km: float = 1500.0
    range_remaining_km: float = 1500.0  # 当前剩余航程，默认与 range_km 一致
    initial_heading_deg: Optional[float] = None

class Target:
    id: str
    position_llh: Tuple[float, float, float]
    position_local: Tuple[float, float, float] = (0, 0, 0)
    approach_directions: List[Tuple[float, float]] = field(default_factory=list)
    arrival_radius_km: float = 50.0
    capacity: Dict[str, int] = field(
        default_factory=dict
    )  # {机型: 最大容量}，返航基地使用

class Waypoint:
    id: str
    position_llh: Tuple[float, float, float]
    position_local: Tuple[float, float, float] = (0, 0, 0)

class PairConfig:
    """平台-目标对配置.

    mode 说明:
      1 — 直接攻击目标，可选引用必经点
      2 — 直接攻击目标，使用入射角参考点定义不同末端方向代价
      3 — 规划到候选攻击点，可选引用必经点
      4 — 隐身规划到候选攻击点，可选引用必经点
    """

    platform_id: str
    target_id: str
    mode: int = 2
    waypoint_id: Optional[str] = None
    attack_point_radius_km: float = 0.0
    attack_point_up_height_km: float = 0.0
    attack_point_count: int = 0
    approach_ref_radius_km: float = 0.0
    approach_ref_up_height_km: float = 0.0
    approach_ref_count: int = 0

class PathResult:
    platform_id: str
    target_id: str
    direction: Tuple[float, float]
    cost: float
    threat_exposure: float
    waypoints_llh: List[Tuple[float, float, float]]  # (lon, lat, alt_m)
    arrival_angle: Tuple[float, float]  # 实际进入角度
    direction_label: str = ""
    control_point_llh: Optional[Tuple[float, float, float]] = None
    control_point_label: str = ""
    control_point_kind: str = ""
    crossed_threats: List[Dict[str, Any]] = field(default_factory=list)
    waypoint_details: List[Dict[str, Any]] = field(default_factory=list)
    segment_details: List[Dict[str, Any]] = field(default_factory=list)
    mode: int = 2

