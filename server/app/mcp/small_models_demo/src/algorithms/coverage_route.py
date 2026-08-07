"""区域覆盖路径规划 — zigzag 扫描 + A* cell 间转移.

用法:
    python algorithms/coverage_route.py -c scenario.json -o result.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# MCP server 在 worker 线程上运行，matplotlib 必须用非交互后端
import matplotlib
matplotlib.use("agg")

from src.algorithms._utils import BASE_DIR


def run(scenario: dict[str, Any], output_path: str = "output/coverage_route_result.json") -> dict[str, Any]:
    """执行覆盖路径规划。

    Args:
        scenario: 场景 dict，格式与 YAML 输入一致 (scenario.platforms, .targets, .no_fly_zones, .pairs)
        output_path: 结果 JSON 输出路径

    Returns:
        {"results": [{platform, target, total_length_km, cells, cell_order, waypoints, segments}],
         "stdout": ""}
    """
    from src.route_plan.region_cover.cell_traversal import (
        CoverageInputPlatform,
        CoverageInputTarget,
        CoverageInputNFZ,
        CoverageInputPair,
        plan_coverage_from_llh,
        load_coverage_scenario,
        write_coverage_results,
    )

    sc = scenario.get("scenario", scenario)

    platforms = []
    for p in sc.get("platforms", []):
        pos = p["position"]
        platforms.append(CoverageInputPlatform(
            id=p["id"],
            position_llh=(pos[0], pos[1], pos[2]),
            detection_radius_km=p.get("detection_radius_km", 5.0),
            speed_ms=p.get("speed", 250.0),
            range_km=p.get("range", 1500.0),
        ))

    targets = []
    for t in sc.get("targets", []):
        targets.append(CoverageInputTarget(
            id=t["id"],
            boundary=[(lon, lat) for lon, lat in t["boundary"]],
        ))

    no_fly_zones = []
    for nfz in sc.get("no_fly_zones", []):
        pos = nfz["position"]
        params = nfz.get("params", {})
        no_fly_zones.append(CoverageInputNFZ(
            id=nfz["id"],
            center_llh=(pos[0], pos[1], pos[2]),
            radius_km=params.get("radius", 10.0),
            height_m=params.get("height", 0.0),
        ))

    pairs = []
    for pr in sc.get("pairs", []):
        pairs.append(CoverageInputPair(
            platform_id=pr.get("platform", pr.get("platform_id", "")),
            target_id=pr.get("target", pr.get("target_id", "")),
        ))

    output_dir = str(Path(output_path).parent / Path(output_path).stem)
    outputs = plan_coverage_from_llh(
        platforms, targets, no_fly_zones, pairs,
        visualize=True, output_dir=output_dir)

    # Serialize results
    result_list = []
    for out in outputs:
        result_list.append({
            "platform": out.platform_id,
            "target": out.target_id,
            "total_length_km": round(out.total_length_km, 2),
            "cells": len(out.cells),
            "cell_order": [c + 1 for c in out.cell_order],
            "waypoints": [[round(v, 4) for v in wp] for wp in out.path_llh],
            "segments": [
                {
                    "type": seg.segment_type,
                    "cell_index": seg.cell_index,
                    "length_km": round(seg.length_km, 2),
                }
                for seg in out.segments
            ],
        })

    result = {"results": result_list, "stdout": ""}

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="区域覆盖路径规划")
    parser.add_argument("-c", "--config", required=True, help="场景配置 JSON 文件路径")
    parser.add_argument("-o", "--output", default="output/coverage_route_result.json", help="结果输出路径")
    args = parser.parse_args()

    scenario = json.loads(Path(args.config).read_text(encoding="utf-8"))
    result = run(scenario, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
