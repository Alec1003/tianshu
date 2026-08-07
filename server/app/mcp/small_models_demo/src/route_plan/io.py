"""
场景与结果输入输出模块。

支持 YAML / JSON:
- 读取场景文件，解析平台/目标/威胁场/禁飞区
- 将规划结果写回 YAML 或 JSON
"""

import json
from pathlib import Path

import yaml
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.config_utils import deep_merge
from .core.geo import (
    azimuth_elevation_to_vector,
    llh_to_local,
)
from .threats import (
    ThreatField,
    SphereThreat,
    ConeThreat,
    CylinderThreat,
    EllipticCylinderThreat,
    EllipsoidThreat,
)
from .cost import CostConfig
from .grid import GridConfig, PlannerConfig


# ============================================================
# 场景数据结构
# ============================================================


@dataclass
class Platform:
    id: str
    type: str  # 型号, e.g. "JH7A", "YJ18", "J11B"
    position_llh: Tuple[float, float, float]  # (lon, lat, alt_m)
    position_local: Tuple[float, float, float] = (0, 0, 0)  # 由 build_scenario 填充
    cls: str = "aircraft"  # "aircraft" | "missile"
    speed_kmh: float = 900.0
    range_km: float = 1500.0
    range_remaining_km: float = 1500.0  # 当前剩余航程，默认与 range_km 一致
    initial_heading_deg: Optional[float] = None
    rcs_scale: float = 1.0  # RCS 缩放因子 (σ_target/σ_ref), SNR ∝ rcs_scale
    weapon_speed_kmh: float = 0.0  # 发射武器速度 (km/h), 0=无独立武器阶段
    refuel_speed_kmh: float = 0.0  # 加油时速度 (km/h), 0=使用 speed_kmh
    refuel_duration_min: float = 8.0  # 单次加油耗时 (分钟)


@dataclass
class Target:
    id: str
    position_llh: Tuple[float, float, float]
    position_local: Tuple[float, float, float] = (0, 0, 0)
    approach_directions: List[Tuple[float, float]] = field(default_factory=list)
    arrival_radius_km: float = 50.0
    capacity: Dict[str, int] = field(
        default_factory=dict
    )  # {机型: 最大容量}，返航基地使用


@dataclass
class Waypoint:
    id: str
    position_llh: Tuple[float, float, float]
    position_local: Tuple[float, float, float] = (0, 0, 0)


@dataclass
class PairConfig:
    """平台-目标对配置.

    mode 说明:
      1 — 直接攻击目标，可选引用必经点
      2 — 直接攻击目标，使用入射角参考点定义不同末端方向代价
      3 — 规划到候选攻击点，可选引用必经点
      4 — 隐身规划到候选攻击点，可选引用必经点
      5 — mode1 最优代价路径 + 沿路径回退攻击距离找攻击阵位
    """

    platform_id: str
    target_id: str
    mode: int = 2
    meet_point: Optional[str] = None
    attack_point_radius_km: float = 0.0
    attack_point_up_height_km: float = 0.0
    attack_point_count: int = 0
    approach_ref_radius_km: float = 0.0
    approach_ref_up_height_km: float = 0.0
    approach_ref_count: int = 0


@dataclass
class Scenario:
    name: str
    ref_lon: float = 0.0
    ref_lat: float = 0.0
    platforms: List[Platform] = field(default_factory=list)
    waypoints: List[Waypoint] = field(default_factory=list)
    targets: List[Target] = field(default_factory=list)
    pair_configs: List[PairConfig] = field(default_factory=list)
    default_mode: int = 2
    threat_field: ThreatField = field(default_factory=ThreatField)
    planner_config: PlannerConfig = field(default_factory=PlannerConfig)


# ============================================================
# 读取场景
# ============================================================


def load_data(filepath: str) -> Dict[str, Any]:
    """按文件后缀读取 YAML / JSON 数据."""
    suffix = Path(filepath).suffix.lower()
    with open(filepath, "r", encoding="utf-8") as f:
        if suffix == ".json":
            return json.load(f)
        return yaml.safe_load(f)


