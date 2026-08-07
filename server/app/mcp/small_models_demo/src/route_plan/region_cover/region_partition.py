#!/usr/bin/env python3
"""
Region Partitioning via Vertical (Trapezoidal) Decomposition.

给定一个多边形区域和内部的多边形障碍物，算法：
1. 合并有重叠的障碍物（取并集）
2. 用垂直扫描线从左到右移动
3. 当扫描线碰到/离开障碍物时（即障碍物顶点处），从该顶点向上向下发射射线
4. 射线碰到区域边界或其他障碍物边界即停止
5. 射线只影响它穿过的区域片段 —— 被障碍物挡住的另一侧不会被切分

使用 shapely 做几何计算，matplotlib 做可视化。
"""

import numpy as np
from shapely.geometry import (Point, Polygon, LineString, MultiLineString,
                               MultiPoint, GeometryCollection)
from shapely.ops import unary_union, split, polygonize, linemerge
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MPLPolygon
from typing import List, Tuple, Optional, Dict, Set
from collections import defaultdict


# ══════════════════════════════════════════════
# 核心算法
# ══════════════════════════════════════════════

def merge_obstacles(obstacle_list: List[List[Tuple[float, float]]],
                    region: Polygon = None) -> List[Polygon]:
    """合并有重叠的障碍物。如果提供 region，先裁剪到区域内。"""
    if not obstacle_list:
        return []

    polygons = []
    for coords in obstacle_list:
        if len(coords) < 3:
            continue
        poly = Polygon(coords)
        if not poly.is_valid:
            poly = poly.buffer(0)
        # 裁剪到区域内：只保留区域内部的部分
        if region is not None and not poly.is_empty:
            poly = poly.intersection(region)
            if poly.is_empty:
                continue
            if not poly.is_valid:
                poly = poly.buffer(0)
        polygons.append(poly)

    if not polygons:
        return []

    merged = unary_union(polygons)
    if isinstance(merged, Polygon):
        return [merged] if not merged.is_empty else []
    elif hasattr(merged, 'geoms'):
        return [g for g in merged.geoms if not g.is_empty]
    return []


def _get_vertices_by_x(polygons: List[Polygon],
                      region: Polygon = None) -> Dict[float, Set[float]]:
    """将障碍物所有顶点 + 区域凹顶点按 x 坐标分组。"""
    result: Dict[float, Set[float]] = defaultdict(set)

    # 障碍物：所有顶点都需要
    for poly in polygons:
        for x, y in poly.exterior.coords[:-1]:
            x_r = round(x, 10)
            result[x_r].add(round(y, 10))
        for interior in poly.interiors:
            for x, y in interior.coords[:-1]:
                x_r = round(x, 10)
                result[x_r].add(round(y, 10))

    # 区域：只取凹顶点（reflex vertices）
    # CCW 多边形中，cross product < 0 表示右转 → 凹
    if region is not None:
        coords = list(region.exterior.coords[:-1])
        n = len(coords)
        for i in range(n):
            xp, yp = coords[(i - 1) % n]
            xi, yi = coords[i]
            xn, yn = coords[(i + 1) % n]
            # Cross product of (incoming) × (outgoing)
            cross = (xi - xp) * (yn - yi) - (yi - yp) * (xn - xi)
            if cross < -1e-9:  # 右转 → 凹顶点
                x_r = round(xi, 10)
                result[x_r].add(round(yi, 10))

    return dict(result)


def _get_free_intervals_at_x(x: float, free_space, y_min: float, y_max: float,
                             margin: float = 1.0) -> List[LineString]:
    """获取垂直线 x 在自由空间内的所有区间段。"""
    vline = LineString([(x, y_min - margin), (x, y_max + margin)])
    inter = vline.intersection(free_space)

    if inter.is_empty:
        return []

    if isinstance(inter, LineString):
        return [inter]
    elif hasattr(inter, 'geoms'):
        return [g for g in inter.geoms if isinstance(g, LineString) and g.length > 1e-9]
    return []


def _extract_polygons(geom) -> List[Polygon]:
    """从任意几何对象中提取 Polygon 列表。"""
    if isinstance(geom, Polygon):
        return [geom] if not geom.is_empty else []
    if hasattr(geom, 'geoms'):
        result = []
        for g in geom.geoms:
            result.extend(_extract_polygons(g))
        return result
    return []


