#!/usr/bin/env python3
"""
Cell Traversal Coverage Path Planning.

给定目标区域（多边形）和禁飞区（圆柱），利用 region_partition 进行 cell 分解，
在 cell 之间规划流通路径，生成完整的覆盖侦查路径。

核心流程 (单平台 → 单区域):
1. 垂直分解目标区域 → n 个 cell
2. 对每个 cell 求解 4 个入口角的 zigzag 路径，记录出入口
3. 贪心遍历：每次从未访问 cell 中选 (当前点到入口 + zigzag) 总代价最小的
"""

import math
import heapq
import os
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict

import numpy as np
from shapely.geometry import Polygon, Point, LineString, box
from shapely.ops import unary_union

from .region_partition import vertical_decompose
from .coverage_lines import generate_boustrophedon_path, BoustrophedonResult

# ══════════════════════════════════════════════
# 数据结构
# ══════════════════════════════════════════════

VALID_CORNERS = ("左上", "右上", "左下", "右下")


@dataclass
class PlatformSpec:
    id: str
    position_xy: Tuple[float, float]       # 局部坐标 (x_km, y_km)
    detection_radius_km: float = 5.0


@dataclass
class TargetArea:
    id: str
    vertices: List[Tuple[float, float]]     # 区域多边形顶点 (x_km, y_km)


@dataclass
class NoFlyZone:
    id: str
    center_xy: Tuple[float, float]          # 圆柱中心 (x_km, y_km)
    radius_km: float                        # 圆柱半径 → 正方形边长 = 2*radius
    height_m: float = 0.0                   # 保留但俯视忽略


@dataclass
class PairSpec:
    platform_id: str
    target_id: str


@dataclass
class CellZigzagPaths:
    """一个 cell 在 4 个入口角下的 zigzag 路径。"""
    cell_index: int
    paths: Dict[str, BoustrophedonResult] = field(default_factory=dict)
    # {corner: BoustrophedonResult}


@dataclass
class TraversalSegment:
    """一段路径：从 entry 到 exit，途经一个 cell 的 zigzag 覆盖。"""
    segment_type: str  # "approach" | "cell_cover" | "inter_cell" | "return"
    cell_index: Optional[int] = None
    entry_point: Optional[Tuple[float, float]] = None
    exit_point: Optional[Tuple[float, float]] = None
    path: List[Tuple[float, float]] = field(default_factory=list)
    length_km: float = 0.0


@dataclass
class CoveragePlanResult:
    platform_id: str
    target_id: str
    full_path: List[Tuple[float, float]] = field(default_factory=list)
    segments: List[TraversalSegment] = field(default_factory=list)
    total_length_km: float = 0.0
    cells: List[Polygon] = field(default_factory=list)
    cell_order: List[int] = field(default_factory=list)
    obstacles: List[Polygon] = field(default_factory=list)
    # 预计算的 zigzag 扫描线，避免可视化时重新生成
    cell_zigzag_lines: Dict[int, List[LineString]] = field(default_factory=dict)


# ══════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════

def cylinder_to_square(center_xy: Tuple[float, float],
                       radius_km: float) -> List[Tuple[float, float]]:
    """将圆柱禁飞区转为正方形（俯视图，边长 = 2*radius）。"""
    cx, cy = center_xy
    r = radius_km
    return [(cx - r, cy - r), (cx + r, cy - r),
            (cx + r, cy + r), (cx - r, cy + r)]


def cylinder_to_hexagon(center_xy: Tuple[float, float],
                        radius_km: float) -> List[Tuple[float, float]]:
    """将圆柱禁飞区转为外接正六边形（俯视图，6 顶点，外接圆半径 = 2r/√3）。"""
    cx, cy = center_xy
    R = radius_km / math.cos(math.radians(30))
    verts = []
    for i in range(6):
        angle = math.radians(i * 60)
        verts.append((cx + R * math.cos(angle), cy + R * math.sin(angle)))
    return verts


def _point_to_2d(p: Tuple[float, ...]) -> Tuple[float, float]:
    return (p[0], p[1])


def dist_2d(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def polygon_centroid_2d(vertices: List[Tuple[float, float]]) -> Tuple[float, float]:
    poly = Polygon(vertices)
    c = poly.centroid
    return (c.x, c.y)


def _all_line_endpoints(lines: List[LineString]) -> List[Tuple[float, float]]:
    """收集所有扫描线的端点。"""
    pts = []
    for line in lines:
        coords = list(line.coords)
        if coords:
            pts.append((coords[0][0], coords[0][1]))
            pts.append((coords[-1][0], coords[-1][1]))
    return pts


# ══════════════════════════════════════════════
# A* 路径规划（网格，避开障碍物）
# ══════════════════════════════════════════════

def _build_obstacle_mask(obstacle_polys: List[Polygon],
                         bounds: Tuple[float, float, float, float],
                         resolution: float) -> np.ndarray:
    """构建占据栅格 (0=free, 1=obstacle)。"""
    xmin, ymin, xmax, ymax = bounds
    cols = max(1, int((xmax - xmin) / resolution) + 1)
    rows = max(1, int((ymax - ymin) / resolution) + 1)
    mask = np.zeros((rows, cols), dtype=np.uint8)

    for r in range(rows):
        for c in range(cols):
            px = xmin + (c + 0.5) * resolution
            py = ymin + (r + 0.5) * resolution
            pt = Point(px, py)
            for obs in obstacle_polys:
                if obs.contains(pt) or obs.touches(pt):
                    mask[r, c] = 1
                    break
    return mask


def astar_path(
    start: Tuple[float, float],
    goal: Tuple[float, float],
    obstacle_polys: List[Polygon],
    resolution: float = 0.5,
    safety_margin: float = 0.1,
    prebuilt_mask: Tuple[np.ndarray, Tuple[float, float, float, float]] = None,
) -> List[Tuple[float, float]]:
    """A* 网格路径搜索，返回路径点列表。

    可选传入 (mask, (xmin, ymin, xmax, ymax)) 避免重复构建掩码。
    """
    if not obstacle_polys:
        return [start, goal]

    if prebuilt_mask is not None:
        mask, (xmin, ymin, xmax, ymax) = prebuilt_mask
    else:
        # 构建包围盒
        all_pts = [start, goal]
        for obs in obstacle_polys:
            b = obs.bounds
            all_pts.extend([(b[0], b[1]), (b[2], b[3])])
        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        margin = max(1.0, safety_margin * 5)
        xmin, xmax = min(xs) - margin, max(xs) + margin
        ymin, ymax = min(ys) - margin, max(ys) + margin
        mask = _build_obstacle_mask(obstacle_polys, (xmin, ymin, xmax, ymax), resolution)

    rows, cols = mask.shape

    def world_to_grid(pt):
        c = int((pt[0] - xmin) / resolution)
        r = int((pt[1] - ymin) / resolution)
        return (max(0, min(rows - 1, r)), max(0, min(cols - 1, c)))

    def grid_to_world(gr, gc):
        return (xmin + (gc + 0.5) * resolution,
                ymin + (gr + 0.5) * resolution)

    start_rc = world_to_grid(start)
    goal_rc = world_to_grid(goal)

    if mask[start_rc] == 1:
        # 起点被障碍物挡住 → 找最近的自由格
        best = None
        best_d = float('inf')
        for dr in range(-3, 4):
            for dc in range(-3, 4):
                nr, nc = start_rc[0] + dr, start_rc[1] + dc
                if 0 <= nr < rows and 0 <= nc < cols and mask[nr, nc] == 0:
                    d = abs(dr) + abs(dc)
                    if d < best_d:
                        best_d = d
                        best = (nr, nc)
        if best is None:
            return [start, goal]
        start_rc = best

    if mask[goal_rc] == 1:
        best = None
        best_d = float('inf')
        for dr in range(-3, 4):
            for dc in range(-3, 4):
                nr, nc = goal_rc[0] + dr, goal_rc[1] + dc
                if 0 <= nr < rows and 0 <= nc < cols and mask[nr, nc] == 0:
                    d = abs(dr) + abs(dc)
                    if d < best_d:
                        best_d = d
                        best = (nr, nc)
        if best is None:
            return [start, goal]
        goal_rc = best

    # A* search
    def heuristic(rc1, rc2):
        return abs(rc1[0] - rc2[0]) + abs(rc1[1] - rc2[1])

    open_set = [(heuristic(start_rc, goal_rc), 0, start_rc)]
    came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
    g_score: Dict[Tuple[int, int], float] = {start_rc: 0.0}
    closed: Set[Tuple[int, int]] = set()

    neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1),
                 (-1, -1), (-1, 1), (1, -1), (1, 1),
                 (-1, -2), (1, -2), (-1, 2), (1, 2),
                 (-2, -1), (2, -1), (-2, 1), (2, 1)]

    found = False
    while open_set:
        _, _, current = heapq.heappop(open_set)
        if current in closed:
            continue
        closed.add(current)

        if current == goal_rc:
            found = True
            break

        cr, cc = current
        for dr, dc in neighbors:
            nr, nc = cr + dr, cc + dc
            if not (0 <= nr < rows and 0 <= nc < cols):
                continue
            if mask[nr, nc] == 1:
                continue
            nbr = (nr, nc)
            if nbr in closed:
                continue
            move_cost = math.sqrt(dr * dr + dc * dc) * resolution
            tentative = g_score[current] + move_cost
            if tentative < g_score.get(nbr, float('inf')):
                came_from[nbr] = current
                g_score[nbr] = tentative
                heapq.heappush(open_set, (tentative + heuristic(nbr, goal_rc),
                                          len(closed), nbr))

    if not found:
        return [start, goal]  # fallback: 直线

    # 重建路径
    path_rc = []
    cur = goal_rc
    while cur != start_rc:
        path_rc.append(cur)
        cur = came_from.get(cur, start_rc)
    path_rc.append(start_rc)
    path_rc.reverse()

    # 重建路径：从网格点转为世界坐标
    path_xy = [start]
    for rc in path_rc:
        w = grid_to_world(rc[0], rc[1])
        # 过滤距离太近的重复点
        if dist_2d(path_xy[-1], w) > resolution * 0.3:
            path_xy.append(w)
    if dist_2d(path_xy[-1], goal) > resolution * 0.1:
        path_xy.append(goal)

    # 路径平滑：贪心视线法 — 从起点出发，尽量跳到能直线到达的最远点
    simplified = [path_xy[0]]
    i = 0
    while i < len(path_xy) - 1:
        best_j = i + 1
        for j in range(len(path_xy) - 1, i, -1):
            line = LineString([path_xy[i], path_xy[j]])
            blocked = False
            for obs in obstacle_polys:
                if line.crosses(obs) or (
                    line.intersects(obs) and not line.touches(obs)
                    and line.intersection(obs).length > resolution):
                    blocked = True
                    break
            if not blocked:
                best_j = j
                break
        simplified.append(path_xy[best_j])
        i = best_j

    return simplified


