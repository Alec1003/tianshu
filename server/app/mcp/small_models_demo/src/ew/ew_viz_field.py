#!/usr/bin/env python3
"""
SNR 缩放因子场可视化.

用法:
  python ew/ew_viz_field.py ew/ew_example_input.pkl
  python ew/ew_viz_field.py ew/ew_example_input.pkl -o output.png
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ew.ew_jamming_field import plot_jamming_from_pkl


def main():
    parser = argparse.ArgumentParser(description="EW SNR 缩放因子场可视化 (从 pickle)")
    parser.add_argument("pkl", help="pickle 文件路径")
    parser.add_argument("-o", "--output", help="输出图片路径", default=None)
    args = parser.parse_args()

    plot_jamming_from_pkl(args.pkl, output_path=args.output)


if __name__ == "__main__":
    main()
