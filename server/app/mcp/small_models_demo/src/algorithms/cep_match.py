"""CEP 精度-弹目匹配：计算武器对目标的安全可用性.

用法:
    python algorithms/cep_match.py -f feature.json -s scenario.json -o result.json
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
    feature: dict[str, Any],
    scenario: dict[str, Any],
    confidence: float | None = None,
    output_path: str = "output/cep_result.json",
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        feature_path = tmpdir_path / "feature.json"
        scenario_path = tmpdir_path / "scenario.json"
        result_path = tmpdir_path / "result.json"

        feature_path.write_text(json.dumps(feature, ensure_ascii=False, indent=2), encoding="utf-8")
        scenario_path.write_text(json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8")

        cmd = [
            sys.executable, "-m", "wta.weapon_target_matching",
            "--feature", str(feature_path),
            "--scenario", str(scenario_path),
            "--output", str(result_path),
        ]
        if confidence is not None:
            cmd.extend(["--confidence", str(confidence)])

        subprocess.run(
            cmd,
            cwd=str(Path(__file__).resolve().parent.parent),
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
    parser = argparse.ArgumentParser(description="CEP 精度-弹目匹配")
    parser.add_argument("-f", "--feature", required=True, help="武器能力配置 JSON 文件路径")
    parser.add_argument("-s", "--scenario", required=True, help="风险场景配置 JSON 文件路径")
    parser.add_argument("-o", "--output", default="output/cep_result.json", help="结果输出路径")
    parser.add_argument("--confidence", type=float, default=None, help="风险置信度 (0~1)")
    args = parser.parse_args()

    feature = json.loads(Path(args.feature).read_text(encoding="utf-8"))
    scenario = json.loads(Path(args.scenario).read_text(encoding="utf-8"))
    result = run(feature, scenario, args.confidence, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
