#!/usr/bin/env python3
"""
Coverage Path Planning — Parallel Scan Lines for Circular Scanner.

给定：
  - 多边形区域顶点
  - 扫描方向（角度）
  - 圆形扫描器半径

生成覆盖整个区域的平行扫描线。圆形扫描器沿每条线运动，
覆盖宽度为直径 2r，相邻线间距 = 2r - overlap。
"""

import math
from dataclasses import dataclass, field
import numpy as np
from shapely.geometry import Polygon, LineString, Point
import matplotlib.pyplot as plt
from matplotlib.patches import Circle as MPLCircle, Polygon as MPLPolygon
from typing import List, Tuple, Optional


# ══════════════════════════════════════════════
# 数据结构
# ══════════════════════════════════════════════

# 合法的起始角落名称
VALID_START_CORNERS = ("左上", "右上", "左下", "右下")


@dataclass
class CoverageResult:
    """generate_coverage_lines 的输出。"""
    lines: List[LineString]           # 扫描线（边界到边界）
    region: Polygon                   # 区域多边形
    scan_angle_deg: float = 0.0       # 扫描方向角度
    radius: float = 0.0               # 扫描器半径
    overlap: float = 0.0              # 重叠量
    scan_dir: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0]))
    perp_dir: np.ndarray = field(default_factory=lambda: np.array([0.0, 1.0]))
    spacing: float = 0.0              # 线间距

    @property
    def total_length(self) -> float:
        return sum(line.length for line in self.lines)

    @property
    def num_lines(self) -> int:
        return len(self.lines)


@dataclass
class BoustrophedonResult:
    """generate_boustrophedon_path 的输出。"""
    path: List[Tuple[float, float]]   # 连续路径点
    lines: List[LineString]           # 扫描线
    region: Polygon                   # 区域多边形
    entry_point: Tuple[float, float]  # 实际入口坐标
    start_corner: str = ""            # 起始角落
    scan_angle_deg: float = 0.0
    radius: float = 0.0
    overlap: float = 0.0

    @property
    def total_length(self) -> float:
        if len(self.path) < 2:
            return 0.0
        return sum(
            math.hypot(self.path[i + 1][0] - self.path[i][0],
                       self.path[i + 1][1] - self.path[i][1])
            for i in range(len(self.path) - 1))

    @property
    def num_lines(self) -> int:
        return len(self.lines)

    @property
    def num_waypoints(self) -> int:
        return len(self.path)

    @property
    def exit_point(self) -> Optional[Tuple[float, float]]:
        return self.path[-1] if self.path else None


# ══════════════════════════════════════════════
# 核心算法
# ══════════════════════════════════════════════

