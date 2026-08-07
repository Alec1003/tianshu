"""不惜代价分配 — 单波次高置信度求解，以最大火力确保摧毁所有目标."""

from __future__ import annotations

import argparse
import json
import logging
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="不惜代价分配 — 单波次高置信度 (waves=1, confidence=0.99)"
    )
    parser.add_argument(
        "--config", default="wta/input/scenario.yaml", help="场景配置路径"
    )
    parser.add_argument("--output", default=None, help="输出目录")
    parser.add_argument("--mc-trials", type=int, default=5000)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")

    config_path = Path(args.config).resolve()
    raw = _load_raw(config_path)

    solver = raw.setdefault("solver", {})
    solver["waves"] = 1
    solver["confidence_level"] = 0.99

    ext = config_path.suffix
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=ext, delete=False, encoding="utf-8"
    )
    _dump_raw(tmp, raw, ext)
    tmp.close()

    from .allocator import run_allocation

    if args.output:
        output_dir = Path(args.output)
    else:
        output_dir = (
            Path(__file__).resolve().parent.parent
            / "output"
            / f"{config_path.stem}_allcost_result"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "plan.json"

    try:
        result = run_allocation(
            config_path=Path(tmp.name),
            output_path=output_path,
            mc_trials=args.mc_trials,
        )
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log.info(f"结果已导出: {output_path}")
        print(f"\n===== 结果摘要 (不惜代价) =====")
        print(f"total_cost={result['total_cost']:.4f}")
        print(f"sorties={len(result['sorties'])}")
        print(f"launches={len(result['launches'])}")
        print(f"p_all_met={result['mc_validation']['p_all_met']:.4f}")
    finally:
        Path(tmp.name).unlink(missing_ok=True)

    return 0


def _load_raw(path: Path) -> dict:
    import yaml as _yaml

    suffix = path.suffix.lower()
    with open(path, encoding="utf-8") as f:
        if suffix == ".json":
            return json.load(f)
        return _yaml.safe_load(f)


def _dump_raw(f, data: dict, ext: str) -> None:
    import yaml as _yaml

    if ext == ".json":
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    else:
        _yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


if __name__ == "__main__":
    raise SystemExit(main())