def vertical_decompose(region_coords: List[Tuple[float, float]],
                       obstacle_coords_list: List[List[Tuple[float, float]]]
                       ) -> Tuple[List[Polygon], List[Polygon], Polygon]:
    """
    垂直分解：将含障碍物的区域划分为若干子区域。

    核心逻辑：
    1. 合并重叠障碍物
    2. 计算自由空间
    3. 对每个障碍物顶点所在的 x 坐标，找到该 x 处的自由空间垂直线段
    4. 只保留与障碍物顶点相邻的线段（被顶点"触发"的分割线）
    5. 用这些线段去切自由空间 —— 线段到哪就切到哪，不会穿透障碍物

    参数
    ----
    region_coords : 外部区域多边形顶点 [(x,y), ...]
    obstacle_coords_list : 障碍物坐标列表

    返回
    ----
    (sub_regions, merged_obstacles, region)
    """
    # 1. 构建区域多边形
    region = Polygon(region_coords)
    if not region.is_valid:
        region = region.buffer(0)

    # 2. 合并障碍物（自动裁剪到区域内）
    merged = merge_obstacles(obstacle_coords_list, region=region)

    # 3. 计算自由空间
    if merged:
        free_space = region.difference(unary_union(merged))
    else:
        free_space = region
    if not free_space.is_valid:
        free_space = free_space.buffer(0)

    # 4. 收集所有顶点按 x 分组（障碍物 + 区域边界）
    #    区域顶点也必须触发分割，否则子区域上下边界可能有拐点 → 非凸
    vertices_by_x = _get_vertices_by_x(merged, region=region)

    if not vertices_by_x:
        # 没有障碍物 → 整个区域就是一个子区域
        return _extract_polygons(free_space), merged, region

    # 5. 对每个有顶点的 x，找出被"触发"的自由空间区间
    y_min, y_max = region.bounds[1], region.bounds[3]
    margin = max((y_max - y_min) * 0.1, 1.0)

    split_segments: List[LineString] = []

    for x, vys in sorted(vertices_by_x.items()):
        intervals = _get_free_intervals_at_x(x, free_space, y_min, y_max, margin)
        for seg in intervals:
            seg_ys = [round(pt[1], 10) for pt in seg.coords]
            seg_lo, seg_hi = min(seg_ys), max(seg_ys)
            # 检查这段自由空间是否与某个顶点相邻（顶点在其端点处）
            for vy in vys:
                if abs(seg_lo - vy) < 1e-6 or abs(seg_hi - vy) < 1e-6:
                    split_segments.append(seg)
                    break

    # 6. 合并同一 x 上相邻或重叠的线段（避免重复切分）
    split_segments = _merge_collinear_segments(split_segments)

    # 7. 用这些线段依次切分自由空间
    pieces = _extract_polygons(free_space)

    for seg in split_segments:
        new_pieces = []
        for piece in pieces:
            # 只有线段与 piece 内部有交集时才切
            if not piece.intersects(seg):
                new_pieces.append(piece)
                continue
            # 如果线段仅在边界上就不要切
            if piece.touches(seg) and not piece.crosses(seg):
                new_pieces.append(piece)
                continue

            try:
                # 延长线段两端一小段确保能切开
                coords = list(seg.coords)
                dy = (coords[-1][1] - coords[0][1]) * 0.001
                ext_seg = LineString([
                    (coords[0][0], coords[0][1] - dy),
                    (coords[-1][0], coords[-1][1] + dy),
                ])
                result = split(piece, ext_seg)
                for g in result.geoms:
                    if hasattr(g, 'area') and g.area > 1e-9:
                        new_pieces.append(g)
            except Exception:
                new_pieces.append(piece)
        pieces = new_pieces

    # 8. 过滤：只保留在自由空间内的多边形
    obstacle_union = unary_union(merged) if merged else None
    result_polys = []
    for piece in pieces:
        if not piece.is_valid:
            piece = piece.buffer(0)
        if piece.area < 1e-8:
            continue
        if obstacle_union is not None:
            if obstacle_union.contains(piece.centroid):
                continue
            piece = piece.intersection(free_space)
        if hasattr(piece, 'area') and piece.area > 1e-8:
            if isinstance(piece, Polygon):
                result_polys.append(piece)
            elif hasattr(piece, 'geoms'):
                for g in piece.geoms:
                    if isinstance(g, Polygon) and g.area > 1e-8:
                        result_polys.append(g)

    return result_polys, merged, region


def _merge_collinear_segments(segments: List[LineString]) -> List[LineString]:
    """合并同一 x 上相邻或重叠的垂直线段。"""
    by_x: Dict[float, List[Tuple[float, float]]] = defaultdict(list)
    for seg in segments:
        coords = list(seg.coords)
        x = round(coords[0][0], 10)
        ys = sorted([coords[0][1], coords[-1][1]])
        by_x[x].append((ys[0], ys[1]))

    result = []
    for x, intervals in by_x.items():
        intervals.sort()
        merged_intervals = []
        for lo, hi in intervals:
            if merged_intervals and lo <= merged_intervals[-1][1] + 1e-6:
                merged_intervals[-1] = (merged_intervals[-1][0],
                                        max(merged_intervals[-1][1], hi))
            else:
                merged_intervals.append((lo, hi))
        for lo, hi in merged_intervals:
            if hi - lo > 1e-9:
                result.append(LineString([(x, lo), (x, hi)]))
    return result