def generate_coverage_lines(
    region_coords: List[Tuple[float, float]],
    scan_angle_deg: float,
    radius: float,
    overlap: float = 0.0,
) -> CoverageResult:
    """
    生成覆盖区域的平行扫描线。

    算法
    ----
    第一条线距左侧边界 radius，后续线间距 2*radius；
    宽度 <= radius → 单条居中；
    最后一条到右侧边界: 剩余 < radius → 不补；radius <= 剩余 < 2*radius → 补边界线。
    """
    region = Polygon(region_coords)
    if not region.is_valid:
        region = region.buffer(0)

    if isinstance(region, Polygon):
        region_polys = [region]
    else:
        region_polys = list(region.geoms)

    # 方向向量
    angle = math.radians(scan_angle_deg)
    scan_dir = np.array([math.cos(angle), math.sin(angle)])
    perp_dir = np.array([-math.sin(angle), math.cos(angle)])
    scan_dir[np.abs(scan_dir) < 1e-14] = 0.0
    perp_dir[np.abs(perp_dir) < 1e-14] = 0.0

    # 垂直方向线间距
    orig_verts = np.array([[x, y] for x, y in region.exterior.coords[:-1]])
    perp_proj = orig_verts @ perp_dir
    perp_min = perp_proj.min()
    perp_max = perp_proj.max()
    perp_range = perp_max - perp_min

    scan_proj = orig_verts @ scan_dir
    scan_min, scan_max = scan_proj.min(), scan_proj.max()
    margin = max(scan_max - scan_min, 1.0) * 0.5
    scan_min -= margin
    scan_max += margin

    spacing = 2.0 * radius - overlap
    lines: List[LineString] = []

    # 扫描线位置：第一条距边界 radius，间距 2*radius
    # 区间宽度 <= 2*radius → 单条居中
    if perp_range <= spacing:
        positions = [(perp_min + perp_max) / 2.0]
    else:
        positions = []
        d = perp_max - radius
        while d > perp_min + 1e-9:
            positions.append(d)
            d -= spacing

    for d in positions:
        base = d * perp_dir
        start = base + scan_min * scan_dir
        end = base + scan_max * scan_dir
        line = LineString([tuple(start), tuple(end)])

        for poly in region_polys:
            inter = line.intersection(poly)
            if not inter.is_empty:
                if isinstance(inter, LineString) and inter.length > 1e-9:
                    lines.append(inter)
                elif isinstance(inter, Point):
                    # 扫描线刚好切过多边形顶点 → 沿扫描方向延长为虚拟线段
                    pt = (inter.x, inter.y)
                    eps = 1e-6
                    lines.append(LineString([
                        (pt[0] - eps * scan_dir[0], pt[1] - eps * scan_dir[1]),
                        (pt[0] + eps * scan_dir[0], pt[1] + eps * scan_dir[1]),
                    ]))
                elif hasattr(inter, 'geoms'):
                    for seg in inter.geoms:
                        if isinstance(seg, LineString) and seg.length > 1e-9:
                            lines.append(seg)
                        elif isinstance(seg, Point):
                            pt = (seg.x, seg.y)
                            eps = 1e-6
                            lines.append(LineString([
                                (pt[0] - eps * scan_dir[0], pt[1] - eps * scan_dir[1]),
                                (pt[0] + eps * scan_dir[0], pt[1] + eps * scan_dir[1]),
                            ]))

    # 合并同一垂线位置上的碎片 LineString（顶点切断导致）
    if lines:
        by_perp = {}
        for line in lines:
            c0 = list(line.coords)[0]
            k = round(c0[0] * perp_dir[0] + c0[1] * perp_dir[1], 9)
            by_perp.setdefault(k, []).append(line)
        merged: List[LineString] = []
        for _k, frags in by_perp.items():
            if len(frags) == 1:
                merged.append(frags[0])
            else:
                all_coords = []
                for f in frags:
                    all_coords.extend(list(f.coords))
                proj = [(c[0] * scan_dir[0] + c[1] * scan_dir[1], c) for c in all_coords]
                min_c = min(proj, key=lambda x: x[0])[1]
                max_c = max(proj, key=lambda x: x[0])[1]
                merged.append(LineString([min_c, max_c]))
        lines = merged

    return CoverageResult(
        lines=lines, region=region,
        scan_angle_deg=scan_angle_deg, radius=radius, overlap=overlap,
        scan_dir=scan_dir, perp_dir=perp_dir, spacing=spacing,
    )


# ══════════════════════════════════════════════
# 弓形路径规划 (Boustrophedon Path)
# ══════════════════════════════════════════════

def _resolve_start_corner(
    lines: List[LineString],
    scan_dir: np.ndarray,
    start_corner: str,
) -> Tuple[int, int, Tuple[float, float]]:
    """Map a corner name to (line_idx, endpoint_idx, entry_point).

    With scan direction as "right":
      - 左上/右上: first line's left/right endpoint
      - 左下/右下: last  line's left/right endpoint

    endpoint_idx: 0 = physical start (coords[0]), 1 = physical end (coords[-1]).
    """
    _valid = {"左上", "右上", "左下", "右下"}
    if start_corner not in _valid:
        raise ValueError(f"start_corner must be one of {_valid}, got {start_corner!r}")

    # 上 → first line (0), 下 → last line (N-1)
    if start_corner[1] == "上":
        line_idx = 0
    else:
        line_idx = len(lines) - 1

    is_left = start_corner[0] == "左"
    line = lines[line_idx]
    coords = list(line.coords)

    # left = smaller projection onto scan_dir
    proj0 = coords[0][0] * scan_dir[0] + coords[0][1] * scan_dir[1]
    proj1 = coords[-1][0] * scan_dir[0] + coords[-1][1] * scan_dir[1]
    left_is_start = proj0 < proj1
    # We want the endpoint that matches is_left
    if is_left:
        ep_idx = 0 if left_is_start else 1
    else:
        ep_idx = 1 if left_is_start else 0

    entry_pt = (coords[ep_idx][0], coords[ep_idx][1]) if ep_idx == 0 else (coords[-1][0], coords[-1][1])
    return line_idx, ep_idx, entry_pt


