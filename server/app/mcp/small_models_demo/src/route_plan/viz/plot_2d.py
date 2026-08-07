"""
路径规划可视化模块。

2D 俯视图：柔和威胁等高线 + 几何轮廓 + 路径 + 方向标注
"""

import math
import numpy as np
from typing import List, Tuple

from ..core.geo import local_to_llh, llh_to_local
from ..grid import Grid
from ..core.types import PathResult
from ..io import Scenario
from ..sectors import (
    generate_attack_point_sectors,
    generate_direction_reference_sectors,
    generate_uniform_approach_reference_sectors,
)

PLATFORM_COLORS = [
    "#1b9e77",
    "#d95f02",
    "#7570b3",
    "#e7298a",
    "#66a61e",
    "#e6ab02",
    "#a6761d",
    "#666666",
]

# Swerling I 参数 (与 threats.py 保持一致)
_PFA = 1e-6


def _haversine_km(lon1, lat1, lon2, lat2):
    """Haversine 球面距离 (km)."""
    dlon = math.radians(lon2 - lon1)
    dlat = math.radians(lat2 - lat1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _rcs_scale_pd(pd_base: float, rcs_scale: float) -> float:
    """通过逆 Swerling 将 rcs=1.0 的 base Pd 转换为 RCS 缩放后的 Pd.

    RCS 在 SNR 层面线性缩放, 再经 Swerling S 型曲线映射为 Pd.
    """
    if rcs_scale == 1.0 or pd_base <= _PFA:
        return pd_base
    if pd_base >= 1.0:
        return 1.0
    # Swerling I: Pd = Pfa^(1/(1+SNR))
    # 逆变换: SNR = ln(Pfa)/ln(Pd) - 1
    snr_base = math.log(_PFA) / math.log(pd_base) - 1.0
    if snr_base <= 0:
        return _PFA
    snr_scaled = snr_base * rcs_scale
    if snr_scaled <= 0:
        return _PFA
    return _PFA ** (1.0 / (1.0 + snr_scaled))


def _scenario_candidate_points(scenario: Scenario):
    targets_by_id = {t.id: t for t in scenario.targets}
    cfg = scenario.planner_config
    points = []
    seen = set()

    for pc in scenario.pair_configs:
        target = targets_by_id.get(pc.target_id)
        if target is None:
            continue

        if pc.mode == 2:
            radius_km = (
                pc.approach_ref_radius_km
                if pc.approach_ref_radius_km > 0
                else cfg.default_approach_ref_radius_km
            )
            up_height_km = (
                pc.approach_ref_up_height_km
                if pc.approach_ref_up_height_km > 0
                else cfg.default_approach_ref_up_height_km
            )
            count = (
                pc.approach_ref_count
                if pc.approach_ref_count > 0
                else cfg.default_approach_ref_count
            )
            if target.approach_directions:
                sectors = generate_direction_reference_sectors(
                    target.id,
                    target.position_local,
                    target.approach_directions,
                    reference_radius_km=radius_km,
                ).sectors
            else:
                sectors = generate_uniform_approach_reference_sectors(
                    target.id,
                    target.position_local,
                    radius_km,
                    up_height_km,
                    count,
                ).sectors
        elif pc.mode in (3, 4):
            radius_km = (
                pc.attack_point_radius_km
                if pc.attack_point_radius_km > 0
                else cfg.default_attack_point_radius_km
            )
            up_height_km = (
                pc.attack_point_up_height_km
                if pc.attack_point_up_height_km > 0
                else cfg.default_attack_point_up_height_km
            )
            count = (
                pc.attack_point_count
                if pc.attack_point_count > 0
                else cfg.default_attack_point_count
            )
            sectors = generate_attack_point_sectors(
                target.id,
                target.position_local,
                radius_km,
                up_height_km,
                count,
            ).sectors
        else:
            sectors = []

        for sector in sectors:
            point_llh = local_to_llh(
                sector.point_local[0],
                sector.point_local[1],
                sector.point_local[2],
                scenario.ref_lon,
                scenario.ref_lat,
            )
            key = (
                sector.point_kind,
                round(point_llh[0], 6),
                round(point_llh[1], 6),
                round(point_llh[2], 2),
            )
            if key in seen:
                continue
            seen.add(key)
            points.append((sector.point_kind, sector.point_label, point_llh))

    return points


def _compute_cumulative_distance(waypoints_llh):
    """计算路径累积距离 (km)."""
    cum = [0.0]
    for i in range(1, len(waypoints_llh)):
        lon1, lat1, alt1 = waypoints_llh[i - 1]
        lon2, lat2, alt2 = waypoints_llh[i]
        dlon = (lon2 - lon1) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
        dlat = (lat2 - lat1) * 111.32
        dalt = (alt2 - alt1) / 1000.0
        cum.append(cum[-1] + math.sqrt(dlon ** 2 + dlat ** 2 + dalt ** 2))
    return cum


def _threat_profile_color(val):
    """威胁等级 → 剖面颜色."""
    if val <= 1e-6:
        return "#10b981"
    if val <= 0.01:
        return "#34d399"
    if val <= 0.1:
        return "#facc15"
    if val <= 0.3:
        return "#f97316"
    if val <= 0.5:
        return "#ef4444"
    return "#dc2626"


def _draw_altitude_profile(ax, results, grid, base_color):
    """绘制单个平台-目标对的高度剖面.

    背景 = 沿最佳路径采样各高度层的 Pd 热力 (威胁包络)
    前景 = 该 pair 的各方向路径高度曲线, 颜色按分段威胁暴露
    """
    from matplotlib.patches import Patch

    if not results:
        return

    # 按代价排序, 最佳路径用于威胁包络采样
    sorted_results = sorted(results, key=lambda r: r.cost)
    best = sorted_results[0]
    best_wps = best.waypoints_llh
    best_cum = _compute_cumulative_distance(best_wps)
    pid, tid = best.platform_id, best.target_id

    # ---- 威胁包络背景 ----
    alt_levels = grid.altitudes
    n_alts = len(alt_levels)
    threat_samples = np.zeros((len(best_wps), n_alts))
    for i, wp in enumerate(best_wps):
        for k, alt_km in enumerate(alt_levels):
            try:
                ix, iy, iz = grid.pos_to_node(wp[0], wp[1], alt_km * 1000.0)
                threat_samples[i, k] = grid.get_node_threat(ix, iy, iz)
            except (IndexError, ValueError):
                threat_samples[i, k] = 0.0

    if n_alts >= 2:
        Xe, Ye = np.meshgrid(best_cum, alt_levels)
        levels = [0.01, 0.05, 0.1, 0.3, 0.5, 1.0]
        ax.contourf(
            Xe, Ye, threat_samples.T,
            levels=levels,
            colors=["#e8f5e9", "#fff9c4", "#ffecb3", "#ffcc80", "#ffab91", "#ef9a9a"],
            alpha=0.40,
            antialiased=True,
        )

    # ---- 路径高度曲线 ----
    for i, r in enumerate(sorted_results):
        wps = r.waypoints_llh
        cum_dist = _compute_cumulative_distance(wps)
        alts_km = [wp[2] / 1000.0 for wp in wps]

        if i == 0:
            lw, alpha, ls = 2.5, 0.9, "-"
            label = f"方位{r.direction[0]:.0f}° (最佳, cost={r.cost:.0f})"
        elif i == 1:
            lw, alpha, ls = 1.5, 0.5, "--"
            label = f"方位{r.direction[0]:.0f}°"
        else:
            lw, alpha, ls = 0.8, 0.25, ":"
            label = None

        if r.segment_details and len(r.segment_details) > 0:
            for seg in r.segment_details:
                fi = seg["from_index"]
                ti = seg["to_index"]
                exp = seg.get("threat_exposure", 0)
                seg_len = seg.get("segment_cost", 0)
                n = exp / max(seg_len, 1.0) if seg_len > 0 else exp
                seg_color = _threat_profile_color(n)
                ax.plot(
                    cum_dist[fi:ti + 1], alts_km[fi:ti + 1],
                    color=seg_color, linewidth=lw, alpha=alpha,
                    solid_capstyle="round",
                )
        else:
            ax.plot(
                cum_dist, alts_km, ls,
                color=base_color, linewidth=lw, alpha=alpha,
                label=label, solid_capstyle="round",
            )

        # 起点 / 终点标记
        if i == 0:
            ax.scatter(
                [cum_dist[0]], [alts_km[0]], marker="s",
                color=base_color, s=60, edgecolors="#333333",
                linewidth=1, zorder=10,
            )
            ax.scatter(
                [cum_dist[-1]], [alts_km[-1]], marker="*",
                color="#ff2222", s=100, edgecolors="#333333",
                linewidth=1, zorder=10,
            )

    # 图例: 威胁包络 + 路径
    legend_elements = [
        Patch(facecolor="#e8f5e9", alpha=0.40, label="安全"),
        Patch(facecolor="#fff9c4", alpha=0.40, label="轻"),
        Patch(facecolor="#ffcc80", alpha=0.40, label="中"),
        Patch(facecolor="#ef9a9a", alpha=0.40, label="高"),
    ]
    leg1 = ax.legend(
        handles=legend_elements, loc="upper left", fontsize=6.5,
        title="Pd 包络", title_fontsize=7, ncol=4,
    )
    ax.add_artist(leg1)

    if len(sorted_results) > 1:
        ax.legend(loc="upper right", fontsize=6.5, ncol=1)

    ax.set_title(f"{pid} → {tid}", fontsize=11, fontweight="bold",
                 loc="left", color=base_color, pad=2)
    ax.set_xlabel("累计距离 (km)", fontsize=9)
    ax.set_ylabel("高度 (km)", fontsize=9)
    ax.grid(True, alpha=0.25, linestyle=":", color="#888888")

    # y 轴范围覆盖路径高度
    all_alts = [wp[2] / 1000.0 for r in sorted_results for wp in r.waypoints_llh]
    if all_alts:
        alt_min = min(all_alts)
        alt_max = max(all_alts)
        pad = max(1.0, (alt_max - alt_min) * 0.15)
        ax.set_ylim(alt_min - pad, alt_max + pad)


def plot_scenario(
    scenario: Scenario,
    grid: Grid,
    results: List[PathResult],
    output_path: str = "route_plan.png",
    title: str = None,
    refuel_segments_map: dict = None,
    show_profile: bool = True,
):
    """绘制完整场景, 可选双面板 (俯视图 + 高度剖面)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["PingFang SC", "STFangsong", "SimHei", "Arial"],
            "font.size": 10,
            "axes.titlesize": 14,
            "axes.labelsize": 11,
            "figure.facecolor": "white",
            "axes.unicode_minus": False,
        }
    )

    # ---- 威胁 2D 投影 (跳过<100m层取max, EW干扰效果可见) ----
    threat_2d = np.zeros((grid.ny, grid.nx))
    k0 = next((k for k, a in enumerate(grid.altitudes) if a >= 0.1), 0)
    for i in range(grid.nx):
        for j in range(grid.ny):
            threat_2d[j, i] = max(grid.node_threat[i][j][k0:])

    # 网格 lon/lat 范围
    xs = [grid.origin_lon + i * grid.dlon for i in range(grid.nx)]
    ys = [grid.origin_lat + j * grid.dlat for j in range(grid.ny)]
    X, Y = np.meshgrid(xs, ys)

    # ---- 画布布局 ----
    # row 0: 全局俯视图 (rcs=1)
    # row 1..N: per-pair [剖面 | mini俯视(rcs=各自)]
    if show_profile and results:
        groups = {}
        for r in results:
            groups.setdefault((r.platform_id, r.target_id), []).append(r)
        group_items = list(groups.items())
        n_pairs = len(group_items)

        fig_height = 13 + n_pairs * 7
        fig = plt.figure(figsize=(22, fig_height))
        gs = plt.GridSpec(
            1 + n_pairs, 2,
            height_ratios=[7] + [4] * n_pairs,
            width_ratios=[1.4, 1],
            hspace=0.15, wspace=0.18, figure=fig,
        )
        ax = fig.add_subplot(gs[0, :])  # 全局俯视占整行
        profile_axes = []
        pair_topdown_axes = []
        for i in range(n_pairs):
            profile_axes.append(fig.add_subplot(gs[1 + i, 0]))
            pair_topdown_axes.append(fig.add_subplot(gs[1 + i, 1]))
    else:
        fig = plt.figure(figsize=(16, 13))
        ax = fig.add_subplot(111)
        profile_axes = None
        pair_topdown_axes = None
        group_items = None

    # 1. 威胁热力图 (无描边)
    levels = [0.01, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0]
    cmap_colors = [
        "#e8f5e9", "#c8e6c9", "#fff9c4", "#ffecb3", "#ffe082",
        "#ffcc80", "#ffab91", "#ef9a9a", "#e57373", "#c62828",
    ]
    from matplotlib.colors import ListedColormap
    cmap = ListedColormap(cmap_colors)
    ct = ax.contourf(
        X, Y, threat_2d,
        levels=levels,
        colors=cmap_colors,
        extend="max",
        antialiased=True,
    )
    cbar = fig.colorbar(ct, ax=ax, shrink=0.75, pad=0.02, aspect=30)
    cbar.set_label("Pd (检测概率)", fontsize=9)
    cbar.set_ticks([0.01, 0.1, 0.2, 0.4, 0.6, 0.8, 1.0])

    # 2. 威胁几何体轮廓
    _draw_threats(ax, scenario)

    # 3. 禁飞区
    _draw_nfz(ax, scenario)

    # 4. 路径
    _draw_paths(ax, results)

    # 4.5. 加油点
    if refuel_segments_map:
        _draw_refuel_segments(ax, refuel_segments_map)

    # 5. 目标
    for target in scenario.targets:
        tlon, tlat, _ = target.position_llh
        # 外圈光晕
        ax.plot(tlon, tlat, "o", markersize=16, color="red", alpha=0.2, zorder=9)
        ax.plot(
            tlon,
            tlat,
            "*",
            markersize=22,
            markeredgecolor="#333333",
            markeredgewidth=1.2,
            color="#ff2222",
            zorder=10,
        )
        ax.annotate(
            target.id,
            (tlon, tlat),
            textcoords="offset points",
            xytext=(10, -12),
            fontsize=12,
            fontweight="bold",
            color="#cc0000",
            bbox=dict(
                boxstyle="round,pad=0.3",
                facecolor="white",
                edgecolor="#cc0000",
                alpha=0.85,
            ),
        )

    # 6. 显式 waypoint
    for waypoint in scenario.waypoints:
        wlon, wlat, _ = waypoint.position_llh
        ax.plot(
            wlon,
            wlat,
            marker="D",
            markersize=9,
            color="#22d3ee",
            markeredgecolor="#0f172a",
            markeredgewidth=1.2,
            zorder=9,
        )
        ax.annotate(
            f"WP {waypoint.id}",
            (wlon, wlat),
            textcoords="offset points",
            xytext=(8, 8),
            fontsize=9,
            fontweight="bold",
            color="#0f766e",
            bbox=dict(
                boxstyle="round,pad=0.25",
                facecolor="white",
                edgecolor="#22d3ee",
                alpha=0.85,
            ),
        )

    # 7. 场景级候选点: 攻击点 / 入射参考点
    for point_kind, point_label, point_llh in _scenario_candidate_points(scenario):
        clon, clat, _ = point_llh
        if point_kind == "attack_point":
            marker = "^"
            color = "#f59e0b"
        else:
            marker = "P"
            color = "#8b5cf6"
        ax.plot(
            clon,
            clat,
            marker=marker,
            markersize=8,
            color=color,
            markeredgecolor="white",
            markeredgewidth=0.8,
            alpha=0.45,
            zorder=8,
        )
        ax.annotate(
            point_label or point_kind,
            (clon, clat),
            textcoords="offset points",
            xytext=(6, -12),
            fontsize=7,
            color=color,
            alpha=0.85,
        )

    # 8. 结果级控制点: 最终选中路径使用的攻击点 / 入射参考点
    for result in results:
        if not result.control_point_llh:
            continue
        clon, clat, _ = result.control_point_llh
        if result.control_point_kind == "attack_point":
            marker = "^"
            color = "#f59e0b"
        else:
            marker = "P"
            color = "#8b5cf6"
        ax.plot(
            clon,
            clat,
            marker=marker,
            markersize=9,
            color=color,
            markeredgecolor="#111827",
            markeredgewidth=1.0,
            zorder=9,
        )
        ax.annotate(
            result.control_point_label or result.control_point_kind,
            (clon, clat),
            textcoords="offset points",
            xytext=(8, -14),
            fontsize=8,
            color=color,
            fontweight="bold",
            bbox=dict(
                boxstyle="round,pad=0.2",
                facecolor="white",
                edgecolor=color,
                alpha=0.82,
            ),
        )

    # 8.5 mode 3/4/5: 攻击阵位 → 目标 LOS 虚线
    target_pos_map = {t.id: t.position_llh for t in scenario.targets}
    for result in results:
        if result.mode not in (3, 4, 5) or not result.control_point_llh:
            continue
        tgt_llh = target_pos_map.get(result.target_id)
        if tgt_llh is None:
            continue
        clon, clat, _ = result.control_point_llh
        ax.plot(
            [clon, tgt_llh[0]], [clat, tgt_llh[1]],
            "--", color="#f59e0b", linewidth=1.0, alpha=0.7,
            dash_capstyle="round", zorder=8,
        )
        # LOS 中点标注距离
        mid_lon = (clon + tgt_llh[0]) / 2
        mid_lat = (clat + tgt_llh[1]) / 2
        los_dist_km = _haversine_km(clon, clat, tgt_llh[0], tgt_llh[1])
        ax.annotate(
            f"{los_dist_km:.0f}km",
            (mid_lon, mid_lat),
            textcoords="offset points",
            xytext=(0, 6),
            fontsize=7,
            color="#f59e0b",
            alpha=0.8,
            ha="center",
        )

    # 9. 标注
    ax.set_xlabel("经度 (°)", fontsize=11)
    ax.set_ylabel("纬度 (°)", fontsize=11)
    ax.set_title(
        title or f"路径规划 — {scenario.name} (威胁等高线)",
        fontsize=14,
        fontweight="bold",
        pad=15,
    )
    ax.grid(True, alpha=0.25, linestyle=":", color="#888888")
    ax.set_xlim(xs[0], xs[-1])
    ax.set_ylim(ys[0], ys[-1])
    ax.set_aspect(1.0 / math.cos(math.radians((ys[0] + ys[-1]) / 2)))

    # 图例
    ax.legend(loc="upper left", fontsize=9, ncol=2, framealpha=0.9, edgecolor="#cccccc",
              bbox_to_anchor=(1.02, 1), borderaxespad=0)

    # 比例尺
    _add_scale_bar(ax)

    # 10. 高度剖面 + mini 俯视图 (每对独立)
    if profile_axes is not None and pair_topdown_axes is not None:
        platform_by_id = {p.id: p for p in scenario.platforms}
        for idx, ((pid, tid), group_results) in enumerate(group_items):
            base_color = PLATFORM_COLORS[idx % len(PLATFORM_COLORS)]
            _draw_altitude_profile(profile_axes[idx], group_results, grid, base_color)

            # 获取平台 RCS
            plat = platform_by_id.get(pid)
            rcs = plat.rcs_scale if plat else 1.0
            _draw_pair_topdown(
                pair_topdown_axes[idx], group_results, base_color,
                scenario, grid, rcs, X, Y,
            )

    fig.savefig(output_path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  图表已保存: {output_path}")


def _draw_pair_topdown(ax, group_results, base_color, scenario, grid, rcs_scale, X, Y):
    """绘制单个平台-目标对的 mini 俯视图 (rcs 缩放后的威胁热图 + 路径)."""
    # RCS 缩放: 通过逆 Swerling 将 rcs=1.0 的 base Pd 转换为 RCS 缩放后的 Pd
    threat_scaled = np.zeros((grid.ny, grid.nx))
    for i in range(grid.nx):
        for j in range(grid.ny):
            threat_scaled[j, i] = _rcs_scale_pd(min(grid.node_threat[i][j]), rcs_scale)

    levels = [0.01, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0]
    cmap_colors = [
        "#e8f5e9", "#c8e6c9", "#fff9c4", "#ffecb3", "#ffe082",
        "#ffcc80", "#ffab91", "#ef9a9a", "#e57373", "#c62828",
    ]
    ax.contourf(
        X, Y, threat_scaled,
        levels=levels,
        colors=cmap_colors,
        extend="max",
        antialiased=True,
    )

    # 路径
    sorted_r = sorted(group_results, key=lambda r: r.cost)
    for i, r in enumerate(sorted_r):
        lons = [wp[0] for wp in r.waypoints_llh]
        lats = [wp[1] for wp in r.waypoints_llh]
        if i == 0:
            lw, alpha, ls = 2.0, 0.95, "-"
        else:
            lw, alpha, ls = 0.8, 0.35, ":"
        ax.plot(lons, lats, ls, color="#111111", linewidth=lw, alpha=alpha,
                solid_capstyle="round", zorder=5)

    # 起点 / 终点
    best = sorted_r[0]
    b_lons = [wp[0] for wp in best.waypoints_llh]
    b_lats = [wp[1] for wp in best.waypoints_llh]
    ax.plot(b_lons[0], b_lats[0], "s", color=base_color,
            markersize=8, markeredgecolor="#333333", zorder=10)
    ax.plot(b_lons[-1], b_lats[-1], "*", color="#ff2222",
            markersize=14, markeredgecolor="#333333", zorder=10)

    # mode 3/4/5: 攻击阵位 → 目标 LOS 虚线
    if best.mode in (3, 4, 5) and best.control_point_llh:
        tgt_map = {t.id: t.position_llh for t in scenario.targets}
        tgt_llh = tgt_map.get(best.target_id)
        if tgt_llh:
            clon, clat, _ = best.control_point_llh
            ax.plot(
                [clon, tgt_llh[0]], [clat, tgt_llh[1]],
                "--", color="#f59e0b", linewidth=1.0, alpha=0.7,
                dash_capstyle="round", zorder=8,
            )

    # 目标
    for target in scenario.targets:
        tlon, tlat, _ = target.position_llh
        ax.plot(tlon, tlat, "o", markersize=6, color="red", alpha=0.2, zorder=9)

    # 干扰机标记
    if scenario.threat_field.jamming_fields:
        meta = scenario.threat_field.jamming_metadata
        jammers = meta.get("jammers", []) if meta else []
        for j in jammers:
            ax.plot(j["position"][0], j["position"][1], "P",
                    color="#c026d3", markersize=6,
                    markeredgecolor="#333333", markeredgewidth=0.5, zorder=11)

    pid = best.platform_id
    tid = best.target_id
    ax.set_title(f"{pid} → {tid}  (RCS={rcs_scale:.2f})", fontsize=9,
                 fontweight="bold", color=base_color)
    ax.set_xlabel("经度 (°)", fontsize=7)
    ax.set_ylabel("纬度 (°)", fontsize=7)
    ax.set_xlim(X[0, 0], X[0, -1])
    ax.set_ylim(Y[0, 0], Y[-1, 0])
    ax.set_aspect(1.0 / math.cos(math.radians((Y[0, 0] + Y[-1, 0]) / 2)))
    ax.grid(True, alpha=0.2, linestyle=":", color="#888888")


def _draw_threats(ax, scenario: Scenario):
    """绘制威胁: 球体投影圈 (ENU→LLH 避免畸变) + 圆锥楔形 + 等级标注."""
    from matplotlib.patches import Wedge

    ref_lon, ref_lat = scenario.ref_lon, scenario.ref_lat

    for s in scenario.threat_field.spheres:
        cx, cy, cz = s.center  # ENU km
        # 地面投影半径 (考虑球体高度)
        r_horiz = math.sqrt(max(0, s.radius ** 2 - cz ** 2))
        theta = np.linspace(0, 2 * np.pi, 200)
        ring_x = cx + r_horiz * np.cos(theta)
        ring_y = cy + r_horiz * np.sin(theta)
        ring_ll = [local_to_llh(x, y, 0, ref_lon, ref_lat)
                   for x, y in zip(ring_x, ring_y)]
        lons = [p[0] for p in ring_ll]
        lats = [p[1] for p in ring_ll]
        ax.plot(lons, lats, color="#333333", linewidth=1.0,
                linestyle="--", alpha=0.45, zorder=3)

        center_ll = local_to_llh(cx, cy, cz, ref_lon, ref_lat)
        ax.annotate(
            f"P{s.threat_level:.1f}",
            (center_ll[0], center_ll[1]),
            fontsize=7,
            color="#cc3333",
            ha="center",
            va="center",
            fontweight="bold",
        )

    for c in scenario.threat_field.cones:
        lon, lat, _ = local_to_llh(*c.apex, ref_lon, ref_lat)
        r = c.max_range_km / 111.32
        az = math.degrees(math.atan2(c.direction[1], c.direction[0]))
        ha = c.angle_deg
        w = Wedge(
            (lon, lat),
            r,
            az - ha,
            az + ha,
            fill=True,
            facecolor="#ff9944",
            edgecolor="#cc6600",
            linewidth=1.2,
            alpha=0.15,
            zorder=1,
        )
        ax.add_patch(w)
        ax.plot(lon, lat, "^", color="#cc6600", markersize=8, zorder=4)
        ax.annotate(
            c.threat_level,
            (lon, lat),
            fontsize=7,
            color="#cc6600",
            ha="center",
            va="bottom",
            fontweight="bold",
        )

    for cy in scenario.threat_field.cylinders:
        lon, lat, _ = local_to_llh(
            cy.center_2d[0], cy.center_2d[1], 0, ref_lon, ref_lat
        )
        ax.annotate(
            f"P{cy.threat_level:.1f}",
            (lon, lat),
            fontsize=7,
            color="#3366cc",
            ha="center",
            va="center",
            fontweight="bold",
        )


def _draw_jamming(ax, scenario: Scenario):
    """EW干扰场: 压制区轮廓 + 干扰机."""
    import numpy as np

    jam_fields = scenario.threat_field.jamming_fields
    if not isinstance(jam_fields, dict) or not jam_fields:
        return

    tf = scenario.threat_field
    threat_ids = set()
    for lst in (tf.spheres, tf.cones, tf.cylinders,
                tf.elliptic_cylinders, tf.ellipsoids):
        for t in lst:
            if t.id:
                threat_ids.add(t.id)

    meta = scenario.threat_field.jamming_metadata
    jammers = meta.get("jammers", []) if meta else []
    radars_meta = meta.get("radars", []) if meta else []

    first_jf = next(iter(jam_fields.values()))
    alt_idx = len(first_jf.alt_grid) // 2
    merged = None
    for rid, jf in jam_fields.items():
        if rid not in threat_ids:
            continue
        f_slice = jf.factors[:, :, alt_idx]
        merged = f_slice if merged is None else np.minimum(merged, f_slice)

    if merged is not None:
        lon_g, lat_g = first_jf.lon_grid, first_jf.lat_grid
        lon_m, lat_m = np.meshgrid(lon_g, lat_g, indexing="ij")
        # 压制区: factor<0.2 深紫半透明
        ax.contourf(lon_m, lat_m, merged, levels=[0, 0.2],
                    colors=["#7e22ce"], alpha=0.18, zorder=4)
        ax.contour(lon_m, lat_m, merged, levels=[0.2],
                   colors=["#7e22ce"], linewidths=[1.0], alpha=0.5, zorder=5)

    # 干扰机 → 雷达连线
    for r_info in radars_meta:
        if r_info["id"] not in threat_ids:
            continue
        rlon, rlat = r_info["position"][0], r_info["position"][1]
        for j in jammers:
            jlon, jlat = j["position"][0], j["position"][1]
            ax.plot([jlon, rlon], [jlat, rlat], "--", color="#c026d3",
                    linewidth=0.6, alpha=0.35, zorder=3)

    for j in jammers:
        ax.plot(j["position"][0], j["position"][1], "P",
                color="#c026d3", markersize=8,
                markeredgecolor="#333333", markeredgewidth=0.8, zorder=11)


def _draw_nfz(ax, scenario: Scenario):
    from matplotlib.patches import Circle

    ref_lon, ref_lat = scenario.ref_lon, scenario.ref_lat
    for nfz in scenario.threat_field.no_fly_zones:
        lon, lat, _ = local_to_llh(
            nfz.center_2d[0], nfz.center_2d[1], 0, ref_lon, ref_lat
        )
        r = nfz.radius / 111.32
        ax.add_patch(
            Circle(
                (lon, lat),
                r,
                fill=True,
                facecolor="#333333",
                edgecolor="#111111",
                linewidth=2.5,
                alpha=0.35,
                hatch="xxxx",
                zorder=3,
            )
        )
        ax.annotate(
            "禁飞区",
            (lon, lat),
            fontsize=8,
            color="#111111",
            ha="center",
            va="center",
            fontweight="bold",
        )


def _draw_refuel_segments(ax, refuel_segments_map: dict):
    """Draw forward-moving refuel segments (start→end lines along path)."""
    for key, segments in refuel_segments_map.items():
        if not segments:
            continue
        pid = key.split("->")[0]
        for rs in segments:
            # Support both dataclass (RefuelSegment) and dict formats
            if hasattr(rs, "start_position_llh"):
                s_lon, s_lat = rs.start_position_llh[0], rs.start_position_llh[1]
                e_lon, e_lat = rs.end_position_llh[0], rs.end_position_llh[1]
                adjusted = rs.adjusted
                refuel_dist = rs.refuel_distance_km
            else:
                sp = rs.get("start_position", [0, 0, 0])
                ep = rs.get("end_position", [0, 0, 0])
                s_lon, s_lat = sp[0], sp[1]
                e_lon, e_lat = ep[0], ep[1]
                adjusted = rs.get("adjusted", False)
                refuel_dist = rs.get("refuel_distance_km", 0)

            if adjusted:
                color = "#f97316"
                edgecolor = "#9a3412"
            else:
                color = "#22c55e"
                edgecolor = "#166534"

            # Draw start marker
            ax.plot(s_lon, s_lat, "D", color=color, markersize=10,
                    markeredgecolor=edgecolor, markeredgewidth=1.5, zorder=10)
            # Draw end marker
            ax.plot(e_lon, e_lat, "s", color=color, markersize=8,
                    markeredgecolor=edgecolor, markeredgewidth=1.5, zorder=10)
            # Label at start position
            label = f"{pid}加油\n{refuel_dist:.0f}km" + ("(回退)" if adjusted else "")
            ax.annotate(
                label,
                (s_lon, s_lat),
                textcoords="offset points",
                xytext=(5, -15),
                fontsize=7,
                color=edgecolor,
                fontweight="bold",
                bbox=dict(
                    boxstyle="round,pad=0.2",
                    facecolor="white",
                    edgecolor=color,
                    alpha=0.85,
                ),
            )


def _draw_paths(ax, results: List[PathResult]):
    groups = {}
    for r in results:
        groups.setdefault((r.platform_id, r.target_id), []).append(r)

    color_idx = 0
    for (pid, tid), group in groups.items():
        group.sort(key=lambda r: r.cost)
        base_color = PLATFORM_COLORS[color_idx % len(PLATFORM_COLORS)]

        for i, r in enumerate(group):
            lons = [wp[0] for wp in r.waypoints_llh]
            lats = [wp[1] for wp in r.waypoints_llh]

            if i == 0:
                # 最佳路径：粗实线
                lw, alpha, ls = 3.2, 0.95, "-"
                label = f"{pid} → {tid} 方位{r.direction[0]}°"
            elif i == 1:
                lw, alpha, ls = 1.8, 0.55, "--"
                label = None
            else:
                lw, alpha, ls = 1.2, 0.3, ":"
                label = None

            ax.plot(
                lons,
                lats,
                ls,
                color=base_color,
                linewidth=lw,
                alpha=alpha,
                label=label,
                zorder=5,
                solid_capstyle="round",
            )

            # 起点方块
            if i == 0:
                ax.plot(
                    lons[0],
                    lats[0],
                    "s",
                    color=base_color,
                    markersize=10,
                    markeredgecolor="#333333",
                    markeredgewidth=1,
                    zorder=8,
                )
                ax.annotate(
                    pid,
                    (lons[0], lats[0]),
                    textcoords="offset points",
                    xytext=(6, 6),
                    fontsize=7,
                    color=base_color,
                    fontweight="bold",
                )

            # 方向箭头（中点偏后）
            if len(lons) >= 3:
                mi = len(lons) // 2 + 1
                ax.annotate(
                    "",
                    xy=(lons[mi], lats[mi]),
                    xytext=(lons[mi - 1], lats[mi - 1]),
                    arrowprops=dict(
                        arrowstyle="->", color=base_color, lw=1.8, alpha=0.6
                    ),
                )

            # 进入方向箭头 (末端)
            if len(lons) >= 2:
                ax.annotate(
                    "",
                    xy=(lons[-1], lats[-1]),
                    xytext=(lons[-2], lats[-2]),
                    arrowprops=dict(
                        arrowstyle="->", color=base_color, lw=2.5, alpha=0.8
                    ),
                )

        color_idx += 1


def _add_scale_bar(ax):
    """添加比例尺 (~100km)."""
    scale_km = 100
    scale_deg = scale_km / 111.32
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    x0 = xlim[0] + 0.05 * (xlim[1] - xlim[0])
    y0 = ylim[0] + 0.04 * (ylim[1] - ylim[0])
    ax.plot([x0, x0 + scale_deg], [y0, y0], "k-", linewidth=3)
    ax.annotate(
        f"{scale_km} km",
        (x0 + scale_deg / 2, y0),
        textcoords="offset points",
        xytext=(0, -12),
        fontsize=9,
        ha="center",
        fontweight="bold",
    )


# ============================================================
# 分层热力图 (柔和版)
# ============================================================