# ══════════════════════════════════════════════
# 便捷函数
# ══════════════════════════════════════════════

def build_adjacency_graph(sub_regions: List[Polygon]) -> Dict[int, List[int]]:
    """
    构建子区域邻接图。

    两个子区域相邻 = 它们共享一条边（不只是点）。

    返回 {region_index: [neighbor_index, ...]}
    """
    n = len(sub_regions)
    adj: Dict[int, List[int]] = {i: [] for i in range(n)}

    for i in range(n):
        for j in range(i + 1, n):
            inter = sub_regions[i].intersection(sub_regions[j])
            if not inter.is_empty:
                # 共享边界长度 > 0（不是仅共享点）
                if hasattr(inter, 'length') and inter.length > 1e-9:
                    adj[i].append(j)
                    adj[j].append(i)
                elif hasattr(inter, 'area') and inter.area > 1e-9:
                    adj[i].append(j)
                    adj[j].append(i)

    return adj


def print_partition_result(sub_regions: List[Polygon],
                           merged_obstacles: List[Polygon] = None):
    """打印划分结果：顶点坐标 + 邻接关系。"""
    adj = build_adjacency_graph(sub_regions)

    print(f"\n{'='*60}")
    print(f"Sub-regions: {len(sub_regions)}")
    if merged_obstacles:
        region_area = sum(p.area for p in sub_regions) + sum(o.area for o in merged_obstacles)
        free_area = sum(p.area for p in sub_regions)
        obs_area = sum(o.area for o in merged_obstacles)
        print(f"Total area: {region_area:.4f}  "
              f"(free: {free_area:.4f}  obstacles: {obs_area:.4f})")
    print(f"{'='*60}")

    # 顶点坐标
    print(f"\n--- Vertex Coordinates ---")
    for i, poly in enumerate(sub_regions):
        coords = list(poly.exterior.coords)
        if len(coords) > 1 and coords[0] == coords[-1]:
            coords = coords[:-1]
        coord_str = ", ".join(f"({x:.4f}, {y:.4f})" for x, y in coords)
        print(f"  R{i+1}: [{coord_str}]")

    # 邻接关系
    print(f"\n--- Adjacency Graph ---")
    for i in range(len(sub_regions)):
        neighbors = adj[i]
        if neighbors:
            n_str = ", ".join(f"R{n+1}" for n in sorted(neighbors))
        else:
            n_str = "(none)"
        print(f"  R{i+1} -> {n_str}")

    # 邻接矩阵（ASCII）
    print(f"\n--- Adjacency Matrix ---")
    n = len(sub_regions)
    # 列标题
    header = "     " + "".join(f"R{i+1:<4}" for i in range(n))
    print(header)
    for i in range(n):
        row = f"R{i+1:<4} "
        for j in range(n):
            if i == j:
                row += " \\  "
            elif j in adj[i]:
                row += " 1  "
            else:
                row += " .  "
        print(row)

    return adj


def partition_to_coords(region_coords: List[Tuple[float, float]],
                        obstacle_coords_list: List[List[Tuple[float, float]]]
                        ) -> List[List[Tuple[float, float]]]:
    """输入坐标，输出划分后的子区域坐标列表。"""
    sub_regions, _, _ = vertical_decompose(region_coords, obstacle_coords_list)
    result = []
    for poly in sub_regions:
        coords = list(poly.exterior.coords)
        if len(coords) > 1 and coords[0] == coords[-1]:
            coords = coords[:-1]
        result.append(coords)
    return result


def custom_partition(region_coords: List[Tuple[float, float]],
                     obstacle_coords_list: List[List[Tuple[float, float]]],
                     show_plot: bool = True,
                     save_plot: str = None):
    """用户自定义区域划分，带可视化和统计输出。"""
    sub_regions, merged, region = vertical_decompose(region_coords, obstacle_coords_list)

    total_free = sum(p.area for p in sub_regions)
    region_area = Polygon(region_coords).area
    obs_area = sum(o.area for o in merged)
    print(f"Region area: {region_area:.2f}")
    print(f"Merged obstacles: {len(merged)} (total area: {obs_area:.2f})")
    print(f"Free space: {region_area - obs_area:.2f}")
    print(f"Sub-regions: {len(sub_regions)} (total area: {total_free:.2f})")
    print(f"Area check: {'OK' if abs(total_free - (region_area - obs_area)) < 1e-6 else 'MISMATCH!'}")

    sub_coords = []
    for poly in sub_regions:
        coords = list(poly.exterior.coords)
        if len(coords) > 1 and coords[0] == coords[-1]:
            coords = coords[:-1]
        sub_coords.append(coords)

    merged_coords = []
    for obs in merged:
        coords = list(obs.exterior.coords)
        if len(coords) > 1 and coords[0] == coords[-1]:
            coords = coords[:-1]
        merged_coords.append(coords)

    if show_plot:
        visualize(region_coords, obstacle_coords_list, sub_regions, merged,
                  title="Region Partitioning", save_path=save_plot)

    return sub_coords, merged_coords