def _determine_zigzag_order(
    num_lines: int,
    start_line_idx: int,
    start_endpoint_idx: int,
) -> List[Tuple[int, bool]]:
    """Return traversal order as list of (line_idx, reverse).

    reverse=False: traverse line from physical start to physical end.
    reverse=True:  traverse line from physical end to physical start.
    """
    if start_line_idx == 0:
        line_order = list(range(num_lines))
    else:
        line_order = list(range(num_lines - 1, -1, -1))

    result = []
    for i, line_idx in enumerate(line_order):
        reverse = ((start_endpoint_idx + i) % 2 == 1)
        result.append((line_idx, reverse))
    return result


def generate_boustrophedon_path(
    region_coords: List[Tuple[float, float]],
    scan_angle_deg: float,
    radius: float,
    start_corner: str = "左下",
    overlap: float = 0.0,
    waypoint_spacing: float = None,
) -> BoustrophedonResult:
    """Generate a continuous boustrophedon (zigzag) coverage path.

    Scan lines are connected end-to-end in order.  Turns are straight-line
    segments between adjacent endpoints.

    Parameters
    ----------
    region_coords : 多边形区域顶点 [(x,y), ...]
    scan_angle_deg : 扫描方向（度），0°=水平向右
    radius : 圆形扫描器半径
    start_corner : 起始角落 — "左上" / "右上" / "左下" / "右下"
        以扫描方向为"右"：上/下对应第一/最后一条扫描线
    overlap : 相邻条带重叠量
    waypoint_spacing : 路径采样间距（默认 radius * 0.5）
    """
    if start_corner not in VALID_START_CORNERS:
        raise ValueError(
            f"start_corner 必须是 {VALID_START_CORNERS} 之一，收到 {start_corner!r}")

    region = Polygon(region_coords)
    if not region.is_valid:
        region = region.buffer(0)

    # 生成平行线
    cov = generate_coverage_lines(region_coords, scan_angle_deg, radius, overlap)
    lines = cov.lines
    if not lines:
        return BoustrophedonResult(
            path=[], lines=[], region=region, entry_point=(0.0, 0.0),
            start_corner=start_corner, scan_angle_deg=scan_angle_deg,
            radius=radius, overlap=overlap,
        )

    if waypoint_spacing is None:
        waypoint_spacing = radius * 0.5

    # 1. Resolve start corner to line + endpoint
    start_li, start_ep, entry_pt = _resolve_start_corner(lines, cov.scan_dir, start_corner)
    zigzag = _determine_zigzag_order(len(lines), start_li, start_ep)

    # 2. Build path: connect lines end-to-end with straight turn segments
    path: List[Tuple[float, float]] = []

    for step, (li, reverse) in enumerate(zigzag):
        line = lines[li]
        is_last = (step == len(zigzag) - 1)

        # Sample waypoints along this line
        line_len = line.length
        num_pts = max(2, int(line_len / waypoint_spacing))
        line_pts = []
        for j in range(num_pts):
            d = j * line_len / (num_pts - 1) if num_pts > 1 else 0.0
            pt = line.interpolate(d)
            line_pts.append((pt.x, pt.y))
        if reverse:
            line_pts.reverse()
        path.extend(line_pts)

        # Straight-line turn to next line's entry point
        if not is_last:
            if reverse:
                exit_pt = (line.coords[0][0], line.coords[0][1])
            else:
                exit_pt = (line.coords[-1][0], line.coords[-1][1])

            next_li, next_reverse = zigzag[step + 1]
            next_line = lines[next_li]
            if next_reverse:
                next_entry = (next_line.coords[-1][0], next_line.coords[-1][1])
            else:
                next_entry = (next_line.coords[0][0], next_line.coords[0][1])

            # Straight line from exit to entry
            turn_len = math.hypot(next_entry[0] - exit_pt[0],
                                 next_entry[1] - exit_pt[1])
            num_turn = max(2, int(turn_len / waypoint_spacing))
            for j in range(1, num_turn):
                t = j / (num_turn - 1) if num_turn > 1 else 0.5
                path.append((exit_pt[0] + t * (next_entry[0] - exit_pt[0]),
                             exit_pt[1] + t * (next_entry[1] - exit_pt[1])))

    return BoustrophedonResult(
        path=path, lines=lines, region=region, entry_point=entry_pt,
        start_corner=start_corner, scan_angle_deg=scan_angle_deg,
        radius=radius, overlap=overlap,
    )


