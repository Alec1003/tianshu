"""Mode 1 攻击路径规划 — 强制所有 pair 使用 mode=1."""

import sys
import tempfile
from pathlib import Path


def main():
    import argparse

    from .io import dump_data, load_data

    parser = argparse.ArgumentParser(description="Mode 1 攻击路径规划")
    parser.add_argument("scenario", help="场景 YAML / JSON 文件路径")
    parser.add_argument("-o", "--output", default=None, help="输出目录 (默认: output/{场景名}_result/")
    args = parser.parse_args()

    data = load_data(args.scenario)
    scenario = data.get("scenario", data)
    for pair in scenario.get("pairs", []):
        pair["mode"] = 1

    ext = Path(args.scenario).suffix
    with tempfile.NamedTemporaryFile(mode="w", suffix=ext, delete=False, encoding="utf-8") as f:
        dump_data(data, f.name)
        temp_path = f.name

    sys.argv = ["route_plan.attack", temp_path]
    if args.output:
        sys.argv.extend(["-o", args.output])

    try:
        from .attack import main as attack_main

        attack_main()
    finally:
        Path(temp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
