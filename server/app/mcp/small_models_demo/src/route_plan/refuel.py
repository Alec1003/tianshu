"""加油点计算核心逻辑."""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class RefuelConfig:
    safe_distance_km: float = 30.0


@dataclass
class RefuelSegment:
    """Forward-moving refuel segment along the path."""
    platform_id: str
    target_id: str
    start_distance_km: float
    end_distance_km: float
    refuel_distance_km: float
    refuel_speed_kmh: float
    start_position_llh: Tuple[float, float, float]
    end_position_llh: Tuple[float, float, float]
    range_remaining_before_km: float
    adjusted: bool
    threat_distance_km: float


def _compute_segment_length(
    p1_llh: Tuple[float, float, float],
    p2_llh: Tuple[float, float, float],
) -> float:
    """Compute ECEF chord length (km) between two LLH points."""
    from .core.geo import llh_to_ecef, vec_len, vec_sub

    ecef1 = llh_to_ecef(*p1_llh)
    ecef2 = llh_to_ecef(*p2_llh)
    return vec_len(vec_sub(ecef2, ecef1))


def _build_cumulative_distances(
    waypoints: List[List[float]],
) -> List[float]:
    """Return cumulative path distances (km) for waypoints_llh.

    cum_dist[0] = 0.0, cum_dist[i] = distance from start to waypoints[i].
    """
    if len(waypoints) < 2:
        return [0.0]
    cum = [0.0]
    for i in range(len(waypoints) - 1):
        p1 = (waypoints[i][0], waypoints[i][1], waypoints[i][2])
        p2 = (waypoints[i + 1][0], waypoints[i + 1][1], waypoints[i + 1][2])
        seg_len = _compute_segment_length(p1, p2)
        cum.append(cum[-1] + seg_len)
    return cum


def _interpolate_at_distance(
    waypoints: List[List[float]],
    cum_dist: List[float],
    target_dist: float,
) -> Tuple[float, float, float]:
    """Interpolate LLH position at given cumulative distance along path.

    Returns (lon, lat, alt_m).
    """
    # Clamp to path bounds
    target_dist = max(0.0, min(target_dist, cum_dist[-1]))

    # Find segment k where cum_dist[k] <= target_dist < cum_dist[k+1]
    for k in range(len(cum_dist) - 1):
        if target_dist <= cum_dist[k + 1] + 1e-9:
            seg_len = cum_dist[k + 1] - cum_dist[k]
            if seg_len < 1e-9:
                return (waypoints[k][0], waypoints[k][1], waypoints[k][2])
            t = (target_dist - cum_dist[k]) / seg_len
            t = max(0.0, min(1.0, t))
            lon = waypoints[k][0] + t * (waypoints[k + 1][0] - waypoints[k][0])
            lat = waypoints[k][1] + t * (waypoints[k + 1][1] - waypoints[k][1])
            alt = waypoints[k][2] + t * (waypoints[k + 1][2] - waypoints[k][2])
            return (lon, lat, alt)

    # Should not reach here, but return last point
    return (waypoints[-1][0], waypoints[-1][1], waypoints[-1][2])


def _backtrack_to_safe(
    waypoints: List[List[float]],
    cum_dist: List[float],
    start_dist: float,
    end_dist: float,
    threat_field,
    safe_distance_km: float,
) -> Optional[Tuple[Tuple[float, float, float], float]]:
    """Search backward from end_dist to start_dist for first safe position.

    Uses binary search for O(log n) performance instead of linear scan.
    Returns (position_llh, actual_distance) or None if no safe point found.
    """
    from .core.geo import llh_to_ecef

    span = end_dist - start_dist
    if span <= 0.0:
        return None

    lo = start_dist
    hi = end_dist
    best: Optional[Tuple[Tuple[float, float, float], float]] = None

    while hi - lo > 0.5:
        mid = (lo + hi) / 2.0
        pos = _interpolate_at_distance(waypoints, cum_dist, mid)
        ecef = llh_to_ecef(*pos)
        d = threat_field.min_distance_to_any_threat(ecef)
        if d >= safe_distance_km:
            best = (pos, mid)
            lo = mid
        else:
            hi = mid

    pos = _interpolate_at_distance(waypoints, cum_dist, lo)
    ecef = llh_to_ecef(*pos)
    if threat_field.min_distance_to_any_threat(ecef) >= safe_distance_km:
        best = (pos, lo)

    return best


