"""
返航路径规划主入口。

用法:
    python -m route_plan.return_plan input/return_test.json [-o output_dir]

流程:
    1. 加载 JSON 场景
    2. 构建所有 (platform, base) 规划任务
    3. 多进程并行跑 mode1 路径规划
    4. MILP 分配飞机到基地
    5. 输出结果 JSON
"""

import argparse
import json
import math
import os
import multiprocessing
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.config_utils import deep_merge
from .io import (
    PathResult,
    dump_data,
    load_data,
    load_scenario,
    path_to_llh,
    write_results,
)
from .grid import (
    build_grid,
    plan_single_direction,
    CostEvaluator,
)
from .cost import CostConfig
from .sectors import (
    ApproachSector,
    calculate_arrival_angle,
)
from .core.geo import (
    azimuth_elevation_to_vector,
    ecef_to_enu,
    llh_to_ecef,
    llh_to_local,
    local_to_llh,
    vec_len,
    vec_sub,
)
from .assignment import assign_platforms_to_bases

INF = float("inf")


@dataclass
class ReturnPathResult:
    platform_id: str
    base_id: str
    aircraft_type: str
    cost: float
    path: Optional[PathResult]


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


def _edge_exposure(p1, p2, evaluator, num_samples):
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


def _plan_single_return(task):
    """单个 return 路径规划 worker."""
    grid = task["grid"]
    threat_field = task["threat_field"]
    platform = task["platform"]
    base = task["base"]
    ref_lon = task["ref_lon"]
    ref_lat = task["ref_lat"]
    heading_count = task["heading_count"]
    vertical_open_threat_distance_km = task["vertical_open_threat_distance_km"]
    edge_samples = task["edge_samples"]
    cost_config_base = task["cost_config_base"]

    cost_config = CostConfig(
        distance_weight=cost_config_base.distance_weight,
        threat_weight=cost_config_base.threat_weight,
        direction_weight=cost_config_base.direction_weight,
        turn_weight=cost_config_base.turn_weight,
        min_turn_radius_km=(
            cost_config_base.missile_turn_radius_km
            if platform.cls == "missile"
            else cost_config_base.aircraft_turn_radius_km
        ),
        mode2_direction_active=False,
        bidirectional=cost_config_base.bidirectional,
        direction_activation_radius_km=0.0,
        edge_samples=edge_samples,
        rcs_scale=platform.rcs_scale,
        use_heading=cost_config_base.use_heading,
        heuristic_mode=getattr(cost_config_base, 'heuristic_mode', 'ecef'),
    )
    evaluator = CostEvaluator(threat_field, cost_config, ref_lon, ref_lat)

    sector = _build_direct_sector(
        platform.position_llh,
        base.position_llh,
        base.position_local,
    )

    target_ecef = llh_to_ecef(*base.position_llh)

    path, _search_time, _expanded = plan_single_direction(
        grid,
        platform.position_llh,
        base.position_llh,
        sector,
        target_ecef,
        evaluator,
        ref_lon,
        ref_lat,
        heading_count,
        cost_config.min_turn_radius_km,
        platform.initial_heading_deg,
        vertical_open_threat_distance_km,
    )

    if path is None:
        return (platform.id, base.id, platform.type, INF, None)

    # 将起点/终点从网格对齐位置替换为真实位置
    path = list(path)
    path[0] = llh_to_ecef(*platform.position_llh)
    path[-1] = target_ecef

    # 计算路径距离
    path_length_km = 0.0
    cumulative = [0.0]
    for i in range(1, len(path)):
        seg_len = vec_len(vec_sub(path[i], path[i - 1]))
        path_length_km += seg_len
        cumulative.append(path_length_km)

    target_distance_km = vec_len(vec_sub(target_ecef, path[-1]))

    total_cost = 0.0
    for i in range(len(path) - 1):
        seg_cost, _ = evaluator.edge_cost(
            path[i],
            path[i + 1],
            target_ecef,
            sector.direction_vec,
        )
        total_cost += seg_cost

    threat_exp = 0.0
    crossed_map = {}
    segment_details = []
    for i in range(len(path) - 1):
        seg_threat = _edge_exposure(path[i], path[i + 1], evaluator, edge_samples)
        threat_exp += seg_threat
        seg_cost, _ = evaluator.edge_cost(
            path[i],
            path[i + 1],
            target_ecef,
            sector.direction_vec,
        )
        seg_hits = threat_field.edge_threat_hits(
            path[i],
            path[i + 1],
            num_samples=edge_samples,
            rcs_scale=platform.rcs_scale,
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
        arrival_angle = calculate_arrival_angle(last_local, base.position_local)
    else:
        arrival_angle = (0, 0)

    waypoints_llh = path_to_llh(path, ref_lon, ref_lat)

    waypoint_details = []
    for idx, (wp_llh, wp_ecef) in enumerate(zip(waypoints_llh, path)):
        hits = threat_field.point_threat_hits(wp_ecef, rcs_scale=platform.rcs_scale)
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

    # Refuel segments for aircraft with range constraints
    refuel_segments: list = []
    if platform.cls == "aircraft" and platform.range_km > 0 and len(path) >= 2:
        from .refuel import calculate_refuel_segments, RefuelConfig

        waypoints_for_refuel = [
            [wp[0], wp[1], wp[2]] for wp in waypoints_llh
        ]
        refuel_map = calculate_refuel_segments(
            [{
                "platform": platform.id,
                "target": base.id,
                "waypoints": waypoints_for_refuel,
            }],
            {platform.id: platform},
            threat_field,
            RefuelConfig(safe_distance_km=5.0),
        )
        raw_segs = refuel_map.get(f"{platform.id}->{base.id}", [])
        refuel_segments = [
            {
                "start_distance_km": rs.start_distance_km,
                "end_distance_km": rs.end_distance_km,
                "refuel_distance_km": rs.refuel_distance_km,
                "refuel_speed_kmh": rs.refuel_speed_kmh,
                "start_position": list(rs.start_position_llh),
                "end_position": list(rs.end_position_llh),
                "range_remaining_before_km": rs.range_remaining_before_km,
                "adjusted": rs.adjusted,
                "threat_distance_km": rs.threat_distance_km,
            }
            for rs in raw_segs
        ]

    result = PathResult(
        platform_id=platform.id,
        target_id=base.id,
        direction=(sector.azimuth_deg, sector.elevation_deg),
        direction_label="return",
        cost=total_cost,
        threat_exposure=threat_exp,
        waypoints_llh=waypoints_llh,
        arrival_angle=arrival_angle,
        control_point_llh=None,
        control_point_label="",
        control_point_kind="",
        crossed_threats=crossed_threats,
        waypoint_details=waypoint_details,
        segment_details=segment_details,
        mode=1,
        path_length_km=path_length_km,
        target_distance_km=target_distance_km,
        cumulative_distances_km=cumulative,
        refuel_segments=refuel_segments,
    )

    return (platform.id, base.id, platform.type, total_cost, result)


def main():
    parser = argparse.ArgumentParser(description="返航路径规划")
    parser.add_argument("scenario", help="场景 YAML / JSON 文件路径")
    parser.add_argument("-o", "--output", default=None, help="输出目录 (默认: output/{场景名}_return_result/")
    args = parser.parse_args()

    print(f"加载场景: {args.scenario}")
    defaults_path = Path(__file__).resolve().parent / "input" / "_defaults.yaml"
    defaults = load_data(str(defaults_path)) if defaults_path.exists() else {}
    scenario = load_scenario(args.scenario, defaults)
    cfg = scenario.planner_config

    print(f"  参考点: ({scenario.ref_lon:.4f}, {scenario.ref_lat:.4f})")
    print(f"  平台数 (待返航): {len(scenario.platforms)}")
    print(f"  基地数: {len(scenario.targets)}")
    for t in scenario.targets:
        print(f"    {t.id}: capacity={t.capacity}")
    print(
        f"  威胁场: {len(scenario.threat_field.spheres)} 球体, "
        f"{len(scenario.threat_field.cones)} 圆锥体, "
        f"{len(scenario.threat_field.cylinders)} 圆柱体"
    )

    all_points = []
    for p in scenario.platforms:
        all_points.append(p.position_llh)
    for t in scenario.targets:
        all_points.append(t.position_llh)

    all_base_alts = sorted(set(t.position_llh[2] / 1000.0 for t in scenario.targets))
    all_plat_alts = sorted(set(p.position_llh[2] / 1000.0 for p in scenario.platforms))
    min_alt_km = min(cfg.grid.altitude_km) if cfg.grid.altitude_km else 0.0
    extra_alt_km = [a for a in all_base_alts + all_plat_alts
                    if a not in cfg.grid.altitude_km and a >= min_alt_km]
    if extra_alt_km:
        cfg.grid.altitude_km = sorted(cfg.grid.altitude_km + extra_alt_km)
        print(f"  自动加入高度层: {[f'{a * 1000:.0f}m' for a in extra_alt_km]}")
    print(f"  高度层: {[f'{a * 1000:.0f}m' for a in cfg.grid.altitude_km]}")

    grid = build_grid(all_points, cfg.grid, scenario.ref_lon, scenario.ref_lat)
    print(
        f"  网格: {grid.nx}×{grid.ny}×{len(grid.altitudes)} = "
        f"{grid.nx * grid.ny * len(grid.altitudes)} 节点"
    )

    print("  预计算节点威胁值...")
    grid.precompute_threat(scenario.threat_field)
    grid.precompute_dense_nfz(scenario.threat_field)
    print("  完成")

    platforms = scenario.platforms
    bases = scenario.targets

    eligible_tasks = []
    skipped = 0
    for platform in platforms:
        for base in bases:
            cap = base.capacity.get(platform.type, 0)
            if cap == 0:
                skipped += 1
                continue
            task = {
                "grid": grid,
                "threat_field": scenario.threat_field,
                "platform": platform,
                "base": base,
                "ref_lon": scenario.ref_lon,
                "ref_lat": scenario.ref_lat,
                "heading_count": cfg.heading_count,
                "vertical_open_threat_distance_km": cfg.vertical_open_threat_distance_km,
                "edge_samples": cfg.cost.edge_samples,
                "cost_config_base": cfg.cost,
            }
            eligible_tasks.append(task)

    num_workers = max(1, os.cpu_count() - 4)
    print(f"\n并行进程数: {num_workers}")
    print(f"路径规划任务: {len(eligible_tasks)} (跳过{skipped}个容量为0的)")
    t_start = time.perf_counter()

    path_results: List[ReturnPathResult] = []
    with multiprocessing.Pool(processes=num_workers) as pool:
        for pid, bid, atype, cost, path_result in pool.imap_unordered(
            _plan_single_return, eligible_tasks
        ):
            r = ReturnPathResult(
                platform_id=pid,
                base_id=bid,
                aircraft_type=atype,
                cost=cost,
                path=path_result,
            )
            path_results.append(r)
            wp = len(path_result.waypoints_llh) if path_result else 0
            status = f"cost={cost:.1f} wp={wp}" if cost < INF / 2 else "FAILED"
            print(f"    {pid} → {bid}: {status}")

    t_total = time.perf_counter() - t_start
    print(
        f"路径规划完成，耗时 {t_total:.2f}s，成功 {sum(1 for r in path_results if r.cost < INF / 2)} 条"
    )

    cost_matrix = {}
    for r in path_results:
        cost_matrix[(r.platform_id, r.base_id)] = r.cost

    platform_types = {p.id: p.type for p in platforms}
    base_capacities = {b.id: b.capacity for b in bases}

    unassigned = []
    inf_platforms = set()
    for r in path_results:
        if r.cost >= INF / 2:
            inf_platforms.add(r.platform_id)
    for pid in [p.id for p in platforms]:
        if pid in inf_platforms:
            all_inf = all(
                (pid, b.id) in cost_matrix and cost_matrix[(pid, b.id)] >= INF / 2
                for b in bases
                if b.capacity.get(platform_types.get(pid, ""), 0) > 0
            )
            if all_inf:
                unassigned.append(pid)
                for b in bases:
                    cost_matrix.pop((pid, b.id), None)

    try:
        assignment, total_cost = assign_platforms_to_bases(
            cost_matrix,
            platform_types,
            base_capacities,
        )
        print(f"\nMILP 分配完成，总代价: {total_cost:.1f}")
        for pid in sorted(assignment.keys()):
            print(f"  {pid} → {assignment[pid]}")
    except ValueError as e:
        print(f"\nMILP 分配失败: {e}")
        assignment = {}
        total_cost = 0.0

    path_map = {}
    for r in path_results:
        if r.path is not None:
            path_map[(r.platform_id, r.base_id)] = r.path

    output_results = []
    for pid, bid in assignment.items():
        p = path_map.get((pid, bid))
        if p:
            output_results.append(p)

    if args.output:
        output_dir = Path(args.output)
    else:
        scenario_name = scenario.name
        output_dir = (
            Path(__file__).resolve().parent.parent
            / "output"
            / f"{scenario_name}_return_result"
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    output = {
        "name": f"{scenario.name}_return",
        "total_cost": round(total_cost, 2),
        "assignment": assignment,
        "unassigned": unassigned,
        "return_results": [
            {
                "platform_id": pid,
                "aircraft_type": platform_types.get(pid, ""),
                "assigned_base": bid,
            }
            for pid, bid in assignment.items()
        ],
    }

    input_ext = Path(args.scenario).suffix.lower()
    result_ext = input_ext if input_ext in (".json", ".yaml", ".yml") else ".yaml"
    result_path = str(output_dir / f"result{result_ext}")
    dump_data(output, result_path)

    paths_path = str(output_dir / f"paths{result_ext}")
    write_results(output_results, paths_path, scenario=scenario)
    print(f"\n结果已写入: {result_path}")
    print(f"路径已写入: {paths_path}")

    plot_output = str(output_dir / "2d.png")
    try:
        from .viz.plot_2d import plot_scenario

        print("\n生成 2D 俯视图...")
        plot_scenario(scenario, grid, output_results, plot_output)
    except ImportError as e:
        print(f"  2D 可视化跳过: {e}")

    html_output = str(output_dir / "3d.html")
    try:
        from .viz.plot_3d import plot_scenario_3d

        print("\n生成 3D 交互可视化...")
        plot_scenario_3d(scenario, grid, output_results, html_output)
        print(f"  3D 可视化: {html_output}")
    except ImportError as e:
        print(f"  3D 可视化跳过: {e}")


if __name__ == "__main__":
    main()