# ══════════════════════════════════════════════
# 可视化
# ══════════════════════════════════════════════

def visualize(region_coords: List[Tuple[float, float]],
              obstacle_coords_list: List[List[Tuple[float, float]]],
              sub_regions: List[Polygon] = None,
              merged_obstacles: List[Polygon] = None,
              title: str = "Region Partitioning",
              save_path: str = None):
    """三栏可视化：原始输入 / 合并障碍物+分割线 / 划分结果"""
    if sub_regions is None:
        sub_regions, merged_obstacles, _ = vertical_decompose(
            region_coords, obstacle_coords_list)

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    # ── 左图：原始输入 ──
    ax = axes[0]
    ax.set_title("Input: Region & Obstacles")
    ax.set_aspect('equal')
    _draw_polygon(ax, region_coords, edgecolor='black', facecolor='whitesmoke',
                  linewidth=2, label='Region')
    colors = plt.cm.Set2.colors
    for i, obs in enumerate(obstacle_coords_list):
        _draw_polygon(ax, obs, edgecolor='darkred',
                      facecolor=colors[i % len(colors)], alpha=0.6,
                      linewidth=1.5, label=f'Obs {i+1}')
    ax.legend(fontsize=7, loc='upper right')
    _set_bounds(ax, region_coords)

    # ── 中图：合并障碍物 + 分割线 ──
    ax = axes[1]
    ax.set_title("Merged Obstacles & Split Lines")
    ax.set_aspect('equal')
    _draw_polygon(ax, region_coords, edgecolor='black', facecolor='whitesmoke',
                  linewidth=2)
    if merged_obstacles:
        for obs in merged_obstacles:
            coords = list(obs.exterior.coords)
            _draw_polygon(ax, coords, edgecolor='darkred',
                          facecolor='lightcoral', alpha=0.5, linewidth=1.5)
    if sub_regions:
        _draw_split_lines(ax, sub_regions)
    _set_bounds(ax, region_coords)

    # ── 右图：划分结果 ──
    ax = axes[2]
    ax.set_title(f"Result: {len(sub_regions)} Sub-regions")
    ax.set_aspect('equal')
    _draw_polygon(ax, region_coords, edgecolor='black', facecolor='none',
                  linewidth=2)
    if merged_obstacles:
        for obs in merged_obstacles:
            coords = list(obs.exterior.coords)
            _draw_polygon(ax, coords, edgecolor='darkred',
                          facecolor='lightcoral', alpha=0.5, linewidth=1.5)
    cmap = plt.cm.tab20
    for i, poly in enumerate(sub_regions):
        coords = list(poly.exterior.coords)
        color = cmap(i % 20)
        _draw_polygon(ax, coords, edgecolor='black',
                      facecolor=color, alpha=0.35, linewidth=1)
        cx, cy = poly.centroid.x, poly.centroid.y
        ax.text(cx, cy, str(i + 1), fontsize=8, ha='center', va='center',
                fontweight='bold')
    _set_bounds(ax, region_coords)

    plt.suptitle(title, fontsize=14, fontweight='bold')
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"  -> {save_path}")
    plt.close()  # 不弹窗，直接保存


def _draw_polygon(ax, coords, **kwargs):
    patch = MPLPolygon(coords, **kwargs)
    ax.add_patch(patch)


def _draw_split_lines(ax, sub_regions: List[Polygon]):
    """高亮显示子区域之间的垂直分割线"""
    from collections import Counter
    edge_counts = Counter()
    for poly in sub_regions:
        coords = list(poly.exterior.coords)
        for i in range(len(coords) - 1):
            a, b = coords[i], coords[i + 1]
            edge = (a, b) if a < b else (b, a)
            edge_counts[edge] += 1

    for edge, count in edge_counts.items():
        if count > 1:
            (x1, y1), (x2, y2) = edge
            if abs(x1 - x2) < 1e-6:
                ax.plot([x1, x2], [y1, y2], 'b--', linewidth=1.2, alpha=0.7)