def calculate_refuel_segments(
    results: List[dict],
    platforms: Dict[str, "Platform"],
    threat_field,
    config: Optional[RefuelConfig] = None,
) -> Dict[str, List[RefuelSegment]]:
    """Calculate forward-moving refuel segments for all path results.

    Each refuel segment is flown at refuel_speed_kmh for refuel_duration_min,
    so the aircraft continues forward during refueling.

    Args:
        results: List of result dicts with keys "platform", "target", "waypoints".
        platforms: Dict[platform_id -> Platform].
        threat_field: ThreatField instance.
        config: RefuelConfig with safe_distance_km.

    Returns:
        Dict[result_key, List[RefuelSegment]].
    """
    from .core.geo import llh_to_ecef

    if config is None:
        config = RefuelConfig()

    output: Dict[str, List[RefuelSegment]] = {}

    for result in results:
        platform_id = result.get("platform", "")
        target_id = result.get("target", "")
        waypoints = result.get("waypoints", [])

        platform = platforms.get(platform_id)
        range_full = getattr(platform, "range_km", 0.0)
        if range_full <= 0:
            continue
        range_remaining = getattr(platform, "range_remaining_km", range_full)
        if range_remaining <= 0:
            continue

        if not waypoints or len(waypoints) < 2:
            continue

        # Refuel speed/duration from platform config (km/h, minutes)
        refuel_speed = (
            getattr(platform, "refuel_speed_kmh", 0.0)
            or getattr(platform, "speed_kmh", 900.0)
        )
        refuel_dur_min = getattr(platform, "refuel_duration_min", 8.0)
        refuel_distance_km = refuel_speed * refuel_dur_min / 60.0

        cum_dist = _build_cumulative_distances(waypoints)
        total_dist = cum_dist[-1]

        cursor_dist = 0.0
        range_left = range_remaining
        refuel_list: List[RefuelSegment] = []

        while cursor_dist + range_left * 2.0 / 3.0 < total_dist:
            # target_dist = 剩余 1/3 航程处 → 作为加油结束点
            target_dist = cursor_dist + range_left * 2.0 / 3.0

            raw_pos = _interpolate_at_distance(waypoints, cum_dist, target_dist)
            ecef_raw = llh_to_ecef(*raw_pos)
            threat_dist = threat_field.min_distance_to_any_threat(ecef_raw)
            adjusted = False
            refuel_end_dist = target_dist
            refuel_end_pos = raw_pos

            if threat_dist < config.safe_distance_km:
                adjusted = True
                bt_result = _backtrack_to_safe(
                    waypoints,
                    cum_dist,
                    cursor_dist,
                    target_dist,
                    threat_field,
                    config.safe_distance_km,
                )
                if bt_result is None:
                    break
                refuel_end_pos, refuel_end_dist = bt_result
                if refuel_end_dist <= cursor_dist + 1e-6:
                    break
                refuel_end_ecef = llh_to_ecef(*refuel_end_pos)
                threat_dist = threat_field.min_distance_to_any_threat(refuel_end_ecef)

            # 从加油结束点向前回退 refuel_distance_km，得到加油开始点
            refuel_start_dist = max(cursor_dist, refuel_end_dist - refuel_distance_km)
            actual_refuel_dist = refuel_end_dist - refuel_start_dist

            # 加油段太短则跳过（< 5km 没有实际意义）
            if actual_refuel_dist < 5.0:
                break

            refuel_start_pos = _interpolate_at_distance(waypoints, cum_dist, refuel_start_dist)

            range_remaining = range_left - (refuel_start_dist - cursor_dist)

            rs = RefuelSegment(
                platform_id=platform_id,
                target_id=target_id,
                start_distance_km=round(refuel_start_dist, 2),
                end_distance_km=round(refuel_end_dist, 2),
                refuel_distance_km=round(actual_refuel_dist, 2),
                refuel_speed_kmh=round(refuel_speed, 1),
                start_position_llh=(round(refuel_start_pos[0], 4), round(refuel_start_pos[1], 4), round(refuel_start_pos[2], 4)),
                end_position_llh=(round(refuel_end_pos[0], 4), round(refuel_end_pos[1], 4), round(refuel_end_pos[2], 4)),
                range_remaining_before_km=round(max(0.0, range_remaining), 2),
                adjusted=adjusted,
                threat_distance_km=round(threat_dist, 2),
            )
            refuel_list.append(rs)
            # Advance cursor past the entire refuel segment (forward motion)
            cursor_dist = refuel_end_dist
            range_left = range_full

        key = f"{platform_id}->{target_id}"
        output[key] = refuel_list

    return output