def dump_data(data: Dict[str, Any], filepath: str) -> None:
    """按文件后缀写出 YAML / JSON 数据."""
    suffix = Path(filepath).suffix.lower()
    with open(filepath, "w", encoding="utf-8") as f:
        if suffix == ".json":
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            return
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def load_scenario(filepath: str, defaults: dict = None) -> Scenario:
    """从 JSON 文件加载场景。可选 defaults 字典用于深度合并默认配置。"""
    data = load_data(filepath)
    if defaults:
        data = deep_merge(defaults, data)
    sc = data.get("scenario", data)
    scenario = Scenario(name=sc.get("name", "unnamed"))

    # 1. 收集所有位置点，计算参考中心
    all_lon, all_lat = [], []

    platforms_raw = sc.get("platforms", [])
    for p in platforms_raw:
        pos = p["position"]
        all_lon.append(pos[0])
        all_lat.append(pos[1])

    targets_raw = sc.get("targets", [])
    for t in targets_raw:
        pos = t["position"]
        all_lon.append(pos[0])
        all_lat.append(pos[1])

    threats_raw = sc.get("threats", [])
    for th in threats_raw:
        pos = th["position"]
        all_lon.append(pos[0])
        all_lat.append(pos[1])

    no_fly_raw = sc.get("no_fly_zones", [])
    for nfz in no_fly_raw:
        pos = nfz["position"]
        all_lon.append(pos[0])
        all_lat.append(pos[1])

    waypoints_raw = sc.get("waypoints", [])
    for wp in waypoints_raw:
        pos = wp["position"]
        all_lon.append(pos[0])
        all_lat.append(pos[1])

    scenario.ref_lon = sum(all_lon) / len(all_lon) if all_lon else 0.0
    scenario.ref_lat = sum(all_lat) / len(all_lat) if all_lat else 0.0
    scenario.threat_field.ref_lon = scenario.ref_lon
    scenario.threat_field.ref_lat = scenario.ref_lat

    # 2. 解析平台
    for p in platforms_raw:
        pos = p["position"]
        local = llh_to_local(pos[0], pos[1], pos[2], scenario.ref_lon, scenario.ref_lat)
        raw_type = p.get("type", "aircraft")
        raw_cls = p.get("class", "")
        if not raw_cls:
            raw_cls = raw_type if raw_type in ("aircraft", "missile") else "aircraft"
        scenario.platforms.append(
            Platform(
                id=p["id"],
                type=raw_type,
                cls=raw_cls,
                position_llh=(pos[0], pos[1], pos[2]),
                position_local=local,
                speed_kmh=p.get("speed", 900),
                range_km=p.get("range", 1500),
                range_remaining_km=p.get("range_remaining", p.get("range", 1500)),
                initial_heading_deg=p.get("initial_heading_deg"),
                rcs_scale=p.get("rcs", 1.0),
                weapon_speed_kmh=p.get("weapon_speed", p.get("speed", 900)),
                refuel_speed_kmh=p.get("refuel_speed", 0),
                refuel_duration_min=p.get("refuel_duration_min", 8.0),
            )
        )

    # 3. 解析必经点
    for wp in waypoints_raw:
        pos = wp["position"]
        local = llh_to_local(pos[0], pos[1], pos[2], scenario.ref_lon, scenario.ref_lat)
        scenario.waypoints.append(
            Waypoint(
                id=wp["id"],
                position_llh=(pos[0], pos[1], pos[2]),
                position_local=local,
            )
        )

    # 4. 解析目标
    for t in targets_raw:
        pos = t["position"]
        local = llh_to_local(pos[0], pos[1], pos[2], scenario.ref_lon, scenario.ref_lat)
        scenario.targets.append(
            Target(
                id=t["id"],
                position_llh=(pos[0], pos[1], pos[2]),
                position_local=local,
                capacity=t.get("capacity", {}),  # 新增
                approach_directions=[
                    tuple(d) for d in t.get("approach_directions", [])
                ],
                arrival_radius_km=t.get("arrival_radius", 50),
            )
        )

    # 5. 解析威胁场
    for th in threats_raw:
        pos = th["position"]
        local_pos = llh_to_local(
            pos[0], pos[1], pos[2], scenario.ref_lon, scenario.ref_lat
        )
        params = th.get("params", {})
        tlevel = th.get("threat_level", 0.5)
        ttype = th["type"]

        if ttype == "sphere":
            scenario.threat_field.spheres.append(
                SphereThreat(
                    center=local_pos,
                    radius=params["radius"],
                    threat_level=tlevel,
                    id=th.get("id", ""),
                )
            )
        elif ttype == "cone":
            az, el = params["direction"]
            direction = azimuth_elevation_to_vector(az, el)
            scenario.threat_field.cones.append(
                ConeThreat(
                    apex=local_pos,
                    direction=direction,
                    angle_deg=params["angle"],
                    max_range_km=params["max_range"],
                    threat_level=tlevel,
                    id=th.get("id", ""),
                )
            )
        elif ttype == "cylinder":
            scenario.threat_field.cylinders.append(
                CylinderThreat(
                    center_2d=(local_pos[0], local_pos[1]),
                    radius=params["radius"],
                    height=params.get("height", 100.0) / 1000.0,  # m → km
                    threat_level=tlevel,
                    id=th.get("id", ""),
                )
            )
        elif ttype == "elliptic_cylinder":
            scenario.threat_field.elliptic_cylinders.append(
                EllipticCylinderThreat(
                    center_2d=(local_pos[0], local_pos[1]),
                    semi_major=params["semi_major"],
                    semi_minor=params["semi_minor"],
                    azimuth_deg=params["azimuth"],
                    height=params.get("height", 100.0) / 1000.0,
                    threat_level=tlevel,
                    id=th.get("id", ""),
                )
            )
        elif ttype == "ellipsoid":
            az, el = params["direction"]
            direction = azimuth_elevation_to_vector(az, el)
            scenario.threat_field.ellipsoids.append(
                EllipsoidThreat(
                    center=local_pos,
                    direction=direction,
                    semi_a=params.get("semi_a", params.get("semi_b", 50.0)),
                    semi_b=params.get("semi_b", params.get("semi_a", 50.0)),
                    semi_c=params["semi_c"],
                    threat_level=tlevel,
                    id=th.get("id", ""),
                )
            )

    # 6. 解析禁飞区
    for nfz in no_fly_raw:
        pos = nfz["position"]
        local_pos = llh_to_local(
            pos[0], pos[1], pos[2], scenario.ref_lon, scenario.ref_lat
        )
        params = nfz.get("params", {})
        nfz_type = nfz.get("type", "cylinder")
        if nfz_type == "ellipsoid":
            az, el = params["direction"]
            direction = azimuth_elevation_to_vector(az, el)
            scenario.threat_field.nfz_ellipsoids.append(
                EllipsoidThreat(
                    center=local_pos,
                    direction=direction,
                    semi_a=params.get("semi_a", params.get("semi_b", 50.0)),
                    semi_b=params.get("semi_b", params.get("semi_a", 50.0)),
                    semi_c=params["semi_c"],
                    threat_level=1.0,
                    id=nfz.get("id", ""),
                )
            )
        else:
            scenario.threat_field.no_fly_zones.append(
                CylinderThreat(
                    center_2d=(local_pos[0], local_pos[1]),
                    radius=params["radius"],
                    height=params.get("height", 100.0) / 1000.0,
                    threat_level=1.0,
                    id=nfz.get("id", ""),
                )
            )

    # 6.5 加载 EW 干扰场 (dict: threat_id → JammingField)
    jamming_cfg = sc.get("jamming", {})
    if jamming_cfg.get("pkl"):
        from src.ew.ew_jamming_field import load_ew_lookup, load_ew_metadata
        jamming_dict = load_ew_lookup(jamming_cfg["pkl"])
        jamming_meta = load_ew_metadata(jamming_cfg["pkl"])
        scenario.threat_field.set_jamming(jamming_dict, jamming_meta)

    # 7. 解析规划参数
    plan_cfg = sc.get("planning", {})
    grid_cfg = GridConfig(
        resolution_km=plan_cfg.get("grid_resolution_km", 10.0),
        altitude_km=[
            a / 1000.0
            for a in plan_cfg.get("altitude_levels", [100, 5000, 10000, 15000])
        ],
        margin_km=plan_cfg.get("margin_km", 100.0),
    )
    cost_cfg = CostConfig(
        distance_weight=plan_cfg.get("distance_weight", 1.0),
        threat_weight=plan_cfg.get("threat_weight", 100.0),
        direction_weight=plan_cfg.get("direction_weight", 50.0),
        turn_weight=plan_cfg.get("turn_weight", 30.0),
        aircraft_turn_radius_km=plan_cfg.get("aircraft_turn_radius_km", 10.0),
        missile_turn_radius_km=plan_cfg.get("missile_turn_radius_km", 6.0),
        bidirectional=plan_cfg.get("bidirectional", True),
        edge_samples=plan_cfg.get("edge_samples", 8),
        use_heading=plan_cfg.get("use_heading", True),
        heuristic_mode=plan_cfg.get("heuristic", "ecef"),
    )
    scenario.planner_config = PlannerConfig(
        grid=grid_cfg,
        cost=cost_cfg,
        default_attack_point_radius_km=plan_cfg.get(
            "default_attack_point_radius_km",
            plan_cfg.get("anchor_radius_km", 50.0),
        ),
        default_attack_point_up_height_km=plan_cfg.get(
            "default_attack_point_up_height_m",
            plan_cfg.get("anchor_up_height_m", 3000.0),
        )
        / 1000.0,
        default_attack_point_count=plan_cfg.get("default_attack_point_count", 8),
        default_approach_ref_radius_km=plan_cfg.get(
            "default_approach_ref_radius_km",
            plan_cfg.get("anchor_radius_km", 50.0),
        ),
        default_approach_ref_up_height_km=plan_cfg.get(
            "default_approach_ref_up_height_m", 0.0
        )
        / 1000.0,
        default_approach_ref_count=plan_cfg.get("default_approach_ref_count", 4),
        heading_count=plan_cfg.get("heading_count", 16),
        vertical_open_threat_distance_km=plan_cfg.get(
            "vertical_open_threat_distance_km", 30.0
        ),
        threat_tolerance_ratio=plan_cfg.get("threat_tolerance_ratio", 0.05),
        stealth_rcs_scale=plan_cfg.get("stealth_factor", 0.4),
        heuristic=plan_cfg.get("heuristic", "ecef"),
        use_heading=plan_cfg.get("use_heading", True),
    )

    # 8. 解析平台-目标对
    pair_raw = sc.get("pairs", [])
    scenario.default_mode = plan_cfg.get("default_mode", 2)
    for pr in pair_raw:
        legacy_anchor_radius = pr.get("anchor_radius_km", 0.0)
        scenario.pair_configs.append(
            PairConfig(
                platform_id=pr["platform"],
                target_id=pr["target"],
                mode=pr.get("mode", scenario.default_mode),
                meet_point=pr.get("meet_point"),
                attack_point_radius_km=pr.get(
                    "attack_point_radius_km",
                    legacy_anchor_radius
                    if pr.get("mode", scenario.default_mode) in (3, 4)
                    else 0.0,
                ),
                attack_point_up_height_km=pr.get("attack_point_up_height_m", 0.0)
                / 1000.0,
                attack_point_count=pr.get("attack_point_count", 0),
                approach_ref_radius_km=pr.get(
                    "approach_ref_radius_km",
                    legacy_anchor_radius
                    if pr.get("mode", scenario.default_mode) == 2
                    else 0.0,
                ),
                approach_ref_up_height_km=pr.get("approach_ref_up_height_m", 0.0)
                / 1000.0,
                approach_ref_count=pr.get("approach_ref_count", 0),
            )
        )

    return scenario


