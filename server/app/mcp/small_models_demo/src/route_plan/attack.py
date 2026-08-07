"""
路径规划主入口。

用法:
    python -m route_plan.attack scenario_example.json [-o output_dir]

流程:
    1. 加载 JSON 场景
    2. 为每个平台的每个目标构建方向扇区
    3. 在每个扇区内运行 Theta* 搜索
    4. 收集 top-k 最低代价路径
    5. 输出 JSON 结果
"""

import argparse
import itertools
import json
import math
import os
import multiprocessing
from typing import Any, Dict, List
import time
from pathlib import Path

from src.config_utils import deep_merge
from .io import (
    load_data,
    load_scenario,
    PathResult,
    path_to_llh,
    write_results,
)
from .grid import (
    build_grid,
    plan_single_direction,
    precompute_fmm_distance,
    CostEvaluator,
)
from .cost import CostConfig
from .sectors import (
    ApproachSector,
    generate_attack_point_sectors,
    generate_direction_reference_sectors,
    generate_uniform_approach_reference_sectors,
    calculate_arrival_angle,
)
from .core.geo import (
    azimuth_elevation_to_vector,
    ecef_to_enu,
    ecef_to_llh,
    llh_to_ecef,
    local_to_llh,
    vec_len,
    vec_sub,
)


def _edge_exposure(
    p1,
    p2,
    evaluator,
    num_samples,
):
    total = 0.0
    seg_len = vec_len(vec_sub(p2, p1))
    if seg_len < 1e-9:
        return 0.0
    if num_samples == 0:
        return (evaluator._point_threat(p1) + evaluator._point_threat(p2)) * seg_len
    for idx in range(num_samples + 1):
        t = idx / num_samples
        px = p1[0] + t * (p2[0] - p1[0])
        py = p1[1] + t * (p2[1] - p1[1])
        pz = p1[2] + t * (p2[2] - p1[2])
        total += evaluator._point_threat((px, py, pz))
    return (total / (num_samples + 1)) * seg_len


def _truncate_path(path, distance_km):
    """沿路径从终点反向回溯 distance_km，返回截断后的路径与攻击点 ECEF.

    Returns: (truncated_path, attack_pos_ecef)
    """
    remaining = distance_km
    for i in range(len(path) - 1, 0, -1):
        seg = vec_sub(path[i], path[i - 1])
        seg_len = vec_len(seg)
        if remaining <= seg_len:
            t = remaining / seg_len if seg_len > 0 else 0
            attack_pos = (
                path[i][0] - t * seg[0],
                path[i][1] - t * seg[1],
                path[i][2] - t * seg[2],
            )
            return path[:i] + [attack_pos], attack_pos
        remaining -= seg_len
    return [path[0]], path[0]


def _direction_dispersion(paths):
    """计算选中路径的方向分散度.

    Returns:
        (min_sep_deg, avg_sep_deg): 最小分离角(度), 平均分离角(度).
        仅1条路径时返回 (180, 180).
    """
    if len(paths) <= 1:
        return (180.0, 180.0)

    seps = []
    for i in range(len(paths)):
        va = azimuth_elevation_to_vector(paths[i].direction[0], paths[i].direction[1])
        for j in range(i + 1, len(paths)):
            vb = azimuth_elevation_to_vector(
                paths[j].direction[0], paths[j].direction[1]
            )
            dot = va[0] * vb[0] + va[1] * vb[1] + va[2] * vb[2]
            angle = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
            seps.append(angle)

    if not seps:
        return (180.0, 180.0)
    return (min(seps), sum(seps) / len(seps))


def select_best_per_pair(pair_groups, cfg):
    """按模式分类选择最优路径组合.

    - mode 1/5: 每对独立选最低 (cost, threat_exposure).
    - mode 2/3/4: 按目标分组，枚举所有方向组合，优先方向分散，再压低威胁和总代价.
    """
    results = []
    threat_tolerance = 1.0 + cfg.threat_tolerance_ratio

    # 收集按模式分组
    mode1 = {}
    grouped_by_target = {}  # target_id -> {platform_id: [paths]}
    for (pid, tid), paths in pair_groups.items():
        if not paths:
            continue
        m = paths[0].mode
        if m in (1, 5):
            mode1[(pid, tid)] = paths
        else:
            grouped_by_target.setdefault(tid, {})[pid] = paths

    # mode 1/5: 最低代价
    for paths in mode1.values():
        best = min(paths, key=lambda r: (r.cost, r.threat_exposure))
        results.append(best)

    # mode 2/3/4: 按目标分组，方向分散优化
    for tid, plat_paths in grouped_by_target.items():
        plat_ids = sorted(plat_paths.keys())
        buckets = [
            sorted(plat_paths[k], key=lambda r: (r.cost, r.threat_exposure))
            for k in plat_ids
        ]
        combos = list(itertools.product(*buckets))
        if not combos:
            continue

        scored = []
        for combo in combos:
            total_threat = sum(p.threat_exposure for p in combo)
            total_cost = sum(p.cost for p in combo)
            min_sep, avg_sep = _direction_dispersion(list(combo))
            scored.append((combo, total_cost, total_threat, min_sep, avg_sep))

        min_threat = min(s[2] for s in scored)
        feasible = [s for s in scored if s[2] <= min_threat * threat_tolerance]
        feasible.sort(key=lambda s: (-s[3], -s[4], s[2], s[1]))
        results.extend(list(feasible[0][0]))

    return results


