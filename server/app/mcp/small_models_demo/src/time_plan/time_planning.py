#!/usr/bin/env python3
"""
时间排程 — 基于 route_plan 增强输出生成每单元的阶段时间表。

原则:
- 路径相关数据 (距离/速度/汇合点/加油点) 全部来自 route_plan 输出
- 时间相关参数 (start_time, refuel duration) 由 time_plan 配置
- time_plan 不重算任何距离

用法:
    python3 -m src.time_plan.time_planning time_config.yaml \
        -r output/test/result.yaml -o output/test/schedule.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.route_plan.io import load_data

EPS = 1e-6
TIME_TOLERANCE_SEC = 1e-3


def parse_iso_time(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def format_iso_time(dt: datetime) -> str:
    return dt.isoformat()


def duration_sec(distance_km: float, speed_kmh: float) -> float:
    if speed_kmh <= EPS:
        return float("inf")
    return distance_km / speed_kmh * 3600.0


def _find_closest_waypoint_index(
    waypoints: List[List[float]], target: List[float]
) -> int:
    best_idx = 0
    best_dist = float("inf")
    for i, wp in enumerate(waypoints):
        dlat = wp[0] - target[0]
        dlon = wp[1] - target[1]
        dist = dlat * dlat + dlon * dlon
        if dist < best_dist:
            best_dist = dist
            best_idx = i
    return best_idx


def _stage_entry(
    stage: str,
    start: datetime,
    end: datetime,
    distance_km: Optional[float] = None,
    speed_kmh: Optional[float] = None,
    position: Optional[List[float]] = None,
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "stage": stage,
        "start_time": format_iso_time(start),
        "end_time": format_iso_time(end),
        "duration_sec": round((end - start).total_seconds(), 3),
    }
    if distance_km is not None:
        entry["distance_km"] = round(distance_km, 4)
    if speed_kmh is not None:
        entry["speed_kmh"] = round(speed_kmh, 1)
    if position is not None:
        entry["position"] = [round(v, 4) for v in position]
    return entry


def _extract_unit(unit: Dict[str, Any]) -> Dict[str, Any]:
    """Extract timing-relevant fields from one enriched result entry."""
    platform_speed_kmh = float(unit.get("platform_speed_kmh", 0))
    weapon_speed_kmh = float(unit.get("weapon_speed_kmh", 0))
    target_distance_km = float(unit.get("target_distance_km", 0))
    cum_dist = unit.get("cumulative_distances_km", [])
    waypoints = unit.get("waypoints", [])
    meet_point = unit.get("meet_point")
    meet_point_id = unit.get("meet_point_id", "")
    refuel_segments = unit.get("refuel_segments", [])

    has_weapon = weapon_speed_kmh > 0 and target_distance_km > 0
    has_meet = bool(meet_point) and bool(meet_point_id)

    # Find meet point index
    meet_idx: Optional[int] = None
    if has_meet and waypoints:
        meet_idx = _find_closest_waypoint_index(waypoints, meet_point)

    # Distances split by meet point
    if has_meet and meet_idx is not None and cum_dist:
        dist_to_meet = cum_dist[meet_idx]
        dist_after_meet = cum_dist[-1] - cum_dist[meet_idx]
    else:
        dist_to_meet = 0.0
        dist_after_meet = cum_dist[-1] if cum_dist else 0.0

    # Refuel segments
    refuel_list: List[Dict[str, Any]] = []
    for rs in refuel_segments:
        refuel_list.append({
            "start_distance_km": float(rs.get("start_distance_km", 0)),
            "end_distance_km": float(rs.get("end_distance_km", 0)),
            "refuel_distance_km": float(rs.get("refuel_distance_km", 0)),
            "refuel_speed_kmh": float(rs.get("refuel_speed_kmh", platform_speed_kmh)),
            "start_position": rs.get("start_position"),
            "end_position": rs.get("end_position"),
        })

    return {
        "unit_id": unit.get("platform", ""),
        "unit_type": unit.get("platform_type", ""),
        "unit_cls": unit.get("platform_cls", ""),
        "target_id": unit.get("target", ""),
        "reachable": True,
        "speed_kmh": platform_speed_kmh,
        "weapon_speed_kmh": weapon_speed_kmh,
        "has_weapon": has_weapon,
        "has_meet": has_meet,
        "meet_point_id": meet_point_id,
        "meet_idx": meet_idx,
        "dist_to_meet": dist_to_meet,
        "dist_after_meet": dist_after_meet,
        "target_distance_km": target_distance_km,
        "path_length_km": float(unit.get("path_length_km", 0)),
        "refuels": refuel_list,
    }


def _build_move_segments(u: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build ordered list of move/refuel segments. Refuel is a move segment
    flown at refuel_speed_kmh (forward motion during aerial refueling)."""
    segments: List[Dict[str, Any]] = []

    # Gather split points: meet + refuel boundaries, sorted by distance
    split_points: List[tuple] = []  # (distance_km, kind, data)

    if u["has_meet"] and u["dist_to_meet"] > EPS:
        split_points.append((u["dist_to_meet"], "meet", {}))

    for r in u["refuels"]:
        split_points.append((r["start_distance_km"], "refuel_begin", r))
        split_points.append((r["end_distance_km"], "refuel_end", r))

    split_points.sort(key=lambda x: x[0])

    cursor_dist = 0.0
    current_speed = u["speed_kmh"]

    if u["has_meet"]:
        label_prefix = "move_to_meet"
    elif u["has_weapon"]:
        label_prefix = "move_to_attack_point"
    else:
        label_prefix = "flight"

    prev_label = label_prefix

    in_refuel = False
    for dist, kind, data in split_points:
        if dist - cursor_dist > EPS:
            segments.append({
                "kind": "move",
                "label": label_prefix,
                "distance_km": dist - cursor_dist,
                "speed_kmh": current_speed,
                "duration_sec": duration_sec(dist - cursor_dist, current_speed),
            })
        cursor_dist = dist

        if kind == "meet":
            if in_refuel:
                # Meet during refuel: update saved label for post-refuel switch
                prev_label = "move_to_attack_point"
            else:
                label_prefix = "move_to_attack_point"
        elif kind == "refuel_begin":
            in_refuel = True
            prev_label = label_prefix
            label_prefix = "refuel"
            current_speed = data["refuel_speed_kmh"]
        elif kind == "refuel_end":
            in_refuel = False
            label_prefix = prev_label
            current_speed = u["speed_kmh"]

    # Final move to end
    total_path = u["dist_to_meet"] + u["dist_after_meet"]
    if total_path - cursor_dist > EPS:
        final_label = "flight" if not u["has_weapon"] else label_prefix
        segments.append({
            "kind": "move",
            "label": final_label,
            "distance_km": total_path - cursor_dist,
            "speed_kmh": current_speed,
            "duration_sec": duration_sec(total_path - cursor_dist, current_speed),
        })

    # Weapon attack phase
    if u["has_weapon"]:
        segments.append({
            "kind": "weapon",
            "label": "weapon_attack",
            "distance_km": u["target_distance_km"],
            "speed_kmh": u["weapon_speed_kmh"],
            "duration_sec": duration_sec(u["target_distance_km"], u["weapon_speed_kmh"]),
        })

    # Merge consecutive move segments with same label and speed
    merged: List[Dict[str, Any]] = []
    for seg in segments:
        if seg["kind"] != "move":
            merged.append(seg)
            continue
        if merged and merged[-1]["kind"] == "move" \
                and merged[-1]["label"] == seg["label"] \
                and abs(merged[-1]["speed_kmh"] - seg["speed_kmh"]) < EPS:
            merged[-1]["distance_km"] += seg["distance_km"]
            merged[-1]["duration_sec"] += seg["duration_sec"]
        else:
            merged.append(seg)
    # Drop move segments with negligible duration (< 0.5s)
    segments = [s for s in merged if s.get("duration_sec", 0) > 0.5 or s["kind"] != "move"]

    if not segments:
        segments.append({
            "kind": "move",
            "label": "flight",
            "distance_km": 0.0,
            "speed_kmh": u["speed_kmh"],
            "duration_sec": 0.0,
        })

    return segments


