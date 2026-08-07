"""攻击路径规划 — Mode 3：以目标为圆心生成攻击点候选，路径以候选攻击点为终点.

用法:
    python algorithms/route_mode3.py -c scenario.json -o result.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from src.algorithms._utils import BASE_DIR, ROUTE_DEFAULTS, deep_merge


def run(scenario: dict[str, Any], output_path: str = "output/route_mode3_result.json") -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        scenario_path = tmpdir_path / "scenario.json"
        output_dir = tmpdir_path / "output"

        merged = deep_merge(ROUTE_DEFAULTS, scenario)
        scenario_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

        completed = subprocess.run(
            [sys.executable, "-m", "src.route_plan.attack3", str(scenario_path), "-o", str(output_dir)],
            cwd=str(BASE_DIR),
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
    parser = argparse.ArgumentParser(description="攻击路径规划 — Mode 3")
    parser.add_argument("-c", "--config", required=True, help="场景配置 JSON 文件路径")
    parser.add_argument("-o", "--output", default="output/route_mode3_result.json", help="结果输出路径")
    args = parser.parse_args()

    scenario = json.loads(Path(args.config).read_text(encoding="utf-8"))
    result = run(scenario, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