# ══════════════════════════════════════════════
# 单区域覆盖路径规划
# ══════════════════════════════════════════════

def plan_single_coverage(
    platform: PlatformSpec,
    target: TargetArea,
    obstacles_xy: List[List[Tuple[float, float]]],
    obstacle_polys: List[Polygon],
) -> CoveragePlanResult:
    """为单平台 → 单目标区域规划覆盖路径（贪心最近邻 cell 遍历）。

    Args:
        platform: 平台规格
        target: 目标区域
        obstacles_xy: 障碍物坐标列表（正方形）
        obstacle_polys: 障碍物 Polygon（用于碰撞检测）

    Returns:
        CoveragePlanResult with full path
    """
    scan_angle_deg = 90.0  # 固定垂直扫描方向
    radius = platform.detection_radius_km
    plat_pos = platform.position_xy

    # 预处理坐标：round 到 6 位小数（mm 级），避免 region_partition
    # 内部的 round(x,10) 因浮点精度导致分割线刚好擦过障碍物边界
    _prep = lambda coords: [(round(x, 6), round(y, 6)) for x, y in coords]
    region_coords = _prep(target.vertices)
    obs_coords = [_prep(obs) for obs in obstacles_xy]

    # 1. Cell 分解
    cells, merged_obs, region = vertical_decompose(region_coords, obs_coords)
    if not cells:
        # 无法分解 → 整个区域作为一个 cell
        cells = [Polygon(target.vertices)]
        merged_obs = []

    n = len(cells)

    # 2. 对每个 cell 求解 4 个 zigzag 路径
    cell_zigzag: Dict[int, CellZigzagPaths] = {}
    for i, poly in enumerate(cells):
        coords = list(poly.exterior.coords)
        if len(coords) > 1 and coords[0] == coords[-1]:
            coords = coords[:-1]
        cz = CellZigzagPaths(cell_index=i)
        all_failed = True
        for corner in VALID_CORNERS:
            try:
                bpath = generate_boustrophedon_path(
                    coords, scan_angle_deg, radius, start_corner=corner)
                if bpath.path:
                    cz.paths[corner] = bpath
                    all_failed = False
            except Exception:
                cz.paths[corner] = None
        # 如果所有 zigzag 都失败（cell 太薄），生成穿越 centroid 的直通路径
        if all_failed:
            centroid = poly.centroid
            cpt = (centroid.x, centroid.y)
            fallback = BoustrophedonResult(
                path=[cpt],
                lines=[],
                region=poly,
                entry_point=cpt,
                start_corner="左下",
            )
            for corner in VALID_CORNERS:
                cz.paths[corner] = fallback
        cell_zigzag[i] = cz

    # 存储 zigzag 扫描线，供可视化复用
    zigzag_lines_store: Dict[int, List[LineString]] = {}
    for i, cz in cell_zigzag.items():
        # 用任意一个有效的 corner 拿扫描线（四条 corner 共享相同的 lines）
        for corner in VALID_CORNERS:
            bp = cz.paths.get(corner)
            if bp is not None and bp.lines:
                zigzag_lines_store[i] = list(bp.lines)
                break

    # 3. 预构建 A* 障碍物掩码（只构建一次，所有 A* 调用共用）
    #    分辨率依区域尺寸自适应：对角线 / 50，下限 radius*0.2，上限 radius*0.8
    tgt_bounds = Polygon(target.vertices).bounds
    region_diag = math.hypot(tgt_bounds[2] - tgt_bounds[0],
                              tgt_bounds[3] - tgt_bounds[1])
    astar_resolution = max(radius * 0.05, min(radius * 0.2, region_diag / 60))
    astar_prebuilt = None
    if obstacle_polys:
        all_pts = [plat_pos]
        for obs in obstacle_polys:
            b = obs.bounds
            all_pts.extend([(b[0], b[1]), (b[2], b[3])])
        for cell_poly in cells:
            b = cell_poly.bounds
            all_pts.extend([(b[0], b[1]), (b[2], b[3])])
        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        margin = 1.0
        xmin, xmax = min(xs) - margin, max(xs) + margin
        ymin, ymax = min(ys) - margin, max(ys) + margin
        mask = _build_obstacle_mask(
            obstacle_polys, (xmin, ymin, xmax, ymax), astar_resolution)
        astar_prebuilt = (mask, (xmin, ymin, xmax, ymax))

    # 4. 贪心遍历：用直线距离选最近入口，A* 只算一次
    unvisited: Set[int] = set(range(n))
    current_pos = plat_pos
    cell_order: List[int] = []
    segments: List[TraversalSegment] = []
    full_path: List[Tuple[float, float]] = []

    while unvisited:
        # Phase 1: 用直线距离选最佳 cell+corner（不调 A*）
        best_dist = float('inf')
        best_cell = -1
        best_corner = None
        best_bp = None

        for ci in unvisited:
            cz = cell_zigzag[ci]
            for corner in VALID_CORNERS:
                bp = cz.paths.get(corner)
                if bp is None or not bp.path:
                    continue
                d = dist_2d(current_pos, bp.entry_point)
                if d < best_dist:
                    best_dist = d
                    best_cell = ci
                    best_corner = corner
                    best_bp = bp

        if best_cell < 0:
            break

        # Phase 2: 只对选中的 corner 做一次 A* 路径搜索
        inter_path = astar_path(current_pos, best_bp.entry_point, obstacle_polys,
                                resolution=astar_resolution,
                                prebuilt_mask=astar_prebuilt)
        inter_cost = sum(dist_2d(inter_path[i], inter_path[i + 1])
                        for i in range(len(inter_path) - 1))

        # 到达段（approach 或 inter_cell）
        seg_type = "approach" if not cell_order else "inter_cell"
        segments.append(TraversalSegment(
            segment_type=seg_type,
            cell_index=None,
            entry_point=current_pos,
            exit_point=best_bp.entry_point,
            path=inter_path,
            length_km=inter_cost,
        ))
        # 到达段：第一个 approach 保留全部，后续 inter_cell 去重第一个点
        if not cell_order:
            full_path.extend(inter_path)
        else:
            full_path.extend(inter_path[1:])

        # Cell 覆盖段 — 去重第一个点（到达段终点 == cell_path 起点）
        cell_path = list(best_bp.path)
        cell_cost = best_bp.total_length
        segments.append(TraversalSegment(
            segment_type="cell_cover",
            cell_index=best_cell,
            entry_point=best_bp.entry_point,
            exit_point=best_bp.exit_point if best_bp.exit_point else cell_path[-1],
            path=cell_path,
            length_km=cell_cost,
        ))
        full_path.extend(cell_path[1:])

        cell_order.append(best_cell)
        unvisited.remove(best_cell)
        current_pos = best_bp.exit_point if best_bp.exit_point else cell_path[-1]

    total_len = sum(seg.length_km for seg in segments)

    return CoveragePlanResult(
        platform_id=platform.id,
        target_id=target.id,
        full_path=full_path,
        segments=segments,
        total_length_km=total_len,
        cells=cells,
        cell_order=cell_order,
        obstacles=merged_obs,
        cell_zigzag_lines=zigzag_lines_store,
    )