def _compute_timing(u: Dict[str, Any]) -> Dict[str, float]:
    """Compute durations accounting for refuel segments at different speeds.

    Cruise portions use speed_kmh; refuel portions use refuel_speed_kmh.
    """
    t = {}

    # Start with all distance at cruise speed, then adjust for refuel segments
    cruise_dist_to_meet = u["dist_to_meet"]
    cruise_dist_after_meet = u["dist_after_meet"]

    t["refuel_before_meet"] = 0.0
    t["refuel_after_meet"] = 0.0

    for r in u["refuels"]:
        rs = r["start_distance_km"]
        re = r["end_distance_km"]
        rd = r["refuel_distance_km"]
        refuel_dur = duration_sec(rd, r["refuel_speed_kmh"])

        if u["has_meet"] and u["meet_idx"] is not None:
            meet_d = u["dist_to_meet"]
            if re <= meet_d + EPS:
                # Entirely before meet
                cruise_dist_to_meet -= rd
                t["refuel_before_meet"] += refuel_dur
            elif rs >= meet_d - EPS:
                # Entirely after meet
                cruise_dist_after_meet -= rd
                t["refuel_after_meet"] += refuel_dur
            else:
                # Straddles meet point: split proportionally
                before_dist = meet_d - rs
                before_frac = before_dist / rd
                cruise_dist_to_meet -= before_dist
                cruise_dist_after_meet -= (rd - before_dist)
                t["refuel_before_meet"] += refuel_dur * before_frac
                t["refuel_after_meet"] += refuel_dur * (1.0 - before_frac)
        else:
            cruise_dist_after_meet -= rd
            t["refuel_after_meet"] += refuel_dur

    t["travel_to_meet"] = duration_sec(max(0, cruise_dist_to_meet), u["speed_kmh"])
    t["travel_after_meet"] = duration_sec(max(0, cruise_dist_after_meet), u["speed_kmh"])

    t["weapon"] = (
        duration_sec(u["target_distance_km"], u["weapon_speed_kmh"])
        if u["has_weapon"]
        else 0.0
    )

    t["pre_meet"] = t["travel_to_meet"] + t["refuel_before_meet"]
    t["post_meet"] = t["travel_after_meet"] + t["refuel_after_meet"] + t["weapon"]
    t["total"] = t["pre_meet"] + t["post_meet"]

    return t


