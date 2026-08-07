"""加油点规划：根据路径轨迹计算加油位置.

用法:
    python algorithms/route_refuel.py -s scenario.json -t trajectory.json -o result.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def run(
    scenario: dict[str, Any],
    trajectory: dict[str, Any],
    output_path: str = "output/route_refuel_result.json",
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        scenario_path = tmpdir_path / "scenario.json"
        trajectory_path = tmpdir_path / "trajectory.json"
        output_dir = tmpdir_path / "output"

        scenario_path.write_text(json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8")
        trajectory_path.write_text(json.dumps(trajectory, ensure_ascii=False, indent=2), encoding="utf-8")

        completed = subprocess.run(
            [
                sys.executable, "-m", "src.route_plan.refuel",
                "-t", str(trajectory_path),
                "-s", str(scenario_path),
                "-o", str(output_dir),
            ],
            cwd=str(Path(__file__).resolve().parent.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if completed.returncode != 0:
            raise RuntimeError(f"subprocess failed\nstderr:\n{completed.stderr}")

        result_json = output_dir / "result.json"
        result = {
            "result": json.loads(result_json.read_text(encoding="utf-8")) if result_json.exists() else {},
            "stdout": completed.stdout,
        }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="加油点规划")
    parser.add_argument("-s", "--scenario", required=True, help="场景配置 JSON 文件路径")
    parser.add_argument("-t", "--trajectory", required=True, help="路径轨迹 JSON 文件路径")
    parser.add_argument("-o", "--output", default="output/route_refuel_result.json", help="结果输出路径")
    args = parser.parse_args()

    scenario = json.loads(Path(args.scenario).read_text(encoding="utf-8"))
    trajectory = json.loads(Path(args.trajectory).read_text(encoding="utf-8"))
    result = run(scenario, trajectory, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
