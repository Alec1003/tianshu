"""Monte Carlo 仿真：验证 WTA 分配方案在随机命中条件下的毁伤达标概率.

用法:
    python algorithms/monte_carlo.py -c config.json -p plan.json -o result.json
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


def run(
    config: dict[str, Any],
    plan: dict[str, Any],
    mc_trials: int = 5000,
    seed: int = 42,
    output_path: str = "output/mc_result.json",
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        scenario_path = tmpdir_path / "scenario.json"
        plan_path = tmpdir_path / "plan.json"
        result_path = tmpdir_path / "result.json"

        merged = deep_merge(WTA_DEFAULTS, config)
        scenario_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

        subprocess.run(
            [
                sys.executable, "-m", "wta.monte_carlo",
                "--config", str(scenario_path),
                "--plan", str(plan_path),
                "--trials", str(mc_trials),
                "--seed", str(seed),
                "--output", str(result_path),
            ],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )

        result = json.loads(result_path.read_text(encoding="utf-8"))

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Monte Carlo 仿真")
    parser.add_argument("-c", "--config", required=True, help="场景配置 JSON 文件路径")
    parser.add_argument("-p", "--plan", required=True, help="WTA 分配方案 JSON 文件路径")
    parser.add_argument("-o", "--output", default="output/mc_result.json", help="结果输出路径")
    parser.add_argument("--mc-trials", type=int, default=5000, help="仿真次数 (默认 5000)")
    parser.add_argument("--seed", type=int, default=42, help="随机种子 (默认 42)")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    result = run(config, plan, args.mc_trials, args.seed, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