def _set_bounds(ax, region_coords):
    xs = [p[0] for p in region_coords]
    ys = [p[1] for p in region_coords]
    margin_x = (max(xs) - min(xs)) * 0.08
    margin_y = (max(ys) - min(ys)) * 0.08
    ax.set_xlim(min(xs) - margin_x, max(xs) + margin_x)
    ax.set_ylim(min(ys) - margin_y, max(ys) + margin_y)


# ══════════════════════════════════════════════
# 测试与演示
# ══════════════════════════════════════════════

def demo_basic():
    """单个矩形障碍物"""
    print("=" * 60)
    print("Demo 1: Single rectangular obstacle")
    print("=" * 60)
    region = [(0, 0), (10, 0), (10, 10), (0, 10)]
    obstacles = [[(3, 2), (7, 2), (7, 5), (3, 5)]]
    sub_regions, merged, _ = vertical_decompose(region, obstacles)
    print(f"Sub-regions: {len(sub_regions)} (total area: {sum(p.area for p in sub_regions):.2f})")
    for i, poly in enumerate(sub_regions):
        c = list(poly.exterior.coords)
        print(f"  R{i+1}: {len(c)-1}v, area={poly.area:.2f}")
    visualize(region, obstacles, sub_regions, merged, title="Demo 1: Single Obstacle")


def demo_overlapping():
    """重叠障碍物 → 合并为 L 形"""
    print("\n" + "=" * 60)
    print("Demo 2: Two overlapping obstacles")
    print("=" * 60)
    region = [(0, 0), (12, 0), (12, 10), (0, 10)]
    obstacles = [
        [(2, 2), (7, 2), (7, 6), (2, 6)],
        [(5, 4), (10, 4), (10, 8), (5, 8)],
    ]
    sub_regions, merged, _ = vertical_decompose(region, obstacles)
    print(f"Original obstacles: {len(obstacles)} → merged: {len(merged)}")
    for i, obs in enumerate(merged):
        print(f"  Merged {i+1}: {len(list(obs.exterior.coords))-1} vertices, area={obs.area:.2f}")
    print(f"Sub-regions: {len(sub_regions)} (total area: {sum(p.area for p in sub_regions):.2f})")
    for i, poly in enumerate(sub_regions):
        c = list(poly.exterior.coords)
        print(f"  R{i+1}: {len(c)-1}v, area={poly.area:.2f}")
    visualize(region, obstacles, sub_regions, merged,
              title="Demo 2: Overlapping → Merged L-shape")


def demo_stacked():
    """关键测试：上下两个障碍物，中间有间隔 —— 分割线不应穿透"""
    print("\n" + "=" * 60)
    print("Demo 3: Vertically stacked obstacles (split isolation test)")
    print("=" * 60)

    # 区域 15x12
    # 障碍物 A: 横向长条 y∈[4,5], x∈[1,13]  —— 将空间上下分开
    # 障碍物 B: 上方小块 y∈[7,10], x∈[3,6] —— 只在上半部分
    # 障碍物 C: 下方小块 y∈[1,3],  x∈[8,11] —— 只在下半部分
    region = [(0, 0), (15, 0), (15, 12), (0, 12)]
    obstacles = [
        [(1, 4), (13, 4), (13, 5), (1, 5)],   # A: 横贯长条
        [(3, 7), (6, 7), (6, 10), (3, 10)],    # B: 上方小块
        [(8, 1), (11, 1), (11, 3), (8, 3)],    # C: 下方小块
    ]

    sub_regions, merged, _ = vertical_decompose(region, obstacles)
    print(f"Obstacles: {len(obstacles)} → merged: {len(merged)}")
    print(f"Sub-regions: {len(sub_regions)} (total area: {sum(p.area for p in sub_regions):.2f})")
    for i, poly in enumerate(sub_regions):
        c = list(poly.exterior.coords)
        centroid = poly.centroid
        print(f"  R{i+1}: {len(c)-1}v, area={poly.area:.2f}, "
              f"centroid=({centroid.x:.1f}, {centroid.y:.1f})")

    # 验证：障碍物 B 的顶点 x=3,6 处的分割不应影响下半部分 (y<4)
    # 下半部分 y∈[0,4] 应该只在 x=1,8,11,13 处被切分（来自 A 和 C 的顶点）
    # 而不应在 x=3,6 处被切分（那是 B 的顶点）
    visualize(region, obstacles, sub_regions, merged,
              title="Demo 3: Stacked Obstacles — Split Isolation")