def main():
    from .io import dump_data, load_data, load_scenario

    parser = argparse.ArgumentParser(
        description="路径加油点计算 — 在路径结果中追加加油点"
    )
    parser.add_argument(
        "-t", "--trajectory", required=True, help="路径规划结果 JSON (attack 或 return_plan 输出)"
    )
    parser.add_argument(
        "-s", "--scenario", required=True, help="场景 JSON (包含 platforms/threats/no_fly_zones/planning)"
    )
    parser.add_argument(
        "-o", "--output", default=None, help="输出目录 (默认: output/{场景名}_refuel_result/)"
    )
    args = parser.parse_args()

    # 加载默认配置
    defaults_path = Path(__file__).resolve().parent / "input" / "_defaults.json"
    defaults = load_data(str(defaults_path)) if defaults_path.exists() else {}

    print(f"读取路径结果: {args.trajectory}")
    result_data = load_data(args.trajectory)

    results = result_data.get("results", [])
    if not results:
        print("警告: 结果文件中没有 results 列表")
        sys.exit(1)

    print(f"  共 {len(results)} 条路径")

    print(f"读取场景: {args.scenario}")
    scenario = load_scenario(args.scenario, defaults)

    platforms = {p.id: p for p in scenario.platforms}
    print(f"  平台数: {len(platforms)}")
    print(
        f"  威胁场: {len(scenario.threat_field.spheres)} 球体, "
        f"{len(scenario.threat_field.cones)} 圆锥体, "
        f"{len(scenario.threat_field.cylinders)} 圆柱体, "
        f"{len(scenario.threat_field.elliptic_cylinders)} 椭圆柱体, "
        f"{len(scenario.threat_field.no_fly_zones)} 禁飞区"
    )

    config = RefuelConfig(safe_distance_km=5.0)
    print("\n计算加油段 (安全距离=5.0km, 前向飞行)...")

    refuel_map = calculate_refuel_segments(
        results, platforms, scenario.threat_field, config
    )

    refuel_count = 0
    for result in results:
        key = f"{result['platform']}->{result['target']}"
        segments = refuel_map.get(key, [])
        if segments:
            result["refuel_segments"] = [
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
                for rs in segments
            ]
            refuel_count += len(segments)
            print(f"  {key}: {len(segments)} 个加油段")
        else:
            result["refuel_segments"] = []
            waypoints = result.get("waypoints", [])
            platform = platforms.get(result.get("platform", ""))
            range_km = getattr(platform, "range_km", 0.0) if platform else 0.0
            total_dist = _build_cumulative_distances(waypoints)[-1] if len(waypoints) >= 2 else 0.0
            if range_km <= 0:
                print(f"  {key}: 无航程数据，跳过")
            elif total_dist <= range_km:
                print(f"  {key}: 无需加油段 (航程 {range_km:.0f}km ≥ 路径 {total_dist:.0f}km)")
            else:
                print(f"  {key}: 无法放置加油段 (路径 {total_dist:.0f}km > 航程 {range_km:.0f}km，无安全位置)")

    print(f"\n总计: {refuel_count} 个加油段")

    if args.output:
        output_dir = Path(args.output)
    else:
        output_dir = (
            Path(__file__).resolve().parent.parent
            / "output"
            / f"{scenario.name}_refuel_result"
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    input_ext = Path(args.trajectory).suffix.lower()
    result_ext = input_ext if input_ext in (".json", ".yaml", ".yml") else ".yaml"
    output_path = str(output_dir / f"result{result_ext}")
    dump_data(result_data, output_path)
    print(f"\n结果已写入: {output_path}")

    # 生成 2D 可视化
    try:
        from .grid import build_grid
        from .io import PathResult

        all_points = [p.position_llh for p in platforms.values()]
        for t in scenario.targets:
            all_points.append(t.position_llh)
        grid = build_grid(
            all_points,
            scenario.planner_config.grid,
            scenario.ref_lon,
            scenario.ref_lat,
        )
        grid.precompute_threat(scenario.threat_field)

        path_objects = []
        for result_item in results:
            wps = result_item.get("waypoints", [])
            if not wps:
                continue
            try:
                pr = PathResult(
                    platform_id=result_item.get("platform", ""),
                    target_id=result_item.get("target", ""),
                    direction=tuple(result_item.get("direction", [0, 0])),
                    cost=result_item.get("cost", 0),
                    threat_exposure=result_item.get("threat_exposure", 0),
                    waypoints_llh=[tuple(w) for w in wps],
                    arrival_angle=tuple(result_item.get("arrival_angle", [0, 0])),
                )
                path_objects.append(pr)
            except Exception:
                pass

        from .viz.plot_2d import plot_scenario

        plot_output = str(output_dir / "2d.png")
        plot_scenario(
            scenario,
            grid,
            path_objects,
            plot_output,
            title=f"{scenario.name} — 加油点 (安全距离=5.0km)",
            refuel_segments_map=refuel_map,
        )
        print(f"  轨迹图已保存: {plot_output}")
    except ImportError as e:
        print(f"  2D 可视化跳过: {e}")



if __name__ == "__main__":
    raise SystemExit(main())