# ══════════════════════════════════════════════
# 场景级入口
# ══════════════════════════════════════════════

def plan_coverage_scenario(
    platforms: List[PlatformSpec],
    targets: List[TargetArea],
    no_fly_zones: List[NoFlyZone],
    pairs: List[PairSpec],
) -> List[CoveragePlanResult]:
    """处理整个场景的覆盖路径规划。

    Args:
        platforms: 平台列表
        targets: 目标区域列表
        no_fly_zones: 禁飞区列表（圆柱）
        pairs: 配对关系
        scan_angle_deg: 扫描方向角度

    Returns:
        每个 pair 一个 CoveragePlanResult
    """
    # 构建查找字典
    plat_dict = {p.id: p for p in platforms}
    target_dict = {t.id: t for t in targets}

    # 禁飞区：六边形用于 cell 分解，圆形用于 A* 避障
    obstacle_xy_list = [cylinder_to_hexagon(z.center_xy, z.radius_km)
                        for z in no_fly_zones]
    obstacle_polys_astar = [Point(z.center_xy).buffer(z.radius_km, resolution=16)
                            for z in no_fly_zones]

    results = []
    for pair in pairs:
        plat = plat_dict.get(pair.platform_id)
        tgt = target_dict.get(pair.target_id)
        if plat is None or tgt is None:
            continue

        result = plan_single_coverage(
            plat, tgt, obstacle_xy_list, obstacle_polys_astar)
        results.append(result)

    return results


# ══════════════════════════════════════════════
# 可视化
# ══════════════════════════════════════════════

def visualize_cell_decomposition(
    result: CoveragePlanResult,
    platform: PlatformSpec,
    target: TargetArea,
    obstacles_xy: List[List[Tuple[float, float]]],
    save_path: str = None,
    show_plot: bool = True,
):
    """图1: Cell 分解示意图 — 目标区域、禁飞区、cell 编号、遍历顺序箭头。"""
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch

    fig, ax = plt.subplots(1, 1, figsize=(12, 10))
    ax.set_aspect('equal')

    _draw_polygon(ax, target.vertices, edgecolor='none',
                  facecolor='#e0e0e0', linewidth=0)

    _draw_nfz_circles(ax, obstacles_xy)

    cmap = plt.cm.Pastel1
    plat_xy = platform.position_xy

    # Cells
    for i, poly in enumerate(result.cells):
        coords = list(poly.exterior.coords)
        _draw_polygon(ax, coords, edgecolor='#888888',
                      facecolor=cmap(i % 9), alpha=0.25, linewidth=0.8)
        cx, cy = poly.centroid.x, poly.centroid.y
        ax.text(cx, cy, str(i + 1), fontsize=10, ha='center', va='center',
                fontweight='bold')

    # Platform
    ax.scatter(*plat_xy, color='#2980b9', s=250, marker='^',
               zorder=15, edgecolors='#1a5276', linewidths=1.5)

    # 遍历顺序标注（在 cell 质心）
    for idx, ci in enumerate(result.cell_order):
        c = result.cells[ci].centroid
        ax.text(c.x, c.y + 0.12, f'[{idx + 1}]', fontsize=8, ha='center',
                va='bottom', color='darkred', fontweight='bold')

    # 流通箭头：使用真实 zigzag 端点，而非 cell 质心
    # segments layout: [approach, cell_cover_0, inter_cell_1, cell_cover_1, ...]
    segs = result.segments
    # 构建箭头路径点：
    #   step 0: plat_xy → segs[0].exit_point  (approach → cell_0 entry)
    #   step k: segs[2*k-1].exit_point → segs[2*k].exit_point (cell exit → next entry)
    arrows_from = [plat_xy]
    arrows_to = [segs[0].exit_point] if segs else []
    for k in range(1, len(result.cell_order)):
        prev_exit = segs[2 * k - 1].exit_point  # cell_cover_(k-1) exit
        next_entry = segs[2 * k].exit_point       # inter_cell_k exit = cell_k entry
        arrows_from.append(prev_exit)
        arrows_to.append(next_entry)

    for idx, (frm, to) in enumerate(zip(arrows_from, arrows_to)):
        color = 'blue' if idx == 0 else 'darkorange'
        lw = 2.5 if idx == 0 else 1.8
        arrow = FancyArrowPatch(frm, to, arrowstyle='->',
                                mutation_scale=18, color=color,
                                linewidth=lw, zorder=12)
        ax.add_patch(arrow)
        mid_x, mid_y = (frm[0] + to[0]) / 2, (frm[1] + to[1]) / 2
        ax.text(mid_x, mid_y, str(idx + 1), fontsize=10, ha='center', va='center',
                color='white', fontweight='bold', zorder=13,
                bbox=dict(boxstyle='circle,pad=0.18', facecolor='darkred', alpha=0.85))

    all_pts = [(plat_xy[0], plat_xy[1])] + target.vertices
    _set_bounds(ax, all_pts)

    ax.set_title(f"{result.platform_id} -> {_short_id(result.target_id)}  |  "
                 f"{len(result.cells)} cells, order {[c+1 for c in result.cell_order]}",
                 fontsize=11, fontweight='bold')
    ax.set_xlabel('x (km)'); ax.set_ylabel('y (km)')
    plt.tight_layout(pad=0.5)
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"  [1/5] cell_decomp saved: {save_path}")
    if show_plot:
        plt.show()
    else:
        plt.close()


def visualize_cell_zigzag_lines(
    result: CoveragePlanResult,
    platform: PlatformSpec,
    target: TargetArea,
    obstacles_xy: List[List[Tuple[float, float]]],
    save_path: str = None,
    show_plot: bool = True,
):
    """图2: 各 Cell 的 Zigzag 平行扫描线示意图。"""
    import matplotlib.pyplot as plt

    n_cells = len(result.cells)
    n_cols = max(2, int(math.ceil(math.sqrt(n_cells))))
    n_rows = int(math.ceil(n_cells / n_cols))

    fig, axes = plt.subplots(n_rows, n_cols,
                              figsize=(n_cols * 4.5, n_rows * 4))
    # flatten
    if n_rows * n_cols == 1:
        axes = [[axes]]
    elif n_rows == 1:
        axes = [axes]
    elif n_cols == 1:
        axes = [[ax] for ax in axes]

    cmap = plt.cm.tab20
    radius = platform.detection_radius_km

    for ci in range(n_cells):
        row = ci // n_cols
        col = ci % n_cols
        ax = axes[row][col]
        ax.set_aspect('equal')

        poly = result.cells[ci]
        coords = list(poly.exterior.coords)
        if len(coords) > 1 and coords[0] == coords[-1]:
            coords = coords[:-1]

        _draw_polygon(ax, coords, edgecolor='black',
                      facecolor=cmap(ci % 20), alpha=0.2, linewidth=1.2)

        # 扫描线画在 cell 轮廓上面，确保边界线可见
        lines = result.cell_zigzag_lines.get(ci, [])
        for line in lines:
            lc = list(line.coords)
            if len(lc) >= 2:
                ax.plot([lc[0][0], lc[-1][0]], [lc[0][1], lc[-1][1]],
                        color='darkblue', linewidth=2.2, alpha=0.9, zorder=5)

        n_lines = len(lines)
        try:
            order_pos = result.cell_order.index(ci)
            label = f'Cell {ci + 1}  [{order_pos + 1}]  ({n_lines} lines)'
            label_color = 'darkred'
        except ValueError:
            label = f'Cell {ci + 1}  ({n_lines} lines)'
            label_color = 'black'
        ax.set_title(label, fontsize=9, fontweight='bold', color=label_color)
        ax.set_xticks([])
        ax.set_yticks([])
        xs = [p[0] for p in coords]
        ys = [p[1] for p in coords]
        ax.set_xlim(min(xs), max(xs))
        ax.set_ylim(min(ys), max(ys))

    # 隐藏多余子图
    for ci in range(n_cells, n_rows * n_cols):
        row = ci // n_cols
        col = ci % n_cols
        axes[row][col].set_visible(False)

    total_lines = sum(len(result.cell_zigzag_lines.get(ci, [])) for ci in range(len(result.cells)))
    fig.suptitle(f"{result.platform_id} -> {_short_id(result.target_id)}  |  "
                 f"radius={radius:.1f}km  |  {total_lines} total lines, {n_cells} cells",
                 fontsize=12, fontweight='bold')
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"  [2/5] cell_zigzag saved: {save_path}")
    if show_plot:
        plt.show()
    else:
        plt.close()