def demo_complex():
    """复杂场景"""
    print("\n" + "=" * 60)
    print("Demo 4: Complex scenario")
    print("=" * 60)
    region = [(0, 0), (15, 0), (15, 12), (0, 12)]
    obstacles = [
        [(2, 1), (5, 1), (5, 4), (2, 4)],
        [(7, 2), (10, 2), (10, 5), (9, 5), (9, 7), (7, 7)],  # L 形
        [(11, 6), (14, 6), (12.5, 10)],  # 三角形
        [(3, 3), (6, 3), (6, 6), (3, 6)],  # 与第一个重叠
    ]
    sub_regions, merged, _ = vertical_decompose(region, obstacles)
    print(f"Obstacles: {len(obstacles)} → merged: {len(merged)}")
    print(f"Sub-regions: {len(sub_regions)} (total area: {sum(p.area for p in sub_regions):.2f})")
    visualize(region, obstacles, sub_regions, merged,
              title="Demo 4: Complex Multi-Obstacle")


def demo_irregular_region():
    """不规则区域"""
    print("\n" + "=" * 60)
    print("Demo 5: Irregular L-shaped region")
    print("=" * 60)
    region = [(0, 0), (12, 0), (12, 4), (6, 4), (6, 10), (0, 10)]
    obstacles = [
        [(2, 1.5), (4.5, 1.5), (4.5, 3), (2, 3)],
        [(2, 6), (4.5, 6), (4.5, 8.5), (2, 8.5)],
    ]
    sub_regions, merged, _ = vertical_decompose(region, obstacles)
    print(f"Sub-regions: {len(sub_regions)} (total area: {sum(p.area for p in sub_regions):.2f})")
    visualize(region, obstacles, sub_regions, merged,
              title="Demo 5: Irregular Region")


def demo_outside_obstacle():
    """障碍物部分在区域外 —— 应自动裁剪"""
    print("\n" + "=" * 60)
    print("Demo 6: Obstacles partially outside region (auto-clip)")
    print("=" * 60)

    region = [(0, 0), (10, 0), (10, 10), (0, 10)]

    # 障碍物 1：完全在区域内
    # 障碍物 2：一半在区域内，一半在外面（右边超出）
    # 障碍物 3：完全在外面
    obstacles = [
        [(2, 2), (4, 2), (4, 5), (2, 5)],                          # 完全在内
        [(7, 3), (13, 3), (13, 6), (7, 6)],                         # 右侧超出 x>10
        [(11, 1), (14, 1), (14, 4), (11, 4)],                       # 完全在外
    ]

    sub_regions, merged, _ = vertical_decompose(region, obstacles)

    print(f"Original obstacles: {len(obstacles)}")
    print(f"After clip & merge: {len(merged)}")
    for i, obs in enumerate(merged):
        coords = list(obs.exterior.coords)
        print(f"  Merged {i+1}: {len(coords)-1}v, area={obs.area:.2f}, "
              f"bounds=({obs.bounds[0]:.1f},{obs.bounds[1]:.1f})-({obs.bounds[2]:.1f},{obs.bounds[3]:.1f})")

    region_area = Polygon(region).area
    obs_area = sum(o.area for o in merged)
    free_area = sum(p.area for p in sub_regions)
    print(f"Region: {region_area:.0f}, obstacles: {obs_area:.2f}, "
          f"free: {free_area:.2f} (check: {region_area - obs_area:.2f})")

    visualize(region, obstacles, sub_regions, merged,
              title="Demo 6: Auto-clip Obstacles Outside Region")


def demo_polygon_region():
    """多边形区域（五边形）+ 障碍物"""
    print("\n" + "=" * 60)
    print("Demo 7: Pentagonal region with obstacles")
    print("=" * 60)

    # 五边形区域
    region = [
        (0, 0), (10, -2), (14, 4), (8, 12), (2, 8),
    ]

    obstacles = [
        [(4, 1), (7, 1), (7, 3.5), (4, 3.5)],              # 矩形障碍物
        [(9, 5), (12, 5.5), (10.5, 9)],                      # 三角形障碍物
        [(2.5, 5), (4, 4.5), (5, 6.5), (4, 7.5)],           # 四边形（部分可能在区域外）
    ]

    sub_regions, merged, _ = vertical_decompose(region, obstacles)

    region_area = Polygon(region).area
    obs_area = sum(o.area for o in merged)
    free_area = sum(p.area for p in sub_regions)
    print(f"Region area: {region_area:.2f}")
    print(f"Obstacles: {len(obstacles)} → merged: {len(merged)} (area: {obs_area:.2f})")
    print(f"Sub-regions: {len(sub_regions)} (total area: {free_area:.2f})")
    print(f"Area check: {'OK' if abs(free_area - (region_area - obs_area)) < 1e-4 else 'MISMATCH!'}")
    for i, poly in enumerate(sub_regions):
        c = list(poly.exterior.coords)
        centroid = poly.centroid
        print(f"  R{i+1}: {len(c)-1}v, area={poly.area:.2f}, "
              f"centroid=({centroid.x:.1f}, {centroid.y:.1f})")

    visualize(region, obstacles, sub_regions, merged,
              title="Demo 7: Pentagonal Region")