def time_planning(
    route_result: Dict[str, Any],
    time_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate per-unit stage timelines from enriched route_plan output."""
    start_time = parse_iso_time(time_config["start_time"])

    results = route_result.get("results", [])
    if not results:
        return {"error": "route_plan result 中没有 results 列表"}

    # Phase 1: Extract unit data
    units = [_extract_unit(r) for r in results]

    # Phase 2: Build move segments for each unit
    for u in units:
        u["_segments"] = _build_move_segments(u)

    # Phase 3: Compute per-unit timing
    for u in units:
        u["_timing"] = _compute_timing(u)

    # Phase 4: Compute meet-point sync
    meet_groups: Dict[str, List[Dict[str, Any]]] = {}
    for u in units:
        if u["has_meet"]:
            meet_groups.setdefault(u["meet_point_id"], []).append(u)

    meet_offsets: Dict[str, float] = {}
    for mid, group in meet_groups.items():
        meet_offsets[mid] = max(u["_timing"]["pre_meet"] for u in group)

    # Phase 5: Compute global hit offset
    unit_hit_offsets: List[float] = []
    for u in units:
        if u["has_meet"]:
            offset = meet_offsets[u["meet_point_id"]] + u["_timing"]["post_meet"]
        else:
            offset = u["_timing"]["total"]
        unit_hit_offsets.append(offset)

    global_hit_offset = max(unit_hit_offsets) if unit_hit_offsets else 0.0
    global_hit_time = start_time + timedelta(seconds=global_hit_offset)

    # Phase 6: Build stage timelines (two-pass to minimize standby)
    unit_schedules: List[Dict[str, Any]] = []
    constraint_violations: List[str] = []

    # --- Pass 1: compute initial wait and standby for each unit ---
    unit_initial: List[Dict[str, Any]] = []
    for i, u in enumerate(units):
        segs = u["_segments"]
        timing = u["_timing"]

        # Find weapon segment
        weapon_seg = None
        for seg in segs:
            if seg["kind"] == "weapon":
                weapon_seg = seg
                break

        # Wait at start
        if u["has_meet"]:
            meet_offset = meet_offsets[u["meet_point_id"]]
            wait_sec = max(0.0, meet_offset - timing["pre_meet"])
        else:
            wait_sec = max(0.0, global_hit_offset - timing["total"])

        # Standby before weapon launch
        standby_sec = 0.0
        if weapon_seg:
            weapon_launch_offset = global_hit_offset - weapon_seg["duration_sec"]
            current_offset = wait_sec + timing["total"] - timing["weapon"]
            standby_sec = max(0.0, weapon_launch_offset - current_offset)

        unit_initial.append({
            "u": u,
            "segs": segs,
            "timing": timing,
            "weapon_seg": weapon_seg,
            "wait_sec": wait_sec,
            "standby_sec": standby_sec,
        })

    # --- Pass 2: compute extra wait to minimize standby ---
    # For non-meet units: convert all standby to wait at start
    # For meet units: shared extra = min(standby in group), so all stay synced
    extra_wait_by_unit: Dict[int, float] = {}
    meet_group_extra: Dict[str, float] = {}

    # First, compute meet group minimum standbys
    for mid, group in meet_groups.items():
        group_indices = [units.index(m) for m in group]
        group_standbys = [unit_initial[idx]["standby_sec"] for idx in group_indices]
        meet_group_extra[mid] = min(group_standbys)

    # Then assign extra wait per unit
    for i, ui in enumerate(unit_initial):
        u = ui["u"]
        if u["has_meet"]:
            extra_wait_by_unit[i] = meet_group_extra.get(u["meet_point_id"], 0.0)
        else:
            extra_wait_by_unit[i] = ui["standby_sec"]

    # --- Pass 3: build timeline with adjusted waits ---
    for i, ui in enumerate(unit_initial):
        u = ui["u"]
        segs = ui["segs"]
        timing = ui["timing"]
        weapon_seg = ui["weapon_seg"]
        extra = extra_wait_by_unit[i]
        wait_sec = ui["wait_sec"] + extra
        standby_sec = max(0.0, ui["standby_sec"] - extra)

        # Build timeline
        stages: List[Dict[str, Any]] = []
        current_time = start_time

        # Wait
        if wait_sec > TIME_TOLERANCE_SEC:
            end_wait = current_time + timedelta(seconds=wait_sec)
            stages.append(_stage_entry("wait", current_time, end_wait))
            current_time = end_wait

        # Process each segment
        for seg in segs:
            if seg["kind"] == "weapon":
                weapon_seg = seg
                continue
            if seg["kind"] == "move":
                end_time = current_time + timedelta(seconds=seg["duration_sec"])
                stages.append(
                    _stage_entry(
                        seg["label"],
                        current_time,
                        end_time,
                        seg.get("distance_km"),
                        seg.get("speed_kmh"),
                        position=seg.get("start_position"),
                    )
                )
                current_time = end_time

        # Standby + weapon
        if weapon_seg:
            if standby_sec > TIME_TOLERANCE_SEC:
                standby_end = current_time + timedelta(seconds=standby_sec)
                stages.append(_stage_entry("standby", current_time, standby_end))
                current_time = standby_end

            weapon_end = current_time + timedelta(seconds=weapon_seg["duration_sec"])
            stages.append(
                _stage_entry(
                    "weapon_attack",
                    current_time,
                    weapon_end,
                    weapon_seg["distance_km"],
                    weapon_seg["speed_kmh"],
                )
            )
            hit_time = weapon_end
        else:
            hit_time = current_time

        total_dur = (hit_time - start_time).total_seconds()

        # For aircraft with weapon, add a zero-duration 武器命中 marker
        if weapon_seg:
            stages.append(_stage_entry("weapon_hit", hit_time, hit_time))

        unit_schedules.append({
            "unit_id": u["unit_id"],
            "unit_type": u["unit_type"],
            "unit_cls": u["unit_cls"],
            "target_id": u["target_id"],
            "reachable": u["reachable"],
            "stage_timeline": stages,
            "hit_time": format_iso_time(hit_time),
            "total_duration_sec": round(total_dur, 3),
        })

    # Phase 7: Sync summary
    sync_summary: Dict[str, Any] = {
        "start_time": format_iso_time(start_time),
        "global_hit_time": format_iso_time(global_hit_time),
    }
    for mid, offset in meet_offsets.items():
        extra = meet_group_extra.get(mid, 0.0)
        sync_summary[f"meet_time_{mid}"] = format_iso_time(
            start_time + timedelta(seconds=offset + extra)
        )

    constraints_satisfied = len(constraint_violations) == 0
    for u in units:
        if not u["reachable"]:
            constraints_satisfied = False
            constraint_violations.append(f"{u['unit_id']} 不可达")

    return {
        "unit_schedules": unit_schedules,
        "sync_summary": sync_summary,
        "constraints_satisfied": constraints_satisfied,
        "constraint_violations": constraint_violations,
    }


STAGE_COLORS = {
    "wait": "#d9d9d9",
    "move_to_meet": "#4c72b0",
    "refuel": "#dd8452",
    "move_to_attack_point": "#55a868",
    "standby": "#f0e442",
    "weapon_attack": "#c44e52",
    "weapon_hit": "#c44e52",
    "flight": "#64b5cd",
}

SYNC_LINE_STYLE = dict(linestyle="--", linewidth=1, alpha=0.8)


def _plot_gantt(result: Dict[str, Any], output_path: str) -> None:
    """Generate a Gantt chart from the time_planning result."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm

    # Find a font that supports Chinese
    from pathlib import Path as _Path
    zh_font = None
    # macOS system fonts
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for fp in candidates:
        if _Path(fp).exists():
            zh_font = fp
            break
    if not zh_font:
        try:
            zh_font = fm.findfont("PingFang SC", fallback_to_default=False)
        except Exception:
            pass
    if not zh_font:
        zh_font = fm.findfont("sans-serif", fallback_to_default=True)

    font_prop = fm.FontProperties(fname=zh_font) if zh_font else None

    schedules = result["unit_schedules"]
    sync = result["sync_summary"]

    unit_ids = [s["unit_id"] for s in schedules]
    n_units = len(unit_ids)

    # Find global time range
    t_min = None
    t_max = None
    for s in schedules:
        for stage in s["stage_timeline"]:
            st = parse_iso_time(stage["start_time"])
            et = parse_iso_time(stage["end_time"])
            if t_min is None or st < t_min:
                t_min = st
            if t_max is None or et > t_max:
                t_max = et

    if t_min is None or t_max is None:
        return

    # Add margin
    margin = (t_max - t_min).total_seconds() * 0.02
    t_min = t_min - timedelta(seconds=margin)
    t_max = t_max + timedelta(seconds=margin)

    fig, ax = plt.subplots(figsize=(16, max(4, n_units * 0.8)))

    # Draw bars for each unit
    y_positions = list(range(n_units))
    bar_height = 0.6

    STAGE_LABEL_MAP = {
        "wait": "等待",
        "move_to_meet": "飞往集合点",
        "refuel": "加油",
        "move_to_attack_point": "飞往攻击阵位",
        "standby": "待命",
        "weapon_attack": "发射武器",
        "weapon_hit": "武器命中",
        "flight": "飞行",
    }

    for i, schedule in enumerate(schedules):
        y = y_positions[i]
        first_start = None  # for showing time from start
        for stage in schedule["stage_timeline"]:
            stage_name = stage["stage"]
            st = parse_iso_time(stage["start_time"])
            et = parse_iso_time(stage["end_time"])
            dur_sec = (et - st).total_seconds()
            dur_days = dur_sec / 86400.0
            if first_start is None:
                first_start = st

            if dur_sec <= 0:
                continue

            color = STAGE_COLORS.get(stage_name, "#aaaaaa")
            ax.barh(y, dur_days, bar_height, left=st,
                    color=color, edgecolor="white", linewidth=0.5)

            # Build label: stage name + seconds + optional distance
            zh_name = STAGE_LABEL_MAP.get(stage_name, stage_name)
            dist = stage.get("distance_km")
            if dist is not None and dist > 0:
                text = f"{zh_name} {int(dur_sec)}s\n{dist:.0f}km"
            else:
                text = f"{zh_name} {int(dur_sec)}s"

            # Place text inside bar if wide enough, otherwise to the right
            mid_time = st + timedelta(seconds=dur_sec / 2)
            # Approximate text width in data coordinates: 6pt char ≈ 0.08 inch
            total_range_days = (t_max - t_min).total_seconds() / 86400.0
            fig_width_inch = fig.get_size_inches()[0]
            char_width_days = total_range_days / fig_width_inch * 0.08
            text_width_est = len(text) * char_width_days * 1.1
            if dur_days > text_width_est * 1.3:
                ax.text(mid_time, y, text, ha="center", va="center",
                        fontsize=6, color="white", fontweight="bold",
                        fontproperties=font_prop)
            else:
                ax.text(et + timedelta(seconds=5), y, text,
                        ha="left", va="center", fontsize=6, color="#333333",
                        fontproperties=font_prop)

        # Hit marker at end of each row
        if schedule["stage_timeline"]:
            last_end = parse_iso_time(schedule["stage_timeline"][-1]["end_time"])
            ax.text(last_end + timedelta(seconds=5), y, "命中",
                    ha="left", va="center", fontsize=7, color="#c44e52",
                    fontweight="bold", fontproperties=font_prop)

    # Sync vertical lines
    y_min_line = -0.8
    y_max_line = n_units - 0.2

    # Global hit time
    hit_time = parse_iso_time(sync["global_hit_time"])
    ax.axvline(x=hit_time, color="#c44e52", **SYNC_LINE_STYLE)
    ax.text(hit_time, y_max_line + 0.3, "命中",
            ha="center", va="bottom", fontsize=9, color="#c44e52",
            fontweight="bold", fontproperties=font_prop)

    # Meet times
    for k, v in sync.items():
        if k.startswith("meet_time_"):
            mt = parse_iso_time(v)
            meet_label = k.replace("meet_time_", "汇合:")
            ax.axvline(x=mt, color="#4c72b0", **SYNC_LINE_STYLE)
            ax.text(mt, y_max_line + 0.3, meet_label,
                    ha="center", va="bottom", fontsize=7, color="#4c72b0",
                    fontproperties=font_prop)

    # Start time
    start_t = parse_iso_time(sync["start_time"])
    ax.axvline(x=start_t, color="black", **SYNC_LINE_STYLE)

    ax.set_yticks(y_positions)
    ax.set_yticklabels(unit_ids, fontsize=9, fontproperties=font_prop)
    ax.set_ylim(y_min_line, y_max_line + 0.8)
    ax.set_xlim(t_min, t_max)
    ax.invert_yaxis()

    # X-axis time formatting
    import matplotlib.dates as mdates
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=8)

    ax.set_xlabel("Time (UTC)", fontsize=10)
    ax.set_title("Time Plan — Gantt", fontsize=12, fontweight="bold")

    ax.grid(True, axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(
        description="时间排程 — 基于 route_plan 增强输出"
    )
    parser.add_argument(
        "time_config",
        help="时间配置文件 (YAML/JSON)，包含 start_time 和可选的 refuel 配置",
    )
    parser.add_argument(
        "-r",
        "--route-result",
        required=True,
        help="route_plan 增强输出文件 (result.yaml/json)",
    )
    parser.add_argument(
        "-o", "--output", default=None, help="输出文件目录 (默认 stdout)"
    )
    args = parser.parse_args()

    print(f"读取时间配置: {args.time_config}")
    time_config = load_data(args.time_config)
    if not time_config:
        print("错误: 时间配置为空")
        sys.exit(1)
    if "start_time" not in time_config:
        print("错误: 时间配置缺少 start_time")
        sys.exit(1)

    print(f"  任务开始时间: {time_config['start_time']}")

    print(f"读取路径结果: {args.route_result}")
    route_result = load_data(args.route_result)
    results = route_result.get("results", [])
    if not results:
        print("错误: route_plan result 中没有 results 列表")
        sys.exit(1)

    print(f"  共 {len(results)} 条路径")
    for r in results:
        pid = r.get("platform", "?")
        tid = r.get("target", "?")
        dist = r.get("path_length_km", 0)
        speed = r.get("platform_speed_kmh", 0)
        weapon = r.get("weapon_speed_kmh", 0)
        meet = r.get("meet_point_id", "")
        refuel_n = len(r.get("refuel_segments", []))
        print(
            f"    {pid} -> {tid}: path={dist:.1f}km, "
            f"speed={speed:.0f}km/h, weapon_speed={weapon:.0f}km/h, meet={meet or '-'}, "
            f"refuels={refuel_n}"
        )

    print("\n计算时间排程...")
    result = time_planning(route_result, time_config)

    if "error" in result:
        print(f"错误: {result['error']}")
        sys.exit(1)

    n_stages = sum(len(s["stage_timeline"]) for s in result["unit_schedules"])
    print(f"  共 {len(result['unit_schedules'])} 个单元, {n_stages} 个阶段")
    print(f"  约束满足: {result['constraints_satisfied']}")
    if result.get("constraint_violations"):
        for v in result["constraint_violations"]:
            print(f"    ⚠ {v}")

    sync = result["sync_summary"]
    print(f"  全局命中时间: {sync['global_hit_time']}")
    for k, v in sync.items():
        if k.startswith("meet_time_"):
            print(f"  汇合时间 ({k}): {v}")

    # Write JSON
    if args.output:
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        schedule_path = str(output_dir / "schedule.json")
        json_text = json.dumps(result, ensure_ascii=False, indent=2)
        Path(schedule_path).write_text(json_text + "\n", encoding="utf-8")
        print(f"\n结果已写入: {schedule_path}")

        # Gantt chart
        gantt_path = str(output_dir / "gantt.png")
        try:
            _plot_gantt(result, gantt_path)
            print(f"甘特图已保存: {gantt_path}")
        except Exception as e:
            print(f"甘特图生成失败: {e}")
    else:
        print("\n" + json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
