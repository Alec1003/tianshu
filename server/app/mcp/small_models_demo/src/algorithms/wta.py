"""WTA 武器-目标分配（MILP + Monte Carlo 验证）.

用法:
    python algorithms/wta.py -c config.json -o result.json
    python algorithms/wta.py -c config.json -o result.json --mc-trials 5000
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from src.algorithms._utils import BASE_DIR, WTA_DEFAULTS, deep_merge


def run(config: dict[str, Any], mc_trials: int = 5000, output_path: str = "output/wta_result.json") -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        scenario_path = tmpdir_path / "scenario.json"
        output_dir = tmpdir_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        merged = deep_merge(WTA_DEFAULTS, config)
        scenario_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

        subprocess.run(
            [sys.executable, "-m", "wta.allocator", "--config", str(scenario_path), "--output", str(output_dir), "--mc-trials", str(mc_trials)],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )

        plan_path = output_dir / "plan.json"
        result = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else {}

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="WTA 武器-目标分配")
    parser.add_argument("-c", "--config", required=True, help="场景配置 JSON/YAML 文件路径")
    parser.add_argument("-o", "--output", default="output/wta_result.json", help="结果输出路径")
    parser.add_argument("--mc-trials", type=int, default=5000, help="MC 仿真次数 (默认 5000)")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    result = run(config, args.mc_trials, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