def _resolve_attack_point_settings(pc, cfg):
    return (
        pc.attack_point_radius_km
        if pc and pc.attack_point_radius_km > 0
        else cfg.default_attack_point_radius_km,
        pc.attack_point_up_height_km
        if pc and pc.attack_point_up_height_km > 0
        else cfg.default_attack_point_up_height_km,
        pc.attack_point_count
        if pc and pc.attack_point_count > 0
        else cfg.default_attack_point_count,
    )


def _resolve_approach_ref_settings(pc, cfg):
    return (
        pc.approach_ref_radius_km
        if pc and pc.approach_ref_radius_km > 0
        else cfg.default_approach_ref_radius_km,
        pc.approach_ref_up_height_km
        if pc and pc.approach_ref_up_height_km > 0
        else cfg.default_approach_ref_up_height_km,
        pc.approach_ref_count
        if pc and pc.approach_ref_count > 0
        else cfg.default_approach_ref_count,
    )


def _build_direct_sector(
    start_llh, end_llh, end_local, label="direct"
) -> ApproachSector:
    dlon = end_llh[0] - start_llh[0]
    dlat = end_llh[1] - start_llh[1]
    az = (math.degrees(math.atan2(dlon, dlat)) + 360) % 360
    el = -math.degrees(
        math.atan2(
            (start_llh[2] - end_llh[2]) / 1000.0,
            math.sqrt(dlon**2 + dlat**2) * 111.32,
        )
    )
    return ApproachSector(
        azimuth_deg=az,
        elevation_deg=el,
        direction_vec=azimuth_elevation_to_vector(az, el),
        point_local=end_local,
        point_label=label,
        point_kind="direct",
    )


def _combine_paths(first_leg, second_leg):
    if first_leg is None or second_leg is None:
        return None
    if not first_leg:
        return second_leg
    if not second_leg:
        return first_leg
    return first_leg + second_leg[1:]