# ══════════════════════════════════════════════
# 可视化
# ══════════════════════════════════════════════

def visualize_coverage(
    region_coords: List[Tuple[float, float]],
    lines: List[LineString],
    region_poly: Polygon,
    radius: float,
    scan_angle_deg: float,
    show_circles: bool = True,
    circle_step: float = None,
    save_path: str = None,
):
    """可视化：区域 + 扫描线（均在区域内）+ 圆形扫描器"""
    region = Polygon(region_coords)
    fig, ax = plt.subplots(1, 1, figsize=(10, 8))
    ax.set_aspect('equal')

    # 原始区域
    _draw_poly(ax, region_coords, edgecolor='black', facecolor='whitesmoke',
               linewidth=2, alpha=0.5, label='Region')

    # 扫描线
    colors = plt.cm.tab10.colors
    for i, line in enumerate(lines):
        coords = list(line.coords)
        x = [c[0] for c in coords]
        y = [c[1] for c in coords]
        ax.plot(x, y, color=colors[i % len(colors)], linewidth=2,
                marker='o', markersize=3, label=f'Line {i+1}' if i < 10 else None)

    # 圆形扫描器（沿线的采样点）
    if show_circles and lines:
        if circle_step is None:
            circle_step = radius * 0.5
        for line in lines:
            total_len = line.length
            num_samples = max(2, int(total_len / circle_step))
            for j in range(num_samples):
                dist = j * total_len / (num_samples - 1) if num_samples > 1 else 0
                pt = line.interpolate(dist)
                circle = MPLCircle((pt.x, pt.y), radius, facecolor='blue',
                                   edgecolor='navy', alpha=0.08, linewidth=0.5)
                ax.add_patch(circle)

    # 扫描方向箭头
    cx, cy = region.centroid.x, region.centroid.y
    angle = math.radians(scan_angle_deg)
    arrow_len = max(region.bounds[2] - region.bounds[0],
                    region.bounds[3] - region.bounds[1]) * 0.2
    dx = arrow_len * math.cos(angle)
    dy = arrow_len * math.sin(angle)
    ax.arrow(cx - dx/2, cy - dy/2, dx, dy,
             head_width=arrow_len*0.15, head_length=arrow_len*0.2,
             fc='red', ec='red', linewidth=2, zorder=10, label='Scan direction')

    _set_bounds(ax, region_coords)
    # 去重 legend
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys(), fontsize=8, loc='upper right')

    ax.set_title(f"Coverage Lines\n"
                 f"angle={scan_angle_deg}°, radius={radius:.1f}, "
                 f"spacing={2*radius:.1f}, lines={len(lines)}")
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"  -> {save_path}")
    plt.show()