def demo_concave_region():
    """凹多边形区域 —— C 形走廊"""
    print("\n" + "=" * 60)
    print("Demo 8: Concave (C-shaped) region")
    print("=" * 60)

    # C 形凹多边形：从矩形中挖掉中间偏右的一块
    # 外轮廓 (0,0) → (14,0) → (14,12) → (0,12) → (0,0)
    # 凹进去: (4,3) → (12,3) → (12,9) → (4,9) → (4,3)  逆时针=洞
    # 用单条轮廓表示凹多边形（顶点按逆时针绕行，凹处走"切口"）
    region = [
        (0, 0), (14, 0), (14, 12), (0, 12),    # 外框
        (0, 9), (10, 9), (10, 3), (0, 3),       # 凹进去（顺时针回到起点形成凹槽）
    ]
    # 注意：上面这种写法在 shapely 中会自动处理为凹多边形（自交的规范化）

    # 更明确的 C 形凹多边形写法（逆时针绕外圈，凹处走两遍）
    region = [
        (0, 0), (14, 0), (14, 12), (0, 12),
        (0, 9), (4, 9), (4, 3), (0, 3),
    ]

    obstacles = [
        [(1.5, 4), (3, 4), (3, 8), (1.5, 8)],          # C 形的左臂内
        [(6, 0.5), (8, 0.5), (8, 2), (6, 2)],           # C 形的下槽内
        [(10, 6), (12.5, 6), (12.5, 7), (10, 7)],        # C 形的右臂内
    ]

    sub_regions, merged, _ = vertical_decompose(region, obstacles)

    region_area = Polygon(region).area
    obs_area = sum(o.area for o in merged)
    free_area = sum(p.area for p in sub_regions)
    print(f"Region area: {region_area:.2f}")
    print(f"Obstacles: {len(obstacles)} → merged: {len(merged)} (area: {obs_area:.2f})")
    print(f"Sub-regions: {len(sub_regions)} (total area: {free_area:.2f})")
    print(f"Area check: {'OK' if abs(free_area - (region_area - obs_area)) < 1e-4 else 'MISMATCH!'}")
    for i, poly in enumerate(sub_regions):
        c = list(poly.exterior.coords)
        centroid = poly.centroid
        print(f"  R{i+1}: {len(c)-1}v, area={poly.area:.2f}, "
              f"centroid=({centroid.x:.1f}, {centroid.y:.1f})")

    visualize(region, obstacles, sub_regions, merged,
              title="Demo 8: Concave C-shaped Region")