def visualize_traversal_flow(
    result: CoveragePlanResult,
    platform: PlatformSpec,
    target: TargetArea,
    obstacles_xy: List[List[Tuple[float, float]]],
    save_path: str = None,
    show_plot: bool = True,
):
    """图3: Traversal flow — arrows between cell entry/exit points."""
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch

    fig, ax = plt.subplots(1, 1, figsize=(12, 10))
    ax.set_aspect('equal')

    _draw_polygon(ax, target.vertices, edgecolor='none',
                  facecolor='#e0e0e0', linewidth=0)
    _draw_nfz_circles(ax, obstacles_xy)

    cmap = plt.cm.Pastel1
    plat_xy = platform.position_xy

    # Cells with fill
    for i, poly in enumerate(result.cells):
        coords = list(poly.exterior.coords)
        _draw_polygon(ax, coords, edgecolor='#aaaaaa',
                      facecolor=cmap(i % 20), alpha=0.15, linewidth=0.8)
        cx, cy = poly.centroid.x, poly.centroid.y
        ax.text(cx, cy, str(i + 1), fontsize=8, ha='center', va='center',
                color='gray', fontweight='normal')

    # 平台
    ax.scatter(*plat_xy, color='#2980b9', s=250, marker='^',
               zorder=15, edgecolors='#1a5276', linewidths=1.5)
    ax.text(plat_xy[0], plat_xy[1] + 0.15, 'PLATFORM', fontsize=8,
            ha='center', va='bottom', color='blue', fontweight='bold')

    # 绘制实际遍历路径：使用真实 zigzag 端点
    segs = result.segments
    arrows_from = [plat_xy]
    arrows_to = [segs[0].exit_point] if segs else []
    for k in range(1, len(result.cell_order)):
        arrows_from.append(segs[2 * k - 1].exit_point)
        arrows_to.append(segs[2 * k].exit_point)

    for idx, (frm, to) in enumerate(zip(arrows_from, arrows_to)):
        alpha_step = 0.4 + 0.6 * (idx / max(len(arrows_from) - 1, 1))
        color = 'darkred' if idx == 0 else 'darkorange'
        lw = 3.0 if idx == 0 else 2.2

        ax.plot([frm[0], to[0]], [frm[1], to[1]],
                color=color, linewidth=lw, alpha=alpha_step, zorder=10)

        arrow = FancyArrowPatch(frm, to, arrowstyle='->',
                                mutation_scale=20, color=color,
                                linewidth=lw, alpha=alpha_step, zorder=12)
        ax.add_patch(arrow)

        mid_x = (frm[0] + to[0]) / 2
        mid_y = (frm[1] + to[1]) / 2
        ax.text(mid_x, mid_y, str(idx + 1), fontsize=11, ha='center', va='center',
                color='white', fontweight='bold', zorder=14,
                bbox=dict(boxstyle='circle,pad=0.2', facecolor=color, alpha=0.9))

    # 高亮当前遍历到的 cell
    for idx, ci in enumerate(result.cell_order):
        c = result.cells[ci].centroid
        ax.text(c.x, c.y, f'{ci+1}\n[{idx+1}]', fontsize=9, ha='center', va='center',
                color='black', fontweight='bold', zorder=13,
                bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.85))

    all_pts = [(plat_xy[0], plat_xy[1])] + target.vertices
    _set_bounds(ax, all_pts)

    ax.set_title(f"{result.platform_id} -> {_short_id(result.target_id)}  |  "
                 f"traversal: {[c+1 for c in result.cell_order]}",
                 fontsize=11, fontweight='bold')
    ax.set_xlabel('x (km)'); ax.set_ylabel('y (km)')
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"  [3/5] traversal_flow saved: {save_path}")
    if show_plot:
        plt.show()
    else:
        plt.close()


