#!/usr/bin/env python3
"""
威胁场 3D 可旋转图 — 只画干扰影响的点。

颜色 = 干扰前后 Pd 差 (红=压制效果强, 蓝=弱)
点在干扰后方可见, 直观看到干扰"咬"掉的部分。

用法:
    python3 plot_threat_3d.py --pkl ew_fields.pkl
"""

import sys
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
import matplotlib.pyplot as plt

from src.route_plan.threats import ThreatField, SphereThreat


def sample_jamming_delta(tf_nojam: ThreatField, tf_jam: ThreatField,
                         x_range, y_range, z_range,
                         nx=40, ny=40, nz=15, delta_min=0.05):
    """采样两点云, 返回有干扰影响的点 (delta >= delta_min)."""
    xs = np.linspace(x_range[0], x_range[1], nx)
    ys = np.linspace(y_range[0], y_range[1], ny)
    zs = np.linspace(z_range[0], z_range[1], nz)

    points = []
    for x in xs:
        for y in ys:
            for z in zs:
                pt = (x, y, z)
                pd0 = tf_nojam.total_threat_cost(pt)
                pd1 = tf_jam.total_threat_cost(pt)
                delta = pd0 - pd1
                if delta >= delta_min:
                    points.append((x, y, z, pd0, pd1, delta))

    if not points:
        return np.array([]), np.array([]), np.array([]), np.array([]), np.array([]), np.array([])
    arr = np.array(points)
    return arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3], arr[:, 4], arr[:, 5]


def plot_3d_jam_effect(x, y, z, pd0, pd1, delta, jammer_az,
                       title="Jamming Effect"):
    """3D 点云: 颜色=Pd 降低幅度, 点大小=Pd0 (原来威胁度)."""
    fig = plt.figure(figsize=(14, 10))
    ax = fig.add_subplot(111, projection="3d")

    # 颜色: delta (0→1), 蓝=弱影响, 红=强压制
    colors = plt.cm.Reds(delta / max(delta.max(), 0.01))

    # 大小: 原来 Pd₀ 高 = 大点
    sizes = np.clip(pd0 * 40, 5, 30)

    scatter = ax.scatter(x, y, z, c=colors, s=sizes, alpha=0.5,
                         edgecolors="none")

    # 雷达
    ax.scatter([0], [0], [0.05], c="blue", s=200, marker="s",
               edgecolors="black", linewidth=1, label="Radar", zorder=10)

    # 干扰机方向
    if jammer_az is not None:
        r_arrow = max(np.ptp(x), np.ptp(y)) * 0.85
        dx = r_arrow * math.sin(math.radians(jammer_az))
        dy = r_arrow * math.cos(math.radians(jammer_az))
        ax.quiver(0, 0, 0, dx, dy, 0, color="black", linewidth=3,
                  arrow_length_ratio=0.12,
                  label=f"Jammer (az={jammer_az:.0f}°)", zorder=10)

    ax.set_xlabel("East (km)")
    ax.set_ylabel("North (km)")
    ax.set_zlabel("Up (km)")
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.legend(loc="upper left", fontsize=8)

    # 等轴
    max_range = max(np.ptp(x), np.ptp(y), np.ptp(z)) / 2
    if max_range > 0:
        mid_x, mid_y, mid_z = np.mean(x), np.mean(y), np.mean(z)
        ax.set_xlim(mid_x - max_range, mid_x + max_range)
        ax.set_ylim(mid_y - max_range, mid_y + max_range)
        ax.set_zlim(0, max(z) * 1.1 if len(z) > 0 else 80)

    # 颜色条
    sm = plt.cm.ScalarMappable(cmap="Reds", norm=plt.Normalize(0, max(delta.max(), 0.01)))
    sm.set_array([])
    cbar = plt.colorbar(sm, ax=ax, shrink=0.6, pad=0.1)
    cbar.set_label("Pd Reduction (ΔPd = Pd₀ - Pd_jammed)", fontsize=10)

    out = Path(__file__).resolve().parent / "threat_3d_cloud.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved: {out}")
    plt.show()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="威胁场 3D — 干扰影响")
    parser.add_argument("--pkl", required=True, help="EW 干扰场 pkl 文件路径")
    parser.add_argument("--resolution", type=int, default=35)
    parser.add_argument("--delta-min", type=float, default=0.03,
                        help="Pd 差显示下限 (默认0.03)")
    args = parser.parse_args()

    ref_lon, ref_lat = 51.0, 35.0

    # 无干扰
    tf0 = ThreatField(
        spheres=[SphereThreat(center=(0, 0, 0.05), radius=100, threat_level=1.0, id="R1")],
        ref_lon=ref_lon, ref_lat=ref_lat,
    )

    # 有干扰
    from src.ew.ew_jamming_field import load_ew_lookup, bearing_deg
    fields = load_ew_lookup(args.pkl)
    tf1 = ThreatField(
        spheres=[SphereThreat(center=(0, 0, 0.05), radius=100, threat_level=1.0, id="R1")],
        ref_lon=ref_lon, ref_lat=ref_lat,
    )
    tf1.set_jamming(fields)

    jammer_az = None
    if fields:
        f0 = fields[0]
        jp = f0.jammer_position
        if hasattr(jp, '__len__') and len(jp) >= 2 and jp[0] >= 0:
            jammer_az = bearing_deg(
                f0.radar_position[0], f0.radar_position[1], jp[0], jp[1]
            )

    n = args.resolution
    print("采样干扰影响点云...")
    x, y, z, pd0, pd1, delta = sample_jamming_delta(
        tf0, tf1,
        x_range=(-120, 120), y_range=(-120, 120), z_range=(1, 61),
        nx=n, ny=n, nz=max(6, n // 4),
        delta_min=args.delta_min,
    )

    n_pts = len(x)
    print(f"受干扰影响的点: {n_pts} (ΔPd >= {args.delta_min})")
    if n_pts > 0:
        print(f"  ΔPd: min={delta.min():.3f}  max={delta.max():.3f}  mean={delta.mean():.3f}")
        print(f"  Pd₀: min={pd0.min():.3f}  max={pd0.max():.3f}  mean={pd0.mean():.3f}")

    plot_3d_jam_effect(x, y, z, pd0, pd1, delta, jammer_az)


if __name__ == "__main__":
    main()