# ============================================================
# 结果输出
# ============================================================


@dataclass
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
    path_length_km: float = 0.0
    target_distance_km: float = 0.0
    cumulative_distances_km: List[float] = field(default_factory=list)
    refuel_segments: List[Dict[str, Any]] = field(default_factory=list)
    meet_point_id: str = ""
    meet_point_llh: Optional[Tuple[float, float, float]] = None
    search_time_sec: float = 0.0
    expanded_nodes: int = 0
    fmm_time_sec: float = 0.0


def path_to_llh(
    path_ecef: List[Tuple[float, float, float]],
    ref_lon: float = 0,
    ref_lat: float = 0,
) -> List[Tuple[float, float, float]]:
    """ECEF 坐标路径 → WGS84 坐标."""
    from .core.geo import ecef_to_llh

    result = []
    for x, y, z in path_ecef:
        lon, lat, alt_m = ecef_to_llh(x, y, z)
        result.append((lon, lat, alt_m))
    return result


def write_results(
    results: List[PathResult],
    output_path: str,
    scenario: "Scenario" = None,
) -> None:
    """将规划结果写入 YAML / JSON 文件. scenario 用于输出平台/目标元数据."""
    plat_map = {}
    target_map = {}
    if scenario is not None:
        plat_map = {p.id: p for p in scenario.platforms}
        target_map = {t.id: t for t in scenario.targets}

    output = {"results": []}

    for r in results:
        plat = plat_map.get(r.platform_id)
        tgt = target_map.get(r.target_id)

        entry = {
            "platform": r.platform_id,
            "platform_type": plat.type if plat else None,
            "platform_cls": plat.cls if plat else None,
            "platform_speed_kmh": plat.speed_kmh if plat else None,
            "platform_range_km": plat.range_km if plat else None,
            "weapon_speed_kmh": plat.weapon_speed_kmh if plat else None,
            "refuel_speed_kmh": plat.refuel_speed_kmh if plat else None,
            "refuel_duration_min": plat.refuel_duration_min if plat else None,
            "target": r.target_id,
            "target_position": [round(v, 4) for v in tgt.position_llh]
            if tgt
            else None,
            "mode": r.mode,
            "direction": list(r.direction),
            "direction_label": r.direction_label,
            "cost": round(r.cost, 2),
            "threat_exposure": round(r.threat_exposure, 4),
            "arrival_angle": [round(a, 2) for a in r.arrival_angle],
            "path_length_km": round(r.path_length_km, 4),
            "target_distance_km": round(r.target_distance_km, 4),
            "cumulative_distances_km": [round(d, 4) for d in r.cumulative_distances_km],
            "refuel_segments": r.refuel_segments,
            "meet_point_id": r.meet_point_id or None,
            "meet_point": [round(v, 4) for v in r.meet_point_llh]
            if r.meet_point_llh
            else None,
            "waypoints": [[round(v, 4) for v in wp] for wp in r.waypoints_llh],
            "control_point": [round(v, 4) for v in r.control_point_llh]
            if r.control_point_llh
            else None,
            "control_point_label": r.control_point_label or None,
            "control_point_kind": r.control_point_kind or None,
            "crossed_threats": [
                {
                    "id": item["id"],
                    "type": item["type"],
                    "avg_value": round(item["avg_value"], 4),
                    "max_value": round(item["max_value"], 4),
                }
                for item in r.crossed_threats
            ],
            "waypoint_details": [
                {
                    "index": item["index"],
                    "waypoint": [round(v, 4) for v in item["waypoint"]],
                    "threat_cost": round(item["threat_cost"], 4),
                    "hits": [
                        {
                            "id": hit["id"],
                            "type": hit["type"],
                            "value": round(hit["value"], 4),
                        }
                        for hit in item["hits"]
                    ],
                }
                for item in r.waypoint_details
            ],
            "segment_details": [
                {
                    "from_index": item["from_index"],
                    "to_index": item["to_index"],
                    "segment_cost": round(item["segment_cost"], 4),
                    "threat_exposure": round(item["threat_exposure"], 4),
                    "crossed_threats": [
                        {
                            "id": hit["id"],
                            "type": hit["type"],
                            "avg_value": round(hit["avg_value"], 4),
                            "max_value": round(hit["max_value"], 4),
                        }
                        for hit in item["crossed_threats"]
                    ],
                }
                for item in r.segment_details
            ],
        }
        output["results"].append(entry)

    dump_data(output, output_path)