def visualize_full_path(
    result: CoveragePlanResult,
    platform: PlatformSpec,
    target: TargetArea,
    obstacles_xy: List[List[Tuple[float, float]]],
    save_path: str = None,
    show_plot: bool = True,
):
    """图4: Full coverage path — approach (cyan solid), cell zigzag (colored solid per cell), inter-cell (dashed)."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    fig, ax = plt.subplots(1, 1, figsize=(12, 10))
    ax.set_aspect('equal')

    # Region: gray fill, no border
    _draw_polygon(ax, target.vertices, edgecolor='none',
                  facecolor='#e8e8e8', linewidth=0)
    # NFZ: red fill
    _draw_nfz_circles(ax, obstacles_xy)

    n_cells = len(result.cells)

    # Cell outline: faint dashed
    if n_cells > 1:
        for i, poly in enumerate(result.cells):
            coords = list(poly.exterior.coords)
            _draw_polygon(ax, coords, edgecolor='#bbbbbb', facecolor='none',
                          alpha=0.5, linewidth=0.4, linestyle='--')

    cell_cmap = plt.cm.Set1

    full_px = [p[0] for p in result.full_path]
    full_py = [p[1] for p in result.full_path]

    offset = 0
    for seg in result.segments:
        n = len(seg.path) if seg.path else 0
        if n < 2:
            continue

        if seg.segment_type == 'approach':
            color, lw, style, alpha = '#00bcd4', 2.5, '-', 0.95
        elif seg.segment_type == 'inter_cell':
            color, lw, style, alpha = '#e91e63', 1.5, '--', 0.7
        elif seg.segment_type == 'cell_cover':
            ci = seg.cell_index if seg.cell_index is not None else 0
            color = cell_cmap(ci % 9)
            lw, style, alpha = 2.5, '-', 0.9
        else:
            continue

        start = offset if offset == 0 else offset - 1
        seg_px = full_px[start:start + n]
        seg_py = full_py[start:start + n]
        ax.plot(seg_px, seg_py, color=color, linewidth=lw, linestyle=style,
                alpha=alpha, solid_capstyle='round')

        offset += n if offset == 0 else n - 1

    # Start marker
    if result.full_path:
        ax.scatter(*result.full_path[0], color='#27ae60', s=180, marker='*',
                   zorder=20, edgecolors='#1e8449', linewidths=1.5)

    # Cell entry sequence numbers along the path
    if result.segments:
        # Step 0: platform (approach entry)
        ax.annotate('0', xy=result.full_path[0], fontsize=8, ha='right', va='bottom',
                   fontweight='bold', color='#2980b9',
                   bbox=dict(boxstyle='round,pad=0.15', facecolor='white', alpha=0.8))

    seg_idx = 0
    for order, ci in enumerate(result.cell_order):
        # cell entry = the approach/inter_cell segment's exit_point
        approach_seg = result.segments[seg_idx]  # approach or inter_cell
        entry_pt = approach_seg.exit_point
        if entry_pt is not None:
            ax.scatter(*entry_pt, color='white', s=50, marker='o',
                       zorder=21, edgecolors='#333333', linewidths=1.0)
            ax.annotate(str(order + 1), xy=entry_pt, fontsize=7,
                       ha='center', va='center', fontweight='bold', color='#333333',
                       zorder=22)
        seg_idx += 2  # skip cell_cover to next approach/inter_cell

    # End marker
    if result.full_path:
        ax.scatter(*result.full_path[-1], color='#e74c3c', s=140, marker='X',
                   zorder=20, edgecolors='#922b21', linewidths=1.5)

    # Legend: only the 3 line types
    legend_items = [
        Line2D([0], [0], color='#00bcd4', linewidth=2.5, label='approach'),
        Line2D([0], [0], color='#333333', linewidth=2.5, label='cell cover (zigzag, solid, per-cell color)'),
        Line2D([0], [0], color='#e91e63', linestyle='--', linewidth=1.5, label='inter-cell A* (dashed)'),
    ]
    ax.legend(handles=legend_items, fontsize=9, loc='upper right',
              framealpha=0.9)

    all_pts = [(platform.position_xy[0], platform.position_xy[1])] + target.vertices
    _set_bounds(ax, all_pts)

    ax.set_title(f"{result.platform_id} -> {_short_id(result.target_id)}  |  "
                 f"{result.total_length_km:.1f} km  |  "
                 f"{n_cells} cells",
                 fontsize=11, fontweight='bold')
    ax.set_xlabel('x (km)'); ax.set_ylabel('y (km)')
    plt.tight_layout(pad=0.5)
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"  [4/5] full_path saved: {save_path}")
    if show_plot:
        plt.show()
    else:
        plt.close()


# ══════════════════════════════════════════════
# 总览图
# ══════════════════════════════════════════════

def visualize_overview(
    results: List[CoveragePlanResult],
    platforms: List[PlatformSpec],
    targets: List[TargetArea],
    obstacles_xy: List[List[Tuple[float, float]]],
    save_path: str = None,
    show_plot: bool = True,
):
    """将所有 platform→target 对的结果绘制在一张总览图中。"""
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MPLPolygon
    from matplotlib.lines import Line2D

    fig, ax = plt.subplots(1, 1, figsize=(16, 12))
    ax.set_aspect('equal')

    # 平台颜色映射
    plat_colors = plt.cm.tab10
    plat_color_map: Dict[str, str] = {}
    for i, p in enumerate(platforms):
        plat_color_map[p.id] = plat_colors(i % 10)

    # 绘制所有禁飞区
    _draw_nfz_circles(ax, obstacles_xy)

    # 绘制所有目标区域
    tgt_style = {}
    tgt_colors = plt.cm.Set3
    for i, t in enumerate(targets):
        tgt_style[t.id] = tgt_colors(i % 12)
        _draw_polygon(ax, t.vertices, edgecolor='black',
                      facecolor=tgt_style[t.id], alpha=0.15, linewidth=2)
        c = polygon_centroid_2d(t.vertices)
        ax.text(c[0], c[1], _short_id(t.id), fontsize=11, ha='center', va='center',
                fontweight='bold', color='black',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

    # 绘制所有平台位置
    for p in platforms:
        color = plat_color_map[p.id]
        ax.scatter(*p.position_xy, color=color, s=250, marker='^',
                   zorder=15, edgecolors='black', linewidths=1.5)
        ax.text(p.position_xy[0], p.position_xy[1] + 0.3, p.id,
                fontsize=9, ha='center', va='bottom', fontweight='bold', color=color)

    # 绘制每条路径
    for result in results:
        p_color = plat_color_map[result.platform_id]

        for seg in result.segments:
            if not seg.path or len(seg.path) < 2:
                continue
            px = [p[0] for p in seg.path]
            py = [p[1] for p in seg.path]

            if seg.segment_type == 'approach':
                lw, style, alpha = 1.8, '-', 0.8
                color = p_color
            elif seg.segment_type == 'inter_cell':
                lw, style, alpha = 1.2, '--', 0.6
                color = p_color
            elif seg.segment_type == 'cell_cover':
                lw, style, alpha = 2.0, '-', 0.75
                color = p_color
            else:
                lw, style, alpha = 1.0, '--', 0.5
                color = 'gray'
            ax.plot(px, py, color=color, linewidth=lw, linestyle=style, alpha=alpha)

        # 起点/终点
        if result.full_path:
            ax.scatter(*result.full_path[0], color=p_color, s=80, marker='*',
                       zorder=16, edgecolors='black', linewidths=0.8)
            ax.scatter(*result.full_path[-1], color=p_color, s=80, marker='X',
                       zorder=16, edgecolors='black', linewidths=0.8)

    # 图例
    legend_handles = []
    for p in platforms:
        color = plat_color_map[p.id]
        legend_handles.append(
            Line2D([0], [0], marker='^', color='w', markerfacecolor=color,
                   markersize=10, label=f'{p.id} (r={p.detection_radius_km}km)'))
    if obstacles_xy:
        legend_handles.append(
            MPLPolygon([(0, 0)], facecolor='#e74c3c', edgecolor='#c0392b',
                       alpha=0.3, label='No-fly Zone'))
    legend_handles.append(Line2D([0], [0], marker='*', color='w', markerfacecolor='green',
                                  markersize=10, label='Start'))
    legend_handles.append(Line2D([0], [0], marker='X', color='w', markerfacecolor='red',
                                  markersize=10, label='End'))

    ax.legend(handles=legend_handles, fontsize=8, loc='upper right',
              ncol=min(2, len(legend_handles)))

    # 收集所有点计算 bounds
    all_pts = []
    for p in platforms:
        all_pts.append((p.position_xy[0], p.position_xy[1]))
    for t in targets:
        all_pts.extend([(v[0], v[1]) for v in t.vertices])
    _set_bounds(ax, all_pts)

    n_pairs = len(results)
    total_len = sum(r.total_length_km for r in results)
    ax.set_title(f"Coverage Overview  |  "
                 f"{len(platforms)} platforms, {len(targets)} targets, "
                 f"{n_pairs} pairs  |  total {total_len:.1f} km",
                 fontsize=12, fontweight='bold')
    ax.set_xlabel('x (km)'); ax.set_ylabel('y (km)')

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"  Overview saved: {save_path}")
    if show_plot:
        plt.show()
    else:
        plt.close()


def animate_coverage_plan(
    result: CoveragePlanResult,
    platform: PlatformSpec,
    target: TargetArea,
    obstacles_xy: List[List[Tuple[float, float]]],
    save_path: str,
    fps: int = 30,
    step: int = 3,
):
    """生成覆盖路径的动态 GIF，显示平台沿路径运动。"""
    import matplotlib.pyplot as plt
    import matplotlib.animation as animation
    from matplotlib.patches import Polygon as MPLPolygon
    from matplotlib.lines import Line2D

    # 预处理：按 segment 收集路径点 + 颜色
    all_pts: List[Tuple[float, float, str]] = []  # (x, y, segment_type)
    cmap = plt.cm.tab20

    for seg in result.segments:
        if not seg.path or len(seg.path) < 2:
            continue
        for pt in seg.path:
            if seg.segment_type == 'cell_cover':
                ci = seg.cell_index if seg.cell_index is not None else 0
                all_pts.append((pt[0], pt[1], f'cell_{ci}'))
            else:
                all_pts.append((pt[0], pt[1], seg.segment_type))

    # 去重：移除与前一点几乎重合的点
    deduped = [all_pts[0]]
    for pt in all_pts[1:]:
        d = math.hypot(pt[0] - deduped[-1][0], pt[1] - deduped[-1][1])
        if d > 1e-6:
            deduped.append(pt)

    # 采样
    pts = deduped[::step]
    if len(deduped) > 0 and len(deduped) % step != 1:
        pts.append(deduped[-1])
    n_frames = len(pts)

    # 建图
    fig, axes = plt.subplots(1, 2, figsize=(18, 8))
    plat_xy = platform.position_xy

    for ax in axes:
        ax.set_aspect('equal')
        _draw_polygon(ax, target.vertices, edgecolor='black',
                      facecolor='whitesmoke', linewidth=2)
        _draw_nfz_circles(ax, obstacles_xy)
        for i, poly in enumerate(result.cells):
            coords = list(poly.exterior.coords)
            _draw_polygon(ax, coords, edgecolor='gray', facecolor='none',
                          alpha=0.3, linewidth=0.5)

        all_pts_bounds = [(plat_xy[0], plat_xy[1])] + target.vertices
        _set_bounds(ax, all_pts_bounds)

    # 左图：cell 分解 + 遍历标注
    ax_l = axes[0]
    cmap_l = plt.cm.tab20
    for i, poly in enumerate(result.cells):
        coords = list(poly.exterior.coords)
        _draw_polygon(ax_l, coords, edgecolor='black',
                      facecolor=cmap_l(i % 20), alpha=0.3, linewidth=1)
        cx, cy = poly.centroid.x, poly.centroid.y
        ax_l.text(cx, cy, str(i + 1), fontsize=9, ha='center', va='center',
                  fontweight='bold')
    for idx, ci in enumerate(result.cell_order):
        poly = result.cells[ci]
        c = poly.centroid
        ax_l.text(c.x, c.y + 0.15, f'[{idx + 1}]', fontsize=7, ha='center',
                  va='bottom', color='red', fontweight='bold')

    from matplotlib.patches import FancyArrowPatch
    prev_xy_arrow = plat_xy
    for idx, ci in enumerate(result.cell_order):
        cc = result.cells[ci].centroid
        cxy = (cc.x, cc.y)
        arrow = FancyArrowPatch(prev_xy_arrow, cxy, arrowstyle='->',
                                mutation_scale=15,
                                color='darkorange' if idx > 0 else 'blue',
                                linewidth=2.0 if idx == 0 else 1.5,
                                linestyle='-' if idx == 0 else '--', zorder=12)
        ax_l.add_patch(arrow)
        mid_x, mid_y = (prev_xy_arrow[0] + cxy[0]) / 2, (prev_xy_arrow[1] + cxy[1]) / 2
        ax_l.text(mid_x, mid_y, str(idx + 1), fontsize=9, ha='center', va='center',
                  color='white', fontweight='bold', zorder=13,
                  bbox=dict(boxstyle='circle,pad=0.15', facecolor='darkred', alpha=0.85))
        prev_xy_arrow = cxy

    ax_l.scatter(*plat_xy, color='#2980b9', s=200, marker='^', zorder=15,
                 edgecolors='darkblue', linewidths=1, label='Platform')
    ax_l.legend(fontsize=7, loc='upper right')
    ax_l.set_title(f"Cell Decomposition & Traversal Order\n"
                   f"Cells: {len(result.cells)}, Order: {[c+1 for c in result.cell_order]}")

    # 右图：动态路径
    ax_r = axes[1]
    ax_r.scatter(*plat_xy, color='#2980b9', s=200, marker='^', zorder=15,
                 edgecolors='darkblue', linewidths=1)
    trail_line, = ax_r.plot([], [], 'cyan', linewidth=2, alpha=0.9)
    platform_dot, = ax_r.plot([], [], 'o', color='blue', markersize=12,
                               zorder=20, markeredgecolor='darkblue', markeredgewidth=1.5)

    # 为不同 segment 类型绘制已完成的路径
    segment_lines: Dict[str, Tuple] = {}

    title_text = ax_r.text(0.5, 1.02, '', transform=ax_r.transAxes, ha='center',
                           fontsize=10, fontweight='bold')
    ax_r.set_title(f"Coverage Path Animation\n"
                   f"Platform: {result.platform_id} → Target: {result.target_id}")

    custom_lines = [
        Line2D([0], [0], color='cyan', linewidth=2, label='Approach'),
        Line2D([0], [0], color='darkorange', linewidth=2.5, label='Cell Zigzag'),
        Line2D([0], [0], color='magenta', linestyle='--', linewidth=1.5, label='Inter-cell'),
    ]
    ax_r.legend(handles=custom_lines, fontsize=7, loc='upper right')

    plt.suptitle("Region Coverage Path — Animation", fontsize=14, fontweight='bold')
    plt.tight_layout()

    # 累积路径数据结构
    cum_paths: Dict[str, Tuple[List[float], List[float]]] = {}
    current_seg = pts[0][2] if pts else ''
    cum_x, cum_y = [], []

    def init():
        trail_line.set_data([], [])
        platform_dot.set_data([], [])
        return [trail_line, platform_dot]

    def update(frame):
        nonlocal current_seg, cum_x, cum_y
        x, y, seg_type = pts[frame]

        if seg_type != current_seg:
            # 保存上一段
            if cum_x:
                key = current_seg
                if key not in cum_paths:
                    cum_paths[key] = ([], [])
                cum_paths[key][0].extend(cum_x)
                cum_paths[key][1].extend(cum_y)
            cum_x, cum_y = [], []
            current_seg = seg_type

        cum_x.append(x)
        cum_y.append(y)
        platform_dot.set_data([x], [y])

        # 绘制所有已完成段 + 当前段
        # 先绘制已保存的段
        artists = [platform_dot]
        all_seg_keys = list(cum_paths.keys()) + ([current_seg] if cum_x else [])
        for key in all_seg_keys:
            if key == current_seg and cum_x:
                lx, ly = cum_x[:], cum_y[:]
            elif key in cum_paths:
                lx, ly = cum_paths[key][0], cum_paths[key][1]
            else:
                continue

            if key == 'approach':
                color, lw, ls = 'cyan', 2.0, '-'
            elif key == 'inter_cell':
                color, lw, ls = 'magenta', 1.5, '--'
            elif key.startswith('cell_'):
                ci = int(key.split('_')[1])
                color, lw, ls = cmap(ci % 20), 2.5, '-'
            else:
                color, lw, ls = 'gray', 1.5, '-'

            line, = ax_r.plot(lx, ly, color=color, linewidth=lw, linestyle=ls, alpha=0.85)
            artists.append(line)

        progress = (frame + 1) / n_frames * 100
        dist_done = sum(math.hypot(pts[i][0] - pts[i-1][0], pts[i][1] - pts[i-1][1])
                        for i in range(1, frame + 1))
        title_text.set_text(f"Progress: {progress:.0f}%  |  "
                           f"Path: {dist_done:.1f} / {result.total_length_km:.1f} km")

        return artists + [title_text]

    ani = animation.FuncAnimation(fig, update, frames=n_frames,
                                   init_func=init, interval=1000 // fps,
                                   blit=False, repeat=True)
    ani.save(save_path, writer='pillow', fps=fps, dpi=120)
    plt.close()
    print(f"  Animation saved: {save_path}")


def interactive_html(
    result: CoveragePlanResult,
    platform: PlatformSpec,
    target: TargetArea,
    obstacles_xy: List[List[Tuple[float, float]]],
    save_path: str,
):
    """生成可拖拽进度条的交互式 HTML（plotly）。

    右图始终显示完整路径（含 cell 间流通线），滑块平滑移动当前位置标记。
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    # ── 收集路径点 ──
    seg_data: List[Tuple[float, float, str, int]] = []  # x, y, seg_type, cell_idx
    for seg in result.segments:
        if not seg.path or len(seg.path) < 2:
            continue
        ci = seg.cell_index if seg.cell_index is not None else -1
        for pt in seg.path:
            seg_data.append((pt[0], pt[1], seg.segment_type, ci))

    # 去重
    deduped = [seg_data[0]]
    for pt in seg_data[1:]:
        if math.hypot(pt[0] - deduped[-1][0], pt[1] - deduped[-1][1]) > 1e-6:
            deduped.append(pt)

    total_pts = len(deduped)
    all_x = [p[0] for p in deduped]
    all_y = [p[1] for p in deduped]

    cmap = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
        '#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5',
        '#c49c94', '#f7b6d2', '#c7c7c7', '#dbdb8d', '#9edae5',
    ]

    plat_x, plat_y = platform.position_xy

    # ── 建图 ──
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=(
            f"Cell Decomposition (Order: {[c+1 for c in result.cell_order]})",
            f"Coverage Path — {result.platform_id} → {result.target_id}  "
            f"({result.total_length_km:.1f} km)"
        ),
        column_widths=[0.45, 0.55],
        horizontal_spacing=0.06,
    )

    # ══════════════════════════════════════════
    # 左图：Cell 分解 + 遍历标注
    # ══════════════════════════════════════════

    # 目标区域
    tx, ty = zip(*target.vertices)
    fig.add_trace(go.Scatter(x=list(tx) + [tx[0]], y=list(ty) + [ty[0]],
                              fill='toself', fillcolor='whitesmoke',
                              line=dict(color='black', width=2),
                              name='Target Region', showlegend=True), row=1, col=1)

    # 障碍物
    for i, obs in enumerate(obstacles_xy):
        ox, oy = zip(*obs)
        fig.add_trace(go.Scatter(x=list(ox) + [ox[0]], y=list(oy) + [oy[0]],
                                  fill='toself', fillcolor='lightcoral',
                                  line=dict(color='darkred', width=1.5),
                                  opacity=0.5, name='No-fly Zone' if i == 0 else None,
                                  showlegend=(i == 0)), row=1, col=1)

    # Cells
    for i, poly in enumerate(result.cells):
        coords = list(poly.exterior.coords)
        cx, cy = zip(*coords)
        color = cmap[i % len(cmap)]
        fig.add_trace(go.Scatter(x=list(cx), y=list(cy),
                                  fill='toself', fillcolor=color,
                                  line=dict(color='black', width=1),
                                  opacity=0.3, name=f'Cell {i+1}',
                                  showlegend=False), row=1, col=1)
        c = poly.centroid
        fig.add_annotation(x=c.x, y=c.y, text=str(i + 1),
                            showarrow=False, font=dict(size=11, color='black'),
                            row=1, col=1)

    # 遍历顺序标签
    for idx, ci in enumerate(result.cell_order):
        c = result.cells[ci].centroid
        fig.add_annotation(x=c.x, y=c.y + 0.12, text=f'<b>[{idx + 1}]</b>',
                            showarrow=False, font=dict(size=9, color='red'),
                            row=1, col=1)

    # 流通箭头 + 步号
    prev_x, prev_y = plat_x, plat_y
    for idx, ci in enumerate(result.cell_order):
        cc = result.cells[ci].centroid
        color = 'blue' if idx == 0 else 'darkorange'
        dash = 'solid' if idx == 0 else 'dash'
        fig.add_trace(go.Scatter(x=[prev_x, cc.x], y=[prev_y, cc.y],
                                  mode='lines+markers',
                                  line=dict(color=color, width=2, dash=dash),
                                  marker=dict(size=6, symbol='arrow',
                                             angleref='previous'),
                                  showlegend=False), row=1, col=1)
        mid_x, mid_y = (prev_x + cc.x) / 2, (prev_y + cc.y) / 2
        fig.add_annotation(x=mid_x, y=mid_y, text=f'<b>{idx + 1}</b>',
                            showarrow=False,
                            font=dict(size=10, color='white'),
                            bgcolor='darkred', borderpad=2, row=1, col=1)
        prev_x, prev_y = cc.x, cc.y

    # 平台
    fig.add_trace(go.Scatter(x=[plat_x], y=[plat_y], mode='markers',
                              marker=dict(size=14, symbol='triangle-up',
                                         color='blue',
                                         line=dict(color='darkblue', width=2)),
                              name='Platform'), row=1, col=1)

    # ══════════════════════════════════════════
    # 右图：完整路径（始终可见）+ 进度标记
    # ══════════════════════════════════════════

    # 区域 + 障碍物
    fig.add_trace(go.Scatter(x=list(tx) + [tx[0]], y=list(ty) + [ty[0]],
                              fill='toself', fillcolor='whitesmoke',
                              line=dict(color='black', width=2),
                              showlegend=False), row=1, col=2)
    for obs in obstacles_xy:
        ox, oy = zip(*obs)
        fig.add_trace(go.Scatter(x=list(ox) + [ox[0]], y=list(oy) + [oy[0]],
                                  fill='toself', fillcolor='lightcoral',
                                  line=dict(color='darkred', width=1.5),
                                  opacity=0.5, showlegend=False), row=1, col=2)

    # Cell 轮廓
    for poly in result.cells:
        coords = list(poly.exterior.coords)
        cx, cy = zip(*coords)
        fig.add_trace(go.Scatter(x=list(cx), y=list(cy),
                                  line=dict(color='gray', width=0.5),
                                  fill='none', showlegend=False), row=1, col=2)

    # 始终显示完整路径（按 segment 拆分，不同颜色/线型）
    for seg in result.segments:
        if not seg.path or len(seg.path) < 2:
            continue
        sx = [p[0] for p in seg.path]
        sy = [p[1] for p in seg.path]
        ci = seg.cell_index if seg.cell_index is not None else -1

        if seg.segment_type == 'approach':
            color, width, dash, name = 'cyan', 2.5, 'solid', 'Approach'
        elif seg.segment_type == 'inter_cell':
            color, width, dash, name = 'magenta', 2.5, 'dash', 'Inter-cell'
        elif seg.segment_type == 'cell_cover':
            color = cmap[(ci + 1) % len(cmap)]
            width, dash, name = 2.5, 'solid', f'Cell {ci+1} cover'
        else:
            color, width, dash, name = 'gray', 1.5, 'solid', seg.segment_type

        fig.add_trace(go.Scatter(x=sx, y=sy, mode='lines',
                                  line=dict(color=color, width=width, dash=dash),
                                  name=name, showlegend=True,
                                  legendgroup=name), row=1, col=2)

    # 平台
    fig.add_trace(go.Scatter(x=[plat_x], y=[plat_y], mode='markers',
                              marker=dict(size=14, symbol='triangle-up',
                                         color='blue',
                                         line=dict(color='darkblue', width=2)),
                              name='Platform', showlegend=False), row=1, col=2)

    # ── 进度标记（滑块控制） ──
    progress_trace = go.Scatter(
        x=[all_x[0]], y=[all_y[0]], mode='markers',
        marker=dict(size=14, symbol='circle', color='red',
                   line=dict(color='darkred', width=2)),
        name='Current Position', showlegend=True,
    )

    # ── 构建帧：只更新进度标记位置 ──
    frames = []
    slider_steps = []
    frame_step = max(1, total_pts // 200)  # ~200 frames max, smooth enough

    for idx in range(0, total_pts, frame_step):
        end_idx = min(idx + 1, total_pts - 1)
        px, py = all_x[end_idx], all_y[end_idx]

        frames.append(go.Frame(
            data=[go.Scatter(x=[px], y=[py], mode='markers',
                            marker=dict(size=14, symbol='circle', color='red',
                                       line=dict(color='darkred', width=2)))],
            name=f'f{idx}',
            traces=[len(fig.data) - 1],  # update last trace (progress marker)
        ))

        dist_done = sum(math.hypot(
            deduped[i][0] - deduped[i-1][0],
            deduped[i][1] - deduped[i-1][1]) for i in range(1, end_idx + 1))
        pct = (end_idx + 1) / total_pts * 100
        slider_steps.append(dict(
            args=[[f'f{idx}'], dict(
                frame=dict(duration=0, redraw=False),
                mode='immediate',
                fromcurrent=True,
            )],
            label=f'{pct:.0f}%',
            method='animate',
        ))

    fig.frames = frames

    # 滑块
    fig.update_layout(
        sliders=[dict(
            active=0,
            currentvalue=dict(prefix='Progress: ', visible=True,
                            font=dict(size=14)),
            pad=dict(t=40),
            steps=slider_steps,
            len=0.85,
            x=0.075,
            transition=dict(duration=0),
        )],
        title=dict(
            text=(f"<b>Region Coverage Path — Interactive</b><br>"
                  f"<sub>Drag slider to move along path  |  "
                  f"Total: {result.total_length_km:.1f} km  |  "
                  f"Waypoints: {total_pts}</sub>"),
            x=0.5,
        ),
        legend=dict(x=1.02, y=1, font=dict(size=9)),
        height=650,
    )

    # 统一坐标轴
    all_bounds_x = [plat_x] + [v[0] for v in target.vertices]
    all_bounds_y = [plat_y] + [v[1] for v in target.vertices]
    x_range = [min(all_bounds_x) - 1, max(all_bounds_x) + 1]
    y_range = [min(all_bounds_y) - 1, max(all_bounds_y) + 1]

    for col in [1, 2]:
        fig.update_xaxes(range=x_range, constrain='domain', row=1, col=col)
        fig.update_yaxes(range=y_range, scaleanchor='x', scaleratio=1, row=1, col=col)

    fig.write_html(save_path)
    print(f"  Interactive HTML saved: {save_path}")


def _draw_polygon(ax, coords, **kwargs):
    from matplotlib.patches import Polygon as MPLPolygon
    patch = MPLPolygon(coords, **kwargs)
    ax.add_patch(patch)


def _draw_nfz_circles(ax, nfz_list: List[Tuple[Tuple[float, float], float]], **kwargs):
    """Draw NFZ as circles (original shape) instead of hexagons."""
    from matplotlib.patches import Circle
    default = dict(edgecolor='#c0392b', facecolor='#e74c3c', alpha=0.3, linewidth=0, zorder=3)
    default.update(kwargs)
    for center, radius in nfz_list:
        ax.add_patch(Circle(center, radius, **default))


def _short_id(name: str) -> str:
    """Strip non-ASCII chars from display name."""
    import re
    return re.sub(r'[^ -~]+', '', name).rstrip('-').strip()


def _set_bounds(ax, region_coords):
    xs = [p[0] for p in region_coords]
    ys = [p[1] for p in region_coords]
    margin_x = max((max(xs) - min(xs)) * 0.12, 1.0)
    margin_y = max((max(ys) - min(ys)) * 0.12, 1.0)
    ax.set_xlim(min(xs) - margin_x, max(xs) + margin_x)
    ax.set_ylim(min(ys) - margin_y, max(ys) + margin_y)


# ══════════════════════════════════════════════
# LLH 输入 / 输出 — 与现有路径规划格式兼容
# ══════════════════════════════════════════════

@dataclass
class CoverageInputPlatform:
    """LLH 平台输入。"""
    id: str
    position_llh: Tuple[float, float, float]  # (lon_deg, lat_deg, alt_m)
    detection_radius_km: float = 5.0
    speed_ms: float = 250.0
    range_km: float = 1500.0


@dataclass
class CoverageInputTarget:
    """LLH 目标区域输入 — 多边形边界顶点列表。"""
    id: str
    boundary: List[Tuple[float, float]]  # [(lon, lat), ...]


@dataclass
class CoverageInputNFZ:
    """LLH 禁飞区输入 — 圆柱体，height 在俯视图中忽略。"""
    id: str
    center_llh: Tuple[float, float, float]  # (lon, lat, alt_m) — alt 忽略
    radius_km: float
    height_m: float = 0.0


@dataclass
class CoverageInputPair:
    """LLH 平台-目标配对。"""
    platform_id: str
    target_id: str


@dataclass
class CoverageOutputLLH:
    """覆盖路径规划 LLH 输出。"""
    platform_id: str
    target_id: str
    path_llh: List[Tuple[float, float, float]]  # [(lon, lat, alt_m), ...]
    total_length_km: float
    cells: List[Polygon]
    cell_order: List[int]
    obstacles: List[Polygon]
    segments: List[TraversalSegment]


def plan_coverage_from_llh(
    platforms: List[CoverageInputPlatform],
    targets: List[CoverageInputTarget],
    no_fly_zones: List[CoverageInputNFZ],
    pairs: List[CoverageInputPair],
    ref_lon: Optional[float] = None,
    ref_lat: Optional[float] = None,
    visualize: bool = False,
    output_dir: Optional[str] = None,
) -> List[CoverageOutputLLH]:
    """一站式覆盖路径规划：LLH 输入 → 坐标转换 → 内部规划 → LLH 输出。

    Args:
        platforms: 平台列表 (LLH)
        targets: 目标区域列表 (LLH 边界)
        no_fly_zones: 禁飞区列表 (LLH 圆柱)
        pairs: 配对列表
        ref_lon, ref_lat: 参考原点，不指定则自动从所有点计算
        visualize: 是否生成可视化图
        output_dir: 可视化输出目录

    Returns:
        每对配对一个 CoverageOutputLLH（含 LLH 路径）
    """
    from ..core.geo import llh_to_local, local_to_llh

    # 1. 计算参考原点
    if ref_lon is None or ref_lat is None:
        all_lons, all_lats = [], []
        for p in platforms:
            all_lons.append(p.position_llh[0])
            all_lats.append(p.position_llh[1])
        for t in targets:
            for lon, lat in t.boundary:
                all_lons.append(lon)
                all_lats.append(lat)
        for n in no_fly_zones:
            all_lons.append(n.center_llh[0])
            all_lats.append(n.center_llh[1])
        ref_lon = sum(all_lons) / len(all_lons) if all_lons else 0.0
        ref_lat = sum(all_lats) / len(all_lats) if all_lats else 0.0

    # 2. 坐标转换 LLH → local (km)
    internal_platforms = []
    for p in platforms:
        e, n, _u = llh_to_local(p.position_llh[0], p.position_llh[1],
                                 p.position_llh[2], ref_lon, ref_lat)
        internal_platforms.append(PlatformSpec(
            id=p.id, position_xy=(e, n),
            detection_radius_km=p.detection_radius_km))

    internal_targets = []
    for t in targets:
        verts = []
        for lon, lat in t.boundary:
            e, n, _u = llh_to_local(lon, lat, 0.0, ref_lon, ref_lat)
            verts.append((e, n))
        internal_targets.append(TargetArea(id=t.id, vertices=verts))

    internal_nfz = []
    for nfz in no_fly_zones:
        e, n, _u = llh_to_local(nfz.center_llh[0], nfz.center_llh[1],
                                 nfz.center_llh[2], ref_lon, ref_lat)
        internal_nfz.append(NoFlyZone(
            id=nfz.id, center_xy=(e, n),
            radius_km=nfz.radius_km, height_m=nfz.height_m))

    internal_pairs = [PairSpec(platform_id=p.platform_id,
                                target_id=p.target_id) for p in pairs]

    # 3. 执行内部规划
    results = plan_coverage_scenario(
        internal_platforms, internal_targets, internal_nfz, internal_pairs)

    # 4. 转回 LLH
    platform_dict = {p.id: p for p in platforms}
    outputs = []
    for result in results:
        plat = platform_dict[result.platform_id]
        cruise_alt_m = plat.position_llh[2]

        path_llh = []
        for x, y in result.full_path:
            lon, lat, alt = local_to_llh(x, y, cruise_alt_m / 1000.0,
                                          ref_lon, ref_lat)
            path_llh.append((lon, lat, alt))

        outputs.append(CoverageOutputLLH(
            platform_id=result.platform_id,
            target_id=result.target_id,
            path_llh=path_llh,
            total_length_km=result.total_length_km,
            cells=result.cells,
            cell_order=result.cell_order,
            obstacles=result.obstacles,
            segments=result.segments,
        ))

    # 5. 可视化（可选）
    if visualize and output_dir:
        os.makedirs(output_dir, exist_ok=True)
        plat_dict_int = {p.id: p for p in internal_platforms}
        tgt_dict_int = {t.id: t for t in internal_targets}
        obs_xy_for_viz = [(z.center_xy, z.radius_km) for z in internal_nfz]

        # 各 pair 四张图
        prefix_map = {
            'cell_decomp': visualize_cell_decomposition,
            'cell_zigzag': visualize_cell_zigzag_lines,
            'traversal_flow': visualize_traversal_flow,
            'full_path': visualize_full_path,
        }
        for result in results:
            plat_int = plat_dict_int[result.platform_id]
            tgt_int = tgt_dict_int[result.target_id]
            pair_tag = f"{result.platform_id}_{result.target_id}"
            for prefix, viz_fn in prefix_map.items():
                viz_fn(result, plat_int, tgt_int, obs_xy_for_viz,
                       save_path=os.path.join(output_dir,
                                              f"{prefix}_{pair_tag}.png"),
                       show_plot=False)

        # 总览图：所有平台 + 所有区域在一张图中
        visualize_overview(
            results, internal_platforms, internal_targets, obs_xy_for_viz,
            save_path=os.path.join(output_dir, "overview.png"),
            show_plot=False)

    return outputs


# ══════════════════════════════════════════════
# 场景文件加载 & 结果写出
# ══════════════════════════════════════════════

def load_coverage_scenario(
    filepath: str,
) -> Tuple[List[CoverageInputPlatform], List[CoverageInputTarget],
           List[CoverageInputNFZ], List[CoverageInputPair]]:
    """从 YAML/JSON 文件加载覆盖路径规划场景。

    文件格式与 route_plan 现有场景文件一致：

        scenario:
          name: "coverage_mission"
          platforms:
            - id: "UAV-1"
              type: "ReconUAV"
              position: [lon, lat, alt_m]
              detection_radius_km: 1.5
              speed: 250
              range: 1500
          targets:
            - id: "Area-A"
              boundary: [[lon, lat], ...]
          no_fly_zones:
            - id: "NFZ-1"
              type: "cylinder"
              position: [lon, lat, alt_m]
              params:
                radius: 1.5
                height: 5000
          pairs:
            - platform: "UAV-1"
              target: "Area-A"

    Returns:
        (platforms, targets, no_fly_zones, pairs) — 可直接传入 plan_coverage_from_llh()
    """
    import json
    from pathlib import Path

    suffix = Path(filepath).suffix.lower()
    with open(filepath, "r", encoding="utf-8") as f:
        if suffix == ".json":
            data = json.load(f)
        else:
            import yaml
            data = yaml.safe_load(f)

    sc = data.get("scenario", data)

    platforms = []
    for p in sc.get("platforms", []):
        pos = p["position"]
        platforms.append(CoverageInputPlatform(
            id=p["id"],
            position_llh=(pos[0], pos[1], pos[2]),
            detection_radius_km=p.get("detection_radius_km", 5.0),
            speed_ms=p.get("speed", 250.0),
            range_km=p.get("range", 1500.0),
        ))

    targets = []
    for t in sc.get("targets", []):
        targets.append(CoverageInputTarget(
            id=t["id"],
            boundary=[(lon, lat) for lon, lat in t["boundary"]],
        ))

    no_fly_zones = []
    for nfz in sc.get("no_fly_zones", []):
        pos = nfz["position"]
        params = nfz.get("params", {})
        no_fly_zones.append(CoverageInputNFZ(
            id=nfz["id"],
            center_llh=(pos[0], pos[1], pos[2]),
            radius_km=params.get("radius", 10.0),
            height_m=params.get("height", 0.0),
        ))

    pairs = []
    for pr in sc.get("pairs", []):
        pairs.append(CoverageInputPair(
            platform_id=pr["platform"],
            target_id=pr["target"],
        ))

    return platforms, targets, no_fly_zones, pairs


def write_coverage_results(
    outputs: List[CoverageOutputLLH],
    filepath: str,
) -> None:
    """将覆盖路径规划结果写出为 YAML/JSON 文件。

    输出格式与 route_plan write_results() 一致。
    """
    import json
    from pathlib import Path

    result_list = []
    for out in outputs:
        result_list.append({
            "platform": out.platform_id,
            "target": out.target_id,
            "total_length_km": round(out.total_length_km, 2),
            "cells": len(out.cells),
            "cell_order": [c + 1 for c in out.cell_order],
            "waypoints": [[round(v, 4) for v in wp] for wp in out.path_llh],
            "segments": [
                {
                    "type": seg.segment_type,
                    "cell_index": seg.cell_index,
                    "length_km": round(seg.length_km, 2),
                }
                for seg in out.segments
            ],
        })

    output = {"results": result_list}

    suffix = Path(filepath).suffix.lower()
    with open(filepath, "w", encoding="utf-8") as f:
        if suffix == ".json":
            json.dump(output, f, ensure_ascii=False, indent=2)
            f.write("\n")
        else:
            import yaml
            yaml.dump(output, f, allow_unicode=True, default_flow_style=False,
                      sort_keys=False)