def visualize_boustrophedon(
    region_coords: List[Tuple[float, float]],
    path: List[Tuple[float, float]],
    lines: List[LineString],
    region_poly: Polygon,
    radius: float,
    scan_angle_deg: float,
    entry_point: Tuple[float, float],
    save_path: str = None,
):
    """Visualize the boustrophedon path with scan lines and scanner coverage."""
    fig, ax = plt.subplots(1, 1, figsize=(12, 10))
    ax.set_aspect('equal')

    # Region
    _draw_poly(ax, region_coords, edgecolor='black', facecolor='whitesmoke',
               linewidth=2, alpha=0.5, label='Region')

    # Scan lines
    colors = plt.cm.tab10.colors
    for i, line in enumerate(lines):
        coords = list(line.coords)
        x = [c[0] for c in coords]
        y = [c[1] for c in coords]
        ax.plot(x, y, color=colors[i % len(colors)], linewidth=2.5,
                marker='s', markersize=4, label=f'Line {i+1}' if i < 6 else None)

    # Full path
    if path:
        px = [p[0] for p in path]
        py = [p[1] for p in path]
        ax.plot(px, py, 'darkorange', linewidth=2.5, alpha=0.9, label='Boustrophedon path')
        # Direction arrows along path
        n_path = len(path)
        arrow_every = max(1, n_path // 12)
        for i in range(0, n_path - 1, arrow_every):
            x0, y0 = path[i]
            x1, y1 = path[min(i + 1, n_path - 1)]
            dx, dy = x1 - x0, y1 - y0
            seg_len = math.hypot(dx, dy)
            if seg_len > 1e-9:
                dx, dy = dx / seg_len, dy / seg_len
                ax.arrow(x0, y0, dx * 0.01, dy * 0.01, head_width=0.15,
                         fc='darkorange', ec='darkorange', alpha=0.7, zorder=10)

    # Scanner circles along path
    if path:
        n_circles = max(2, int(len(path) // 5))
        step = max(1, len(path) // n_circles)
        for j in range(0, len(path), step):
            px_j, py_j = path[j]
            circle = MPLCircle((px_j, py_j), radius, facecolor='blue',
                               edgecolor='navy', alpha=0.06, linewidth=0.5)
            ax.add_patch(circle)

    # Entry point
    ax.scatter(*entry_point, c='green', s=200, marker='*', zorder=15,
               edgecolors='darkgreen', linewidths=1, label='Entry')
    # Exit point
    if path:
        ax.scatter(*path[-1], c='red', s=120, marker='X', zorder=15,
                   edgecolors='darkred', linewidths=1, label='Exit')

    # Scan direction arrow
    cx, cy = region_poly.centroid.x, region_poly.centroid.y
    angle_r = math.radians(scan_angle_deg)
    arrow_len = max(region_poly.bounds[2] - region_poly.bounds[0],
                    region_poly.bounds[3] - region_poly.bounds[1]) * 0.2
    dx = arrow_len * math.cos(angle_r)
    dy = arrow_len * math.sin(angle_r)
    ax.arrow(cx - dx / 2, cy - dy / 2, dx, dy,
             head_width=arrow_len * 0.15, head_length=arrow_len * 0.2,
             fc='red', ec='red', linewidth=2, zorder=10, label='Scan direction')

    _set_bounds(ax, region_coords)
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys(), fontsize=7, loc='upper right')

    ax.set_title(f"Boustrophedon Path\n"
                 f"angle={scan_angle_deg}°, radius={radius:.1f}, "
                 f"lines={len(lines)}, path length={sum(math.hypot(path[i+1][0]-path[i][0], path[i+1][1]-path[i][1]) for i in range(len(path)-1)):.1f}")
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"  -> {save_path}")
    plt.show()


def _draw_poly(ax, coords, **kwargs):
    patch = MPLPolygon(coords, **kwargs)
    ax.add_patch(patch)


def _set_bounds(ax, region_coords):
    xs = [p[0] for p in region_coords]
    ys = [p[1] for p in region_coords]
    margin_x = max((max(xs) - min(xs)) * 0.1, 1.0)
    margin_y = max((max(ys) - min(ys)) * 0.1, 1.0)
    ax.set_xlim(min(xs) - margin_x, max(xs) + margin_x)
    ax.set_ylim(min(ys) - margin_y, max(ys) + margin_y)


# ══════════════════════════════════════════════
# 演示
# ══════════════════════════════════════════════

def demo(name, region, angle, radius, overlap=0.0):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"  angle={angle}°, radius={radius}, overlap={overlap}")
    print(f"{'='*60}")
    result = generate_coverage_lines(region, angle, radius, overlap)
    print(f"  Lines: {result.num_lines}, total length: {result.total_length:.2f}")
    for i, line in enumerate(result.lines):
        coords = list(line.coords)
        print(f"    L{i+1}: ({coords[0][0]:.2f}, {coords[0][1]:.2f}) "
              f"-> ({coords[-1][0]:.2f}, {coords[-1][1]:.2f})  len={line.length:.2f}")
    return result


def demo_boustrophedon(name, region, angle, radius, start_corner="左下", overlap=0.0):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"  angle={angle}°, radius={radius}, start={start_corner}, overlap={overlap}")
    print(f"{'='*60}")
    result = generate_boustrophedon_path(region, angle, radius, start_corner, overlap)
    print(f"  Lines: {result.num_lines}")
    print(f"  Path waypoints: {result.num_waypoints}, total length: {result.total_length:.2f}")
    print(f"  Entry: ({result.entry_point[0]:.2f}, {result.entry_point[1]:.2f})")
    if result.exit_point:
        print(f"  Exit:  ({result.exit_point[0]:.2f}, {result.exit_point[1]:.2f})")
    return result


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(out, exist_ok=True)

    # --- Demo A: 矩形区域，水平扫描 ---
    rA = [(0, 0), (12, 0), (12, 10), (0, 10)]
    resA = demo("A: Rectangle, horizontal scan", rA, angle=0, radius=1.5)
    visualize_coverage(rA, resA.lines, resA.region, radius=1.5, scan_angle_deg=0,
                       save_path=os.path.join(out, "coverage_A_horizontal.png"))

    # --- Demo B: 矩形区域，倾斜 35° 扫描 ---
    rB = [(0, 0), (12, 0), (12, 10), (0, 10)]
    resB = demo("B: Rectangle, 35° tilted scan", rB, angle=35, radius=1.5)
    visualize_coverage(rB, resB.lines, resB.region, radius=1.5, scan_angle_deg=35,
                       save_path=os.path.join(out, "coverage_B_tilted.png"))

    # --- Demo C: L 形区域 ---
    rC = [(0, 0), (14, 0), (14, 5), (5, 5), (5, 12), (0, 12)]
    resC = demo("C: L-shaped region, vertical scan", rC, angle=90, radius=1.2)
    visualize_coverage(rC, resC.lines, resC.region, radius=1.2, scan_angle_deg=90,
                       save_path=os.path.join(out, "coverage_C_lshape.png"))

    # --- Demo D: 五边形，不同半径 ---
    rD = [(0, 0), (10, -2), (15, 5), (8, 12), (2, 8)]
    resD = demo("D: Pentagon, 20° scan, small radius", rD, angle=20, radius=0.8)
    visualize_coverage(rD, resD.lines, resD.region, radius=0.8, scan_angle_deg=20,
                       save_path=os.path.join(out, "coverage_D_pentagon.png"))

    # --- Demo E: 带 overlap ---
    rE = [(0, 0), (10, 0), (10, 8), (0, 8)]
    resE = demo("E: Rectangle with overlap", rE, angle=45, radius=1.0, overlap=0.3)
    visualize_coverage(rE, resE.lines, resE.region, radius=1.0, scan_angle_deg=45,
                       save_path=os.path.join(out, "coverage_E_overlap.png"))

    # --- Demo F: 弓形路径 — 矩形水平扫描，左下角入口 ---
    rF = [(0, 0), (12, 0), (12, 10), (0, 10)]
    resF = demo_boustrophedon(
        "F: Boustrophedon — Rectangle, horizontal, 左下",
        rF, angle=0, radius=1.5, start_corner="左下")
    visualize_boustrophedon(rF, resF.path, resF.lines, resF.region, radius=1.5,
                            scan_angle_deg=0, entry_point=resF.entry_point,
                            save_path=os.path.join(out, "coverage_F_boustrophedon_rect.png"))

    # --- Demo G: 弓形路径 — L 形区域，垂直扫描，右下入口 ---
    rG = [(0, 0), (14, 0), (14, 5), (5, 5), (5, 12), (0, 12)]
    resG = demo_boustrophedon(
        "G: Boustrophedon — L-shape, vertical, 右下",
        rG, angle=90, radius=1.2, start_corner="右下")
    visualize_boustrophedon(rG, resG.path, resG.lines, resG.region, radius=1.2,
                            scan_angle_deg=90, entry_point=resG.entry_point,
                            save_path=os.path.join(out, "coverage_G_boustrophedon_lshape.png"))

    # --- Demo H: 弓形路径 — 五边形，倾斜扫描，左上入口 ---
    rH = [(0, 0), (10, -2), (15, 5), (8, 12), (2, 8)]
    resH = demo_boustrophedon(
        "H: Boustrophedon — Pentagon, 20° tilted, 左上",
        rH, angle=20, radius=0.8, start_corner="左上")
    visualize_boustrophedon(rH, resH.path, resH.lines, resH.region, radius=0.8,
                            scan_angle_deg=20, entry_point=resH.entry_point,
                            save_path=os.path.join(out, "coverage_H_boustrophedon_pentagon.png"))

    print(f"\nAll figures saved to: {out}")