def _path_terminal_heading_deg(path, ref_lon, ref_lat):
    if not path or len(path) < 2:
        return None
    prev_local = ecef_to_enu(path[-2][0], path[-2][1], path[-2][2], ref_lon, ref_lat)
    last_local = ecef_to_enu(path[-1][0], path[-1][1], path[-1][2], ref_lon, ref_lat)
    dx = last_local[0] - prev_local[0]
    dy = last_local[1] - prev_local[1]
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return None
    return (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0


def _build_mode_sectors(platform, target, mode, pair_cfg, cfg):
    if pair_cfg and pair_cfg.meet_point:
        label_prefix = f"via_{pair_cfg.meet_point}"
    else:
        label_prefix = ""

    if mode in (3, 4):
        radius_km, up_height_km, count = _resolve_attack_point_settings(pair_cfg, cfg)
        sectors = generate_attack_point_sectors(
            target.id,
            target.position_local,
            radius_km,
            up_height_km,
            count,
        )
        if label_prefix:
            for sector in sectors.sectors:
                sector.point_label = f"{label_prefix}_{sector.point_label}"
        return sectors.sectors

    if mode == 2:
        radius_km, up_height_km, count = _resolve_approach_ref_settings(pair_cfg, cfg)
        if target.approach_directions:
            sectors = generate_direction_reference_sectors(
                target.id,
                target.position_local,
                target.approach_directions,
                reference_radius_km=radius_km,
            )
        else:
            sectors = generate_uniform_approach_reference_sectors(
                target.id,
                target.position_local,
                radius_km,
                up_height_km,
                count,
            )
        if label_prefix:
            for sector in sectors.sectors:
                sector.point_label = f"{label_prefix}_{sector.point_label}"
        return sectors.sectors

    direct_label = f"{label_prefix}_direct" if label_prefix else "direct"
    return [
        _build_direct_sector(
            platform.position_llh,
            target.position_llh,
            target.position_local,
            label=direct_label,
        )
    ]


def _plan_sector_worker(task):
    """单个扇区路径规划的 worker 函数 (多进程并行)."""
    grid = task["grid"]
    threat_field = task["threat_field"]
    platform = task["platform"]
    target = task["target"]
    sector = task["sector"]
    mode = task["mode"]
    waypoint = task["waypoint"]
    ref_lon = task["ref_lon"]
    ref_lat = task["ref_lat"]
    heading_count = task["heading_count"]
    vertical_open_threat_distance_km = task["vertical_open_threat_distance_km"]
    edge_samples = task["edge_samples"]
    cost_config_base = task["cost_config_base"]
    mode2_direction_active = task["mode2_direction_active"]
    rcs_scale = task["rcs_scale"]
    min_turn_radius_km_val = task["min_turn_radius_km"]
    direction_activation_radius_km = task["direction_activation_radius_km"]
    attack_point_radius_km = task.get("attack_point_radius_km", 0.0)
    meet_point_id = task.get("meet_point_id", "")
    meet_point_llh = task.get("meet_point_llh")
    pair_key = task["pair_key"]
    use_fmm = task.get("use_fmm", True)
    heuristic_mode = task.get("heuristic_mode", "ecef")
    force_unidirectional = task.get("force_unidirectional", False)
    fmm_cache = task.get("fmm_cache", {})

    cost_config = CostConfig(
        distance_weight=cost_config_base.distance_weight,
        threat_weight=cost_config_base.threat_weight,
        direction_weight=cost_config_base.direction_weight,
        turn_weight=cost_config_base.turn_weight,
        min_turn_radius_km=min_turn_radius_km_val,
        mode2_direction_active=mode2_direction_active,
        rcs_scale=rcs_scale,
        bidirectional=cost_config_base.bidirectional and not force_unidirectional,
        direction_activation_radius_km=direction_activation_radius_km,
        edge_samples=edge_samples,
        use_heading=cost_config_base.use_heading,
        heuristic_mode=heuristic_mode,
    )
    evaluator = CostEvaluator(threat_field, cost_config, ref_lon, ref_lat)

    target_ecef = llh_to_ecef(*target.position_llh)

    leg_start_llh = platform.position_llh
    first_leg = []
    first_leg_target_ecef = None
    first_leg_sector = None
    initial_heading_deg = platform.initial_heading_deg

    search_time_total = 0.0
    expanded_total = 0
    fmm_time_total = 0.0

    if waypoint is not None:
        first_leg_sector = _build_direct_sector(
            platform.position_llh,
            waypoint.position_llh,
            waypoint.position_local,
            label=f"to_{waypoint.id}",
        )
        first_leg_target_ecef = llh_to_ecef(*waypoint.position_llh)
        # FMM heuristic for first leg (forward + reverse)
        if use_fmm:
            t_fmm = time.perf_counter()
            wp_goal_node = grid.pos_to_node(*waypoint.position_llh)
            fmm_dist = fmm_cache.get(wp_goal_node)
            if fmm_dist is None:
                fmm_dist = precompute_fmm_distance(
                    grid, wp_goal_node, threat_field, evaluator.config.threat_weight
                )
            evaluator.set_fmm_heuristic(fmm_dist, grid)
            start_node = grid.pos_to_node(*platform.position_llh)
            fmm_rev = precompute_fmm_distance(
                grid, start_node, threat_field, evaluator.config.threat_weight
            )
            evaluator.set_fmm_heuristic_reverse(fmm_rev)
            fmm_time_total += time.perf_counter() - t_fmm
        saved_active = evaluator.config.mode2_direction_active
        evaluator.config.mode2_direction_active = False
        first_leg, leg_time, leg_exp = plan_single_direction(
            grid,
            platform.position_llh,
            waypoint.position_llh,
            first_leg_sector,
            first_leg_target_ecef,
            evaluator,
            ref_lon,
            ref_lat,
            heading_count,
            min_turn_radius_km_val,
            platform.initial_heading_deg,
            vertical_open_threat_distance_km,
        )
        search_time_total += leg_time
        expanded_total += leg_exp
        evaluator.config.mode2_direction_active = saved_active
        if first_leg is None:
            return (None, pair_key)
        leg_start_llh = waypoint.position_llh
        initial_heading_deg = _path_terminal_heading_deg(first_leg, ref_lon, ref_lat)

    if mode in (3, 4):
        search_target_llh = local_to_llh(
            sector.point_local[0],
            sector.point_local[1],
            sector.point_local[2],
            ref_lon,
            ref_lat,
        )
        search_target_ecef = llh_to_ecef(*search_target_llh)
    else:
        search_target_llh = target.position_llh
        search_target_ecef = target_ecef

    # FMM heuristic for second leg (forward + reverse)
    if use_fmm:
        t_fmm = time.perf_counter()
        leg2_goal_node = grid.pos_to_node(*search_target_llh)
        fmm_dist = fmm_cache.get(leg2_goal_node)
        if fmm_dist is None:
            fmm_dist = precompute_fmm_distance(
                grid, leg2_goal_node, threat_field, evaluator.config.threat_weight
            )
        evaluator.set_fmm_heuristic(fmm_dist, grid)
        leg2_start_node = grid.pos_to_node(*leg_start_llh)
        fmm_rev = precompute_fmm_distance(
            grid, leg2_start_node, threat_field, evaluator.config.threat_weight
        )
        evaluator.set_fmm_heuristic_reverse(fmm_rev)
        fmm_time_total += time.perf_counter() - t_fmm

    second_leg, leg_time, leg_exp = plan_single_direction(
        grid,
        leg_start_llh,
        search_target_llh,
        sector,
        search_target_ecef,
        evaluator,
        ref_lon,
        ref_lat,
        heading_count,
        min_turn_radius_km_val,
        initial_heading_deg,
        vertical_open_threat_distance_km,
    )
    search_time_total += leg_time
    expanded_total += leg_exp

    path = _combine_paths(first_leg, second_leg) if waypoint is not None else second_leg

    if path is None:
        return (None, pair_key)

    # 将起点/终点/途径点从网格对齐位置替换为真实位置
    path[0] = llh_to_ecef(*platform.position_llh)
    path[-1] = search_target_ecef
    if waypoint is not None and len(first_leg) > 0:
        wp_idx = len(first_leg) - 1
        path[wp_idx] = llh_to_ecef(*waypoint.position_llh)

    terminal_ecef = search_target_ecef
    control_point_llh = None
    control_point_kind_override = None  # mode 5 覆盖 sector.point_kind
    if mode == 5 and attack_point_radius_km > 0 and len(path) >= 2:
        path, attack_pos_ecef = _truncate_path(path, attack_point_radius_km)
        terminal_ecef = attack_pos_ecef
        control_point_llh = ecef_to_llh(*attack_pos_ecef)
        control_point_kind_override = "attack_point"
    elif sector.point_kind in ("approach_ref", "attack_point"):
        control_point_llh = local_to_llh(
            sector.point_local[0],
            sector.point_local[1],
            sector.point_local[2],
            ref_lon,
            ref_lat,
        )

    total_cost = 0.0
    first_leg_edge_count = max(0, len(first_leg) - 1) if waypoint is not None else 0
    for i in range(len(path) - 1):
        edge_target = terminal_ecef
        edge_direction = sector.direction_vec
        if i < first_leg_edge_count and first_leg_sector is not None:
            edge_target = first_leg_target_ecef
            edge_direction = first_leg_sector.direction_vec
        ec, _ = evaluator.edge_cost(
            path[i],
            path[i + 1],
            edge_target,
            edge_direction,
        )
        total_cost += ec

    threat_exp = 0.0
    segment_details = []
    crossed_map = {}
    for i in range(len(path) - 1):
        edge_target = terminal_ecef
        edge_direction = sector.direction_vec
        if i < first_leg_edge_count and first_leg_sector is not None:
            edge_target = first_leg_target_ecef
            edge_direction = first_leg_sector.direction_vec
        seg_threat = _edge_exposure(
            path[i],
            path[i + 1],
            evaluator,
            edge_samples,
        )
        threat_exp += seg_threat
        seg_cost, _ = evaluator.edge_cost(
            path[i],
            path[i + 1],
            edge_target,
            edge_direction,
        )
        seg_hits = threat_field.edge_threat_hits(
            path[i],
            path[i + 1],
            num_samples=edge_samples,
            rcs_scale=rcs_scale,
        )
        for hit in seg_hits:
            key = (hit["id"], hit["type"])
            if key not in crossed_map:
                crossed_map[key] = dict(hit)
            else:
                crossed_map[key]["avg_value"] = max(
                    crossed_map[key]["avg_value"], hit["avg_value"]
                )
                crossed_map[key]["max_value"] = max(
                    crossed_map[key]["max_value"], hit["max_value"]
                )
        segment_details.append(
            {
                "from_index": i,
                "to_index": i + 1,
                "segment_cost": seg_cost,
                "threat_exposure": seg_threat,
                "crossed_threats": seg_hits,
            }
        )

    if len(path) >= 2:
        last_local = ecef_to_enu(
            path[-2][0],
            path[-2][1],
            path[-2][2],
            ref_lon,
            ref_lat,
        )
        if mode == 5:
            arrival_target_local = ecef_to_enu(
                path[-1][0], path[-1][1], path[-1][2],
                ref_lon, ref_lat,
            )
        elif mode in (3, 4):
            arrival_target_local = sector.point_local
        else:
            arrival_target_local = target.position_local
        arrival_angle = calculate_arrival_angle(last_local, arrival_target_local)
    else:
        arrival_angle = (0, 0)

    waypoints_llh = path_to_llh(path, ref_lon, ref_lat)
    waypoint_details = []
    for idx, (wp_llh, wp_ecef) in enumerate(zip(waypoints_llh, path)):
        hits = threat_field.point_threat_hits(wp_ecef, rcs_scale=rcs_scale)
        waypoint_details.append(
            {
                "index": idx,
                "waypoint": wp_llh,
                "threat_cost": evaluator._point_threat(wp_ecef),
                "hits": hits,
            }
        )

    crossed_threats = sorted(
        crossed_map.values(),
        key=lambda item: (-item["max_value"], item["id"]),
    )

    # 计算路径距离
    path_length_km = 0.0
    cumulative = [0.0]
    for i in range(1, len(path)):
        seg_len = vec_len(vec_sub(path[i], path[i - 1]))
        path_length_km += seg_len
        cumulative.append(path_length_km)

    # 计算攻击点到目标的距离 (武器飞行距离)
    target_distance_km = vec_len(vec_sub(target_ecef, path[-1]))

    # Refuel segments for aircraft with range constraints
    refuel_segments: List[Dict[str, Any]] = []
    if platform.cls == "aircraft" and platform.range_km > 0 and len(path) >= 2:
        from .refuel import calculate_refuel_segments, RefuelConfig

        refuel_map = calculate_refuel_segments(
            [{
                "platform": platform.id,
                "target": target.id,
                "waypoints": waypoints_llh,
            }],
            {platform.id: platform},
            threat_field,
            RefuelConfig(safe_distance_km=5.0),
        )
        key = f"{platform.id}->{target.id}"
        for rs in refuel_map.get(key, []):
            refuel_segments.append({
                "start_distance_km": rs.start_distance_km,
                "end_distance_km": rs.end_distance_km,
                "refuel_distance_km": rs.refuel_distance_km,
                "refuel_speed_kmh": rs.refuel_speed_kmh,
                "start_position": list(rs.start_position_llh),
                "end_position": list(rs.end_position_llh),
                "range_remaining_before_km": rs.range_remaining_before_km,
                "adjusted": rs.adjusted,
                "threat_distance_km": rs.threat_distance_km,
            })

    direction_label = (
        sector.point_label or f"{sector.azimuth_deg}/{sector.elevation_deg}"
    )
    if mode == 4:
        direction_label += "_stealth"

    result = PathResult(
        platform_id=platform.id,
        target_id=target.id,
        direction=(sector.azimuth_deg, sector.elevation_deg),
        direction_label=direction_label,
        cost=total_cost,
        threat_exposure=threat_exp,
        waypoints_llh=waypoints_llh,
        arrival_angle=arrival_angle,
        control_point_llh=control_point_llh,
        control_point_label="attack_pos" if mode == 5 else sector.point_label,
        control_point_kind=control_point_kind_override or sector.point_kind,
        crossed_threats=crossed_threats,
        waypoint_details=waypoint_details,
        segment_details=segment_details,
        mode=mode,
        path_length_km=path_length_km,
        target_distance_km=target_distance_km,
        cumulative_distances_km=cumulative,
        refuel_segments=refuel_segments,
        meet_point_id=meet_point_id,
        meet_point_llh=meet_point_llh,
        search_time_sec=search_time_total,
        expanded_nodes=expanded_total,
        fmm_time_sec=fmm_time_total,
    )

    return (result, pair_key)


def main():
    parser = argparse.ArgumentParser(description="多方向进入路径规划")
    parser.add_argument("scenario", help="场景 YAML / JSON 文件路径")
    parser.add_argument("-o", "--output", default=None, help="输出目录 (默认: output/{场景名}_result/")
    parser.add_argument("--no-fmm", action="store_true", help="禁用 FMM 启发式 (用于对比)")
    parser.add_argument("--no-bidirectional", action="store_true", help="强制单向 A* (用于对比)")
    args = parser.parse_args()

    # 1. 加载场景（含默认配置合并）
    print(f"加载场景: {args.scenario}")
    defaults_path = Path(__file__).resolve().parent / "input" / "_defaults.yaml"
    defaults = load_data(str(defaults_path)) if defaults_path.exists() else {}
    scenario = load_scenario(args.scenario, defaults)
    cfg = scenario.planner_config

    print(f"  参考点: ({scenario.ref_lon:.4f}, {scenario.ref_lat:.4f})")
    print(f"  平台数: {len(scenario.platforms)}")
    print(f"  目标数: {len(scenario.targets)}")
    print(
        f"  威胁场: {len(scenario.threat_field.spheres)} 球体, "
        f"{len(scenario.threat_field.cones)} 圆锥体, "
        f"{len(scenario.threat_field.cylinders)} 圆柱体, "
        f"{len(scenario.threat_field.elliptic_cylinders)} 椭圆柱体"
    )
    print(f"  禁飞区: {len(scenario.threat_field.no_fly_zones)}")
    print(f"  网格分辨率: {cfg.grid.resolution_km} km")
    print(f"  高度层: {[f'{a * 1000:.0f}m' for a in cfg.grid.altitude_km]}")
    print(f"  高度开放威胁阈值: {cfg.vertical_open_threat_distance_km:.1f} km")
    print(f"  Waypoint: {len(scenario.waypoints)} 个显式必经点")
    print(
        "  候选点默认值: "
        f"attack=({cfg.default_attack_point_radius_km:.1f}km, "
        f"{cfg.default_attack_point_up_height_km * 1000:.0f}m, "
        f"{cfg.default_attack_point_count}个), "
        f"approach_ref=({cfg.default_approach_ref_radius_km:.1f}km, "
        f"{cfg.default_approach_ref_up_height_km * 1000:.0f}m, "
        f"{cfg.default_approach_ref_count}个)"
    )

    # 构建平台-目标对: YAML 显式 pairs 或全连接 fallback
    pair_specs = []
    if scenario.pair_configs:
        print(f"  Pairs: {len(scenario.pair_configs)} 显式对")
        for pc in scenario.pair_configs:
            p = next((p for p in scenario.platforms if p.id == pc.platform_id), None)
            t = next((t for t in scenario.targets if t.id == pc.target_id), None)
            if p and t:
                pair_specs.append((p, t, pc))
            else:
                print(f"  警告: pair {pc.platform_id}→{pc.target_id} 找不到平台或目标")
    else:
        print(f"  Pairs: {len(scenario.platforms) * len(scenario.targets)} (全连接)")
        for p in scenario.platforms:
            for t in scenario.targets:
                pair_specs.append((p, t, None))
    print(f"  默认模式: {scenario.default_mode}")

    t_pipeline_start = time.perf_counter()

    waypoint_map = {wp.id: wp for wp in scenario.waypoints}

    # ---- Phase 1: 收集关键点 + 构建网格 ----
    t_phase = time.perf_counter()
    all_points = []
    for p in scenario.platforms:
        all_points.append(p.position_llh)
    for t in scenario.targets:
        all_points.append(t.position_llh)
    for wp in scenario.waypoints:
        all_points.append(wp.position_llh)
    for platform, target, pc in pair_specs:
        mode = pc.mode if pc else scenario.default_mode
        if pc and pc.meet_point:
            waypoint = waypoint_map.get(pc.meet_point)
            if waypoint is None:
                print(
                    f"  警告: pair {platform.id}→{target.id} 引用的 waypoint "
                    f"{pc.meet_point} 不存在"
                )
            else:
                all_points.append(waypoint.position_llh)
        if mode in (3, 4):
            radius_km, up_height_km, count = _resolve_attack_point_settings(pc, cfg)
            sectors = generate_attack_point_sectors(
                target.id,
                target.position_local,
                radius_km,
                up_height_km,
                count,
            )
        elif mode == 2:
            radius_km, up_height_km, count = _resolve_approach_ref_settings(pc, cfg)
            if target.approach_directions:
                sectors = generate_direction_reference_sectors(
                    target.id,
                    target.position_local,
                    target.approach_directions,
                    reference_radius_km=radius_km,
                )
            else:
                sectors = generate_uniform_approach_reference_sectors(
                    target.id,
                    target.position_local,
                    radius_km,
                    up_height_km,
                    count,
                )
        else:
            sectors = None
        if sectors:
            for sector in sectors.sectors:
                all_points.append(
                    local_to_llh(
                        sector.point_local[0],
                        sector.point_local[1],
                        sector.point_local[2],
                        scenario.ref_lon,
                        scenario.ref_lat,
                    )
                )

    # 自动加入目标/必经点/攻击点的高度层 (不低于最低配置层)
    all_alts = sorted(set(p[2] / 1000.0 for p in all_points))
    min_alt_km = min(cfg.grid.altitude_km) if cfg.grid.altitude_km else 0.0
    new_alt_km = [a for a in all_alts if a not in cfg.grid.altitude_km and a >= min_alt_km]
    if new_alt_km:
        cfg.grid.altitude_km = sorted(cfg.grid.altitude_km + new_alt_km)
        print(f"  自动加入高度层: {[f'{a * 1000:.0f}m' for a in new_alt_km]}")
    print(f"  高度层: {[f'{a * 1000:.0f}m' for a in cfg.grid.altitude_km]}")

    grid = build_grid(all_points, cfg.grid, scenario.ref_lon, scenario.ref_lat)
    print(
        f"  网格: {grid.nx}×{grid.ny}×{len(grid.altitudes)} = "
        f"{grid.nx * grid.ny * len(grid.altitudes)} 节点"
    )
    t_grid_build = time.perf_counter() - t_phase
    print(f"  [耗时] 网格构建: {t_grid_build:.2f}s")

    # ---- Phase 2: 预计算节点威胁值 ----
    t_phase = time.perf_counter()
    print("  预计算节点威胁值...")
    grid.precompute_threat(scenario.threat_field)
    grid.precompute_dense_nfz(scenario.threat_field)
    t_threat_pre = time.perf_counter() - t_phase
    print(f"  [耗时] 威胁预计算: {t_threat_pre:.2f}s")

    print(f"  启发函数: {cfg.heuristic.upper()}")
    print(f"  双向A*: {'开启' if cfg.cost.bidirectional else '关闭'}")

    # ---- Phase 3: 构建并行任务 ----
    t_phase = time.perf_counter()
    num_workers = max(1, os.cpu_count() - 4)
    print(f"\n并行进程数: {num_workers} (CPU核心数: {os.cpu_count()})")

    fmm_cache = {}
    all_tasks = []
    for platform, target, pc in pair_specs:
        mode = pc.mode if pc else scenario.default_mode
        print(f"  准备: {platform.id} → {target.id} (mode={mode})")
        waypoint = None
        meet_point_llh = None
        if pc and pc.meet_point:
            waypoint = waypoint_map.get(pc.meet_point)
            if waypoint is None:
                print(f"    跳过: waypoint {pc.meet_point} 不存在")
                continue
            meet_point_llh = waypoint.position_llh

        mode2_dir_active = mode == 2
        min_tr = (
            cfg.cost.missile_turn_radius_km
            if platform.cls == "missile"
            else cfg.cost.aircraft_turn_radius_km
        )
        dir_activation = 0.0
        if mode == 2:
            dir_activation, _, _ = _resolve_approach_ref_settings(pc, cfg)

        attack_radius = 0.0
        if mode == 5:
            attack_radius, _, _ = _resolve_attack_point_settings(pc, cfg)

        sectors = _build_mode_sectors(platform, target, mode, pc, cfg)

        for sector in sectors:
            task = {
                "grid": grid,
                "threat_field": scenario.threat_field,
                "platform": platform,
                "target": target,
                "sector": sector,
                "mode": mode,
                "waypoint": waypoint,
                "ref_lon": scenario.ref_lon,
                "ref_lat": scenario.ref_lat,
                "heading_count": cfg.heading_count,
                "vertical_open_threat_distance_km": cfg.vertical_open_threat_distance_km,
                "edge_samples": cfg.cost.edge_samples,
                "cost_config_base": cfg.cost,
                "mode2_direction_active": mode2_dir_active,
                "rcs_scale": cfg.stealth_rcs_scale if mode == 4 else platform.rcs_scale,
                "min_turn_radius_km": min_tr,
                "direction_activation_radius_km": dir_activation,
                "attack_point_radius_km": attack_radius,
                "meet_point_id": pc.meet_point or "",
                "meet_point_llh": meet_point_llh,
                "pair_key": (platform.id, target.id),
                "use_fmm": cfg.heuristic == "fmm" and not args.no_fmm,
                "heuristic_mode": cfg.heuristic,
                "force_unidirectional": args.no_bidirectional,
                "fmm_cache": fmm_cache,
            }
            all_tasks.append(task)

    t_task_build = time.perf_counter() - t_phase
    print(f"  [耗时] 任务构建: {t_task_build:.2f}s")

    # ---- Phase 3.5: 预计算 FMM 缓存 (共享目标/汇合点) ----
    if cfg.heuristic == "fmm" and not args.no_fmm:
        t_fmm_cache = time.perf_counter()
        # 收集唯一的目标位置
        unique_goals = {}  # (grid_i, grid_j, grid_k) -> count
        for platform, target, pc in pair_specs:
            target_node = grid.pos_to_node(*target.position_llh)
            unique_goals[target_node] = unique_goals.get(target_node, 0) + 1
            if pc and pc.meet_point:
                wp = waypoint_map.get(pc.meet_point)
                if wp:
                    wp_node = grid.pos_to_node(*wp.position_llh)
                    unique_goals[wp_node] = unique_goals.get(wp_node, 0) + 1

        # 预计算共享的 FMM 前向图 (距离到目标)
        threat_w = cfg.cost.threat_weight
        n_cached = 0
        for goal_node, count in unique_goals.items():
            if count > 1:  # 只缓存被多次使用的
                fmm_cache[goal_node] = precompute_fmm_distance(
                    grid, goal_node, scenario.threat_field, threat_w
                )
                n_cached += 1
        print(f"  FMM 缓存: {n_cached}/{len(unique_goals)} 个目标预计算 ({time.perf_counter() - t_fmm_cache:.3f}s)")

    # ---- Phase 4: 并行 A* 搜索 ----
    print(f"\n任务总数: {len(all_tasks)}，开始并行规划...")
    t_phase = time.perf_counter()

    all_results = []
    with multiprocessing.Pool(processes=num_workers) as pool:
        for result, pair_key in pool.imap_unordered(_plan_sector_worker, all_tasks):
            if result is not None:
                all_results.append(result)
                label = result.direction_label
                az = result.direction[0]
                el = result.direction[1]
                wps = len(result.waypoints_llh)
                print(
                    f"    完成: {result.platform_id}→{result.target_id} {label} "
                    f"[{az:.1f}°, {el:.1f}°] cost={result.cost:.1f} "
                    f"threat={result.threat_exposure:.3f} wp={wps}"
                )

    t_parallel = time.perf_counter() - t_phase
    print(f"并行规划完成，耗时 {t_parallel:.2f}s，成功 {len(all_results)} 条路径")

    # A* 搜索统计汇总
    total_search_time = sum(r.search_time_sec for r in all_results)
    total_expanded = sum(r.expanded_nodes for r in all_results)
    total_fmm_time = sum(r.fmm_time_sec for r in all_results)
    max_search_time = max((r.search_time_sec for r in all_results), default=0)
    avg_search_time = total_search_time / len(all_results) if all_results else 0
    print(f"  A* 搜索总计: {total_search_time:.2f}s (平均 {avg_search_time:.3f}s/次, 最长 {max_search_time:.3f}s)")
    print(f"  总展开节点: {total_expanded} (平均 {total_expanded // max(1, len(all_results))}/次)")
    print(f"  FMM预计算总计: {total_fmm_time:.3f}s")

    # ---- Phase 5: 结果选择 ----
    t_phase = time.perf_counter()
    # direct 模式: 每个平台-目标对选最低 cost
    # anchor 模式: 每个平台-目标对保留 8 个候选，再做全局组合选择
    best_results = []
    pair_groups = {}
    for r in all_results:
        key = (r.platform_id, r.target_id)
        pair_groups.setdefault(key, []).append(r)

    best_results = select_best_per_pair(pair_groups, cfg)
    t_select = time.perf_counter() - t_phase

    best_map = {(r.platform_id, r.target_id): r for r in best_results}
    for key, paths in pair_groups.items():
        best = best_map[key]
        others = [p for p in paths if p != best]
        print(f"\n  {key[0]} → {key[1]}: 共{len(paths)}个方向")
        print(
            f"    最佳: 方位{best.direction[0]}° 俯仰{best.direction[1]}° "
            f"标签={best.direction_label} "
            f"威胁暴露={best.threat_exposure:.1f} 代价={best.cost:.0f}"
        )
        for o in sorted(others, key=lambda r: (r.cost, r.threat_exposure)):
            print(
                f"    备选: 方位{o.direction[0]}° 俯仰{o.direction[1]}° 标签={o.direction_label} "
                f"威胁暴露={o.threat_exposure:.1f} 代价={o.cost:.0f}"
            )

    print(f"\n========== 结果汇总 ==========")
    print(f"  总路径数: {len(all_results)}")
    print(f"  最终选取: {len(best_results)} 条 (每武器-目标对1条)")

    # 5. 输出 YAML / JSON
    if args.output:
        output_dir = Path(args.output)
    else:
        scenario_name = scenario.name
        output_dir = (
            Path(__file__).resolve().parent.parent
            / "output"
            / f"{scenario_name}_result"
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    input_ext = Path(args.scenario).suffix.lower()
    result_ext = input_ext if input_ext in (".json", ".yaml", ".yml") else ".yaml"
    result_path = str(output_dir / f"result{result_ext}")

    write_results(best_results, result_path, scenario=scenario)
    print(f"\n结果已写入: {result_path}")

    # ---- Phase 6: 可视化 ----
    t_phase = time.perf_counter()
    plot_output = str(output_dir / "2d.png")
    try:
        from .viz.plot_2d import plot_scenario

        print("\n生成 2D 俯视图...")
        plot_scenario(scenario, grid, best_results, plot_output)
    except ImportError as e:
        print(f"  2D 可视化跳过: {e}")
    t_viz = time.perf_counter() - t_phase

    # ---- 总耗时汇总 ----
    t_total = time.perf_counter() - t_pipeline_start
    print(f"\n========== 各阶段耗时汇总 ==========")
    print(f"  网格构建:        {t_grid_build:8.2f}s")
    print(f"  威胁预计算:      {t_threat_pre:8.2f}s")
    print(f"  任务构建:        {t_task_build:8.2f}s")
    print(f"  并行A*搜索:      {t_parallel:8.2f}s  ({len(all_tasks)}任务, {num_workers}进程)")
    print(f"  结果选择:        {t_select:8.2f}s")
    print(f"  可视化:          {t_viz:8.2f}s")
    print(f"  {'─' * 35}")
    print(f"  总耗时:          {t_total:8.2f}s")



if __name__ == "__main__":
    main()