def demo_concave_star():
    """凹多边形 —— 十字形/星形区域"""
    print("\n" + "=" * 60)
    print("Demo 9: Concave star/cross-shaped region")
    print("=" * 60)

    # 十字形凹多边形
    region = [
        (3, 0), (9, 0), (9, 3), (12, 3), (12, 9),
        (9, 9), (9, 12), (3, 12), (3, 9), (0, 9),
        (0, 3), (3, 3),
    ]

    obstacles = [
        [(4, 4), (8, 4), (8, 8), (4, 8)],    # 中心方块
        [(10, 4), (11.5, 4), (11.5, 5.5), (10, 5.5)],  # 右臂
    ]

    sub_regions, merged, _ = vertical_decompose(region, obstacles)

    region_area = Polygon(region).area
    obs_area = sum(o.area for o in merged)
    free_area = sum(p.area for p in sub_regions)
    print(f"Region area: {region_area:.2f}")
    print(f"Obstacles: {len(obstacles)} → merged: {len(merged)} (area: {obs_area:.2f})")
    print(f"Sub-regions: {len(sub_regions)} (total area: {free_area:.2f})")
    print(f"Area check: {'OK' if abs(free_area - (region_area - obs_area)) < 1e-4 else 'MISMATCH!'}")
    for i, poly in enumerate(sub_regions):
        c = list(poly.exterior.coords)
        centroid = poly.centroid
        print(f"  R{i+1}: {len(c)-1}v, area={poly.area:.2f}, "
              f"centroid=({centroid.x:.1f}, {centroid.y:.1f})")

    visualize(region, obstacles, sub_regions, merged,
              title="Demo 9: Concave Cross-shaped Region")


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(out, exist_ok=True)

    def _save(region, obs, sub, merged, title, fname):
        visualize(region, obs, sub, merged, title=title,
                  save_path=os.path.join(out, fname))

    demos = []

    # --- Demo 1 ---
    r1 = [(0,0),(10,0),(10,10),(0,10)]
    o1 = [[(3,2),(7,2),(7,5),(3,5)]]
    sub1, m1, _ = vertical_decompose(r1, o1)
    demos.append(("Demo 1: Single Obstacle", r1, o1, sub1, m1, "demo1_single.png"))

    # --- Demo 2 ---
    r2 = [(0,0),(12,0),(12,10),(0,10)]
    o2 = [[(2,2),(7,2),(7,6),(2,6)], [(5,4),(10,4),(10,8),(5,8)]]
    sub2, m2, _ = vertical_decompose(r2, o2)
    demos.append(("Demo 2: Overlapping -> Merged", r2, o2, sub2, m2, "demo2_overlap.png"))

    # --- Demo 3 ---
    r3 = [(0,0),(15,0),(15,12),(0,12)]
    o3 = [[(1,4),(13,4),(13,5),(1,5)], [(3,7),(6,7),(6,10),(3,10)], [(8,1),(11,1),(11,3),(8,3)]]
    sub3, m3, _ = vertical_decompose(r3, o3)
    demos.append(("Demo 3: Split Isolation", r3, o3, sub3, m3, "demo3_isolation.png"))

    # --- Demo 4 ---
    r4 = [(0,0),(15,0),(15,12),(0,12)]
    o4 = [[(2,1),(5,1),(5,4),(2,4)], [(7,2),(10,2),(10,5),(9,5),(9,7),(7,7)],
          [(11,6),(14,6),(12.5,10)], [(3,3),(6,3),(6,6),(3,6)]]
    sub4, m4, _ = vertical_decompose(r4, o4)
    demos.append(("Demo 4: Complex", r4, o4, sub4, m4, "demo4_complex.png"))

    # --- Demo 5 ---
    r5 = [(0,0),(12,0),(12,4),(6,4),(6,10),(0,10)]
    o5 = [[(2,1.5),(4.5,1.5),(4.5,3),(2,3)], [(2,6),(4.5,6),(4.5,8.5),(2,8.5)]]
    sub5, m5, _ = vertical_decompose(r5, o5)
    demos.append(("Demo 5: L-shaped Region", r5, o5, sub5, m5, "demo5_lshape.png"))

    # --- Demo 6 ---
    r6 = [(0,0),(10,0),(10,10),(0,10)]
    o6 = [[(2,2),(4,2),(4,5),(2,5)], [(7,3),(13,3),(13,6),(7,6)], [(11,1),(14,1),(14,4),(11,4)]]
    sub6, m6, _ = vertical_decompose(r6, o6)
    demos.append(("Demo 6: Auto-clip Outside", r6, o6, sub6, m6, "demo6_clip.png"))

    # --- Demo 7 ---
    r7 = [(0,0),(10,-2),(14,4),(8,12),(2,8)]
    o7 = [[(4,1),(7,1),(7,3.5),(4,3.5)], [(9,5),(12,5.5),(10.5,9)], [(2.5,5),(4,4.5),(5,6.5),(4,7.5)]]
    sub7, m7, _ = vertical_decompose(r7, o7)
    demos.append(("Demo 7: Pentagonal Region", r7, o7, sub7, m7, "demo7_pentagon.png"))

    # --- Demo 8 ---
    r8 = [(0,0),(14,0),(14,12),(0,12),(0,9),(4,9),(4,3),(0,3)]
    o8 = [[(1.5,4),(3,4),(3,8),(1.5,8)], [(6,0.5),(8,0.5),(8,2),(6,2)], [(10,6),(12.5,6),(12.5,7),(10,7)]]
    sub8, m8, _ = vertical_decompose(r8, o8)
    demos.append(("Demo 8: Concave C-shape", r8, o8, sub8, m8, "demo8_concave_c.png"))

    # --- Demo 9 ---
    r9 = [(3,0),(9,0),(9,3),(12,3),(12,9),(9,9),(9,12),(3,12),(3,9),(0,9),(0,3),(3,3)]
    o9 = [[(4,4),(8,4),(8,8),(4,8)], [(10,4),(11.5,4),(11.5,5.5),(10,5.5)]]
    sub9, m9, _ = vertical_decompose(r9, o9)
    demos.append(("Demo 9: Concave Cross", r9, o9, sub9, m9, "demo9_concave_cross.png"))

    # 统一输出 + 保存图
    for title, region, obs, sub, merged, fname in demos:
        print(f"\n{'='*60}")
        print(f"  {title}")
        print(f"{'='*60}")
        print_partition_result(sub, merged)
        _save(region, obs, sub, merged, title, fname)

    print(f"\nAll figures saved to: {out}")
