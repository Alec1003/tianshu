"""
带离散航向状态的网格 A* 路径规划器。

- 网格构建在局部 ENU 对应的经纬高规则栅格上
- 支持禁飞区硬约束 + 威胁场软代价
- 支持方向约束与候选目标点规划
- 支持最小水平转弯半径硬约束
"""

import heapq
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .core.geo import vec_len, vec_sub, llh_to_local, KM_PER_DEG
from .cost import CostEvaluator, CostConfig
from .sectors import ApproachSector


@dataclass
class GridConfig:
    """网格配置."""

    resolution_km: float = 10.0  # 基础网格分辨率 (km)
    altitude_km: List[float] = field(default_factory=lambda: [0.1, 5.0, 10.0, 15.0])
    margin_km: float = 100.0  # 网格边界外扩边距


@dataclass
class PlannerConfig:
    """规划器配置."""

    grid: GridConfig = field(default_factory=GridConfig)
    cost: CostConfig = field(default_factory=CostConfig)
    default_attack_point_radius_km: float = 50.0
    default_attack_point_up_height_km: float = 3.0
    default_attack_point_count: int = 8
    default_approach_ref_radius_km: float = 50.0
    default_approach_ref_up_height_km: float = 0.0
    default_approach_ref_count: int = 4
    heading_count: int = 16
    vertical_open_threat_distance_km: float = 30.0
    threat_tolerance_ratio: float = 0.05
    stealth_rcs_scale: float = 0.4  # mode 4 隐身战机 RCS 缩放因子
    heuristic: str = "ecef"  # "ecef", "fmm", or "dubins"
    use_heading: bool = True  # 是否启用 heading 状态空间


# ============================================================
# 网格
# ============================================================


@dataclass
class Grid:
    """3D 规则网格 (lon/lat/alt → ECEF)."""

    ref_lon: float
    ref_lat: float
    origin_lon: float  # 网格原点经度
    origin_lat: float  # 网格原点纬度
    dlon: float  # 经度步长 (度)
    dlat: float  # 纬度步长 (度)
    nx: int  # 经度方向节点数
    ny: int  # 纬度方向节点数
    altitudes: List[float]  # 高度层 (km)
    node_threat: List[List[List[float]]] = field(default_factory=list)
    node_pos_cache: List[List[List[Tuple[float, float, float]]]] = field(
        default_factory=list
    )
    node_local_cache: List[List[List[Tuple[float, float, float]]]] = field(
        default_factory=list
    )
    dense_nfz: List[List[List[bool]]] = field(default_factory=list)  # 2x 分辨率 NFZ 网格
    resolution_km: float = 10.0  # 网格分辨率 (km)

    def precompute_geometry(self) -> None:
        """预计算所有网格节点的 ECEF 与局部坐标."""
        from .core.geo import llh_to_ecef

        self.node_pos_cache = []
        self.node_local_cache = []
        for i in range(self.nx):
            pos_row = []
            local_row = []
            lon = self.origin_lon + i * self.dlon
            for j in range(self.ny):
                pos_col = []
                local_col = []
                lat = self.origin_lat + j * self.dlat
                for k, alt_km in enumerate(self.altitudes):
                    alt_m = alt_km * 1000.0
                    pos_col.append(llh_to_ecef(lon, lat, alt_m))
                    local_col.append(
                        llh_to_local(lon, lat, alt_m, self.ref_lon, self.ref_lat)
                    )
                pos_row.append(pos_col)
                local_row.append(local_col)
            self.node_pos_cache.append(pos_row)
            self.node_local_cache.append(local_row)

    def precompute_threat(self, threat_field) -> None:
        """预计算所有网格节点的威胁代价."""
        if not self.node_pos_cache:
            self.precompute_geometry()
        self.node_threat = []
        for i in range(self.nx):
            row_i = []
            for j in range(self.ny):
                col_j = []
                for k in range(len(self.altitudes)):
                    pos = self.node_pos_cache[i][j][k]
                    col_j.append(threat_field.total_threat_cost(pos))
                row_i.append(col_j)
            self.node_threat.append(row_i)

    def get_node_threat(self, i: int, j: int, k: int) -> float:
        if not self.node_threat:
            return 0.0
        return self.node_threat[i][j][k]

    def precompute_dense_nfz(self, threat_field) -> None:
        """预计算 2x 分辨率 NFZ 网格.

        2x 网格维度为 (2*nx-1, 2*ny-1, 2*nz-1), 覆盖所有原始节点和相邻节点中点.
        索引映射: 原始节点 (i,j,k) → 2x 索引 (2*i, 2*j, 2*k).
                  相邻节点中点 → 2x 索引 (i1+i2, j1+j2, k1+k2).
        """
        from .core.geo import llh_to_ecef

        if not self.node_pos_cache:
            self.precompute_geometry()
        dn = 2 * self.nx - 1
        dm = 2 * self.ny - 1
        dk = 2 * len(self.altitudes) - 1

        # 构建 2x 高度层 (km)
        alt = self.altitudes
        dense_alts = []
        for a in range(len(alt) - 1):
            dense_alts.append(alt[a])
            dense_alts.append((alt[a] + alt[a + 1]) / 2)
        dense_alts.append(alt[-1])

        self.dense_nfz = []
        for di in range(dn):
            row_i = []
            lon = self.origin_lon + (di / 2) * self.dlon
            for dj in range(dm):
                col_j = []
                lat = self.origin_lat + (dj / 2) * self.dlat
                for dk_idx, alt_km in enumerate(dense_alts):
                    alt_m = alt_km * 1000.0
                    pos = llh_to_ecef(lon, lat, alt_m)
                    col_j.append(threat_field.is_in_no_fly_zone(pos))
                row_i.append(col_j)
            self.dense_nfz.append(row_i)

    def get_dense_nfz(self, di: int, dj: int, dk: int) -> bool:
        if not self.dense_nfz:
            return False
        return self.dense_nfz[di][dj][dk]

    def node_to_pos(self, i: int, j: int, k: int) -> Tuple[float, float, float]:
        """网格索引 → ECEF 坐标 (km)."""
        if self.node_pos_cache:
            return self.node_pos_cache[i][j][k]
        from .core.geo import llh_to_ecef

        lon = self.origin_lon + i * self.dlon
        lat = self.origin_lat + j * self.dlat
        alt_m = self.altitudes[k] * 1000.0
        return llh_to_ecef(lon, lat, alt_m)

    def node_to_llh(self, i: int, j: int, k: int) -> Tuple[float, float, float]:
        """网格索引 → (lon, lat, alt_m)."""
        return (
            self.origin_lon + i * self.dlon,
            self.origin_lat + j * self.dlat,
            self.altitudes[k] * 1000.0,
        )

    def node_to_local(self, i: int, j: int, k: int) -> Tuple[float, float, float]:
        if self.node_local_cache:
            return self.node_local_cache[i][j][k]
        lon, lat, alt_m = self.node_to_llh(i, j, k)
        return llh_to_local(lon, lat, alt_m, self.ref_lon, self.ref_lat)

    def pos_to_node(self, lon, lat, alt_m) -> Tuple[int, int, int]:
        """LLH → 最近网格索引."""
        i = round((lon - self.origin_lon) / self.dlon)
        j = round((lat - self.origin_lat) / self.dlat)
        k = min(
            range(len(self.altitudes)),
            key=lambda _k: abs(self.altitudes[_k] - alt_m / 1000.0),
        )
        return (max(0, min(self.nx - 1, i)), max(0, min(self.ny - 1, j)), k)

    def in_bounds(self, i: int, j: int, k: int) -> bool:
        return 0 <= i < self.nx and 0 <= j < self.ny and 0 <= k < len(self.altitudes)


def precompute_fmm_distance(
    grid: Grid,
    goal_node: Tuple[int, int, int],
    threat_field,
    threat_weight: float = 100.0,
) -> List[List[List[float]]]:
    """FMM on grid graph with threat-weighted edges + NFZ obstacles.

    Edge cost matches A* threat model exactly:
      edge_km * (1 + threat_weight * ((t1+t2)/2 + t_mid) / 2)

    NFZ cells are impassable (INF).
    Returns fmm_dist[i][j][k] = shortest effective-distance (km-equiv) to goal.

    Admissible by construction: FMM edge cost ≤ A* edge cost (missing turn/dir penalties).
    """
    nx, ny, nz = grid.nx, grid.ny, len(grid.altitudes)
    INF = float('inf')
    n_nodes = nx * ny * nz
    have_threat = bool(grid.node_threat) and threat_weight > 0

    # ---- obstacle mask + node threat cache ----
    obstacle = [[[False] * nz for _ in range(ny)] for __ in range(nx)]
    node_th = [[[0.0] * nz for _ in range(ny)] for __ in range(nx)]
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                pos_ecef = grid.node_to_pos(i, j, k)
                if threat_field.is_in_no_fly_zone(pos_ecef):
                    obstacle[i][j][k] = True
                elif have_threat:
                    node_th[i][j][k] = grid.get_node_threat(i, j, k)

    def idx(i, j, k):
        return (i * ny + j) * nz + k

    dist = [INF] * n_nodes
    state = [0] * n_nodes  # 0=FAR, 1=TRIAL, 2=KNOWN

    gi, gj, gk = goal_node
    if not (0 <= gi < nx and 0 <= gj < ny and 0 <= gk < nz) or obstacle[gi][gj][gk]:
        fmm = [[[INF] * nz for _ in range(ny)] for __ in range(nx)]
        return fmm

    dist[idx(gi, gj, gk)] = 0.0
    state[idx(gi, gj, gk)] = 2  # KNOWN

    neighbors = [
        (di, dj, dk)
        for di in (-1, 0, 1) for dj in (-1, 0, 1) for dk in (-1, 0, 1)
        if not (di == 0 and dj == 0 and dk == 0)
    ]

    trial: List[Tuple[float, int, int, int]] = []
    goal_local = grid.node_to_local(gi, gj, gk)
    goal_th = node_th[gi][gj][gk]

    # Initialize trial set from goal neighbors
    for di, dj, dk in neighbors:
        ni, nj, nk = gi + di, gj + dj, gk + dk
        if not (0 <= ni < nx and 0 <= nj < ny and 0 <= nk < nz):
            continue
        if obstacle[ni][nj][nk]:
            continue
        nb_local = grid.node_to_local(ni, nj, nk)
        edge = ((nb_local[0] - goal_local[0]) ** 2
              + (nb_local[1] - goal_local[1]) ** 2
              + (nb_local[2] - goal_local[2]) ** 2) ** 0.5
        d = edge * (1.0 + threat_weight * (goal_th + node_th[ni][nj][nk]))
        didx = idx(ni, nj, nk)
        dist[didx] = d
        state[didx] = 1
        heapq.heappush(trial, (d, ni, nj, nk))

    # ---- main FMM loop ----
    while trial:
        d, i, j, k = heapq.heappop(trial)
        didx = idx(i, j, k)
        if state[didx] == 2:
            continue
        if d > dist[didx]:
            continue
        state[didx] = 2

        cur_local = grid.node_to_local(i, j, k)
        cur_dist = dist[didx]
        cur_th = node_th[i][j][k]

        for di, dj, dk in neighbors:
            ni, nj, nk = i + di, j + dj, k + dk
            if not (0 <= ni < nx and 0 <= nj < ny and 0 <= nk < nz):
                continue
            nidx = idx(ni, nj, nk)
            if obstacle[ni][nj][nk] or state[nidx] == 2:
                continue

            nb_local = grid.node_to_local(ni, nj, nk)
            edge = ((nb_local[0] - cur_local[0]) ** 2
                  + (nb_local[1] - cur_local[1]) ** 2
                  + (nb_local[2] - cur_local[2]) ** 2) ** 0.5
            edge_cost = edge * (1.0 + threat_weight * (cur_th + node_th[ni][nj][nk]))

            new_dist = cur_dist + edge_cost
            if new_dist < dist[nidx]:
                dist[nidx] = new_dist
                if state[nidx] != 1:
                    state[nidx] = 1
                heapq.heappush(trial, (new_dist, ni, nj, nk))

    fmm = [[[INF] * nz for _ in range(ny)] for __ in range(nx)]
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                fmm[i][j][k] = dist[idx(i, j, k)]
    return fmm


def _precompute_threat_exposure(
    grid: Grid,
    root_node: Tuple[int, int, int],
    threat_field,
) -> List[List[List[float]]]:
    """FMM computing minimum Pd exposure (no distance component) to root_node.

    Edge cost: min(t1, t2) * 0.5 * edge_km  — admissible lower bound for
    the threat exposure Σ avg_threat * length in A* (min ≤ avg, 0.5 factor).

    26-connectivity, NFZ cells impassable.
    """
    nx, ny, nz = grid.nx, grid.ny, len(grid.altitudes)
    INF = float('inf')
    n_nodes = nx * ny * nz

    obstacle = [[[False] * nz for _ in range(ny)] for __ in range(nx)]
    node_th = [[[0.0] * nz for _ in range(ny)] for __ in range(nx)]
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                pos_ecef = grid.node_to_pos(i, j, k)
                if threat_field.is_in_no_fly_zone(pos_ecef):
                    obstacle[i][j][k] = True
                if grid.node_threat and grid.get_node_threat(i, j, k) > 0:
                    node_th[i][j][k] = grid.get_node_threat(i, j, k)

    def idx(i, j, k):
        return (i * ny + j) * nz + k

    dist = [INF] * n_nodes
    state = [0] * n_nodes

    ri, rj, rk = root_node
    if not (0 <= ri < nx and 0 <= rj < ny and 0 <= rk < nz):
        return [[[INF] * nz for _ in range(ny)] for __ in range(nx)]

    dist[idx(ri, rj, rk)] = 0.0
    state[idx(ri, rj, rk)] = 2

    neighbors = [
        (di, dj, dk)
        for di in (-1, 0, 1) for dj in (-1, 0, 1) for dk in (-1, 0, 1)
        if not (di == 0 and dj == 0 and dk == 0)
    ]

    trial: List[Tuple[float, int, int, int]] = []
    root_local = grid.node_to_local(ri, rj, rk)
    root_th = node_th[ri][rj][rk]

    for di, dj, dk in neighbors:
        ni, nj, nk = ri + di, rj + dj, rk + dk
        if not (0 <= ni < nx and 0 <= nj < ny and 0 <= nk < nz):
            continue
        if obstacle[ni][nj][nk]:
            continue
        nb_local = grid.node_to_local(ni, nj, nk)
        edge = ((nb_local[0] - root_local[0]) ** 2
              + (nb_local[1] - root_local[1]) ** 2
              + (nb_local[2] - root_local[2]) ** 2) ** 0.5
        d = edge * (root_th + node_th[ni][nj][nk])
        didx = idx(ni, nj, nk)
        dist[didx] = d
        state[didx] = 1
        heapq.heappush(trial, (d, ni, nj, nk))

    while trial:
        d, i, j, k = heapq.heappop(trial)
        didx = idx(i, j, k)
        if state[didx] == 2:
            continue
        if d > dist[didx]:
            continue
        state[didx] = 2

        cur_local = grid.node_to_local(i, j, k)
        cur_dist = dist[didx]
        cur_th = node_th[i][j][k]

        for di, dj, dk in neighbors:
            ni, nj, nk = i + di, j + dj, k + dk
            if not (0 <= ni < nx and 0 <= nj < ny and 0 <= nk < nz):
                continue
            nidx = idx(ni, nj, nk)
            if obstacle[ni][nj][nk] or state[nidx] == 2:
                continue

            nb_local = grid.node_to_local(ni, nj, nk)
            edge = ((nb_local[0] - cur_local[0]) ** 2
                  + (nb_local[1] - cur_local[1]) ** 2
                  + (nb_local[2] - cur_local[2]) ** 2) ** 0.5
            edge_cost = edge * (cur_th + node_th[ni][nj][nk])

            new_dist = cur_dist + edge_cost
            if new_dist < dist[nidx]:
                dist[nidx] = new_dist
                if state[nidx] != 1:
                    state[nidx] = 1
                heapq.heappush(trial, (new_dist, ni, nj, nk))

    result = [[[INF] * nz for _ in range(ny)] for __ in range(nx)]
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                result[i][j][k] = dist[idx(i, j, k)]
    return result


def build_grid(
    points_llh: List[Tuple[float, float, float]],  # [(lon, lat, alt_m)]
    config: GridConfig,
    ref_lon: float,
    ref_lat: float,
) -> Grid:
    """根据场景关键点 (WGS84) 构建 lon/lat 网格."""
    import math as _m

    margin_deg = config.margin_km / KM_PER_DEG
    min_lon = min(p[0] for p in points_llh) - margin_deg
    max_lon = max(p[0] for p in points_llh) + margin_deg
    min_lat = min(p[1] for p in points_llh) - margin_deg
    max_lat = max(p[1] for p in points_llh) + margin_deg

    mid_lat = (min_lat + max_lat) / 2
    dlon = config.resolution_km / (KM_PER_DEG * _m.cos(_m.radians(mid_lat)))
    dlat = config.resolution_km / KM_PER_DEG

    nx = max(3, int((max_lon - min_lon) / dlon) + 1)
    ny = max(3, int((max_lat - min_lat) / dlat) + 1)

    return Grid(
        ref_lon=ref_lon,
        ref_lat=ref_lat,
        origin_lon=min_lon,
        origin_lat=min_lat,
        dlon=dlon,
        dlat=dlat,
        nx=nx,
        ny=ny,
        altitudes=list(config.altitude_km),
        resolution_km=config.resolution_km,
    )


# ============================================================
# A* 搜索
# ============================================================

INF = float("inf")


_HEADING_DELTAS: Dict[int, List[Tuple[int, int]]] = {
    4: [
        (0, 1),
        (1, 0),
        (0, -1),
        (-1, 0),
    ],
    8: [
        (0, 1),
        (1, 1),
        (1, 0),
        (1, -1),
        (0, -1),
        (-1, -1),
        (-1, 0),
        (-1, 1),
    ],
    12: [
        (0, 1),
        (1, 2),
        (2, 1),
        (1, 0),
        (2, -1),
        (1, -2),
        (0, -1),
        (-1, -2),
        (-2, -1),
        (-1, 0),
        (-2, 1),
        (-1, 2),
    ],
    16: [
        (0, 1),    # 0° — 北
        (1, 2),    # ~26.6°
        (1, 1),    # 45°
        (2, 1),    # ~63.4°
        (1, 0),    # 90° — 东
        (2, -1),   # ~116.6°
        (1, -1),   # 135°
        (1, -2),   # ~153.4°
        (0, -1),   # 180° — 南
        (-1, -2),  # ~206.6°
        (-1, -1),  # 225°
        (-2, -1),  # ~243.4°
        (-1, 0),   # 270° — 西
        (-2, 1),   # ~296.6°
        (-1, 1),   # 315°
        (-1, 2),   # ~333.4°
    ],
}


def _heading_table(heading_count: int) -> List[Tuple[int, int]]:
    if heading_count not in _HEADING_DELTAS:
        raise ValueError(
            f"unsupported heading_count={heading_count}; currently only 4, 8, 12, 16 are supported"
        )
    return _HEADING_DELTAS[heading_count]


# Heading 预计算表: (angle_rad, vector, angle_delta_matrix)
_HEADING_ANGLES: Dict[int, List[float]] = {}
_HEADING_VECTORS: Dict[int, List[Tuple[float, float]]] = {}
_HEADING_ANGLE_DELTAS: Dict[int, List[List[float]]] = {}

for _hc, _deltas in _HEADING_DELTAS.items():
    _n = _hc
    # angle per heading
    _angles = [math.atan2(di, dj) % (2.0 * math.pi) for di, dj in _deltas]
    _HEADING_ANGLES[_hc] = _angles
    # unit vector per heading
    _vectors = []
    for di, dj in _deltas:
        _l = math.hypot(di, dj)
        _vectors.append((di / _l, dj / _l) if _l > 1e-9 else (0.0, 0.0))
    _HEADING_VECTORS[_hc] = _vectors
    # pairwise angle delta
    _ad = [[0.0] * _n for _ in range(_n)]
    for _a in range(_n):
        for _b in range(_n):
            _d = abs(_angles[_a] - _angles[_b])
            _ad[_a][_b] = _d if _d <= math.pi else 2.0 * math.pi - _d
    _HEADING_ANGLE_DELTAS[_hc] = _ad

# Lazy-computed turn radius table per grid, keyed by (id(grid), heading_count).
# Uses actual ENU step sizes from the grid's representative center node.
_TURN_RADIUS_CACHE: Dict[Tuple[int, int], List[List[float]]] = {}

# Cache for _precompute_threat_exposure results keyed by (id(grid), root_i, root_j, root_k)
_THREAT_EXPOSURE_CACHE: Dict[Tuple[int, int, int, int], List[List[List[float]]]] = {}


def _get_turn_radius_table(grid, heading_count):
    key = (id(grid), heading_count)
    cached = _TURN_RADIUS_CACHE.get(key)
    if cached is not None:
        return cached
    # Use center node of grid for representative ENU step sizes
    ci, cj = grid.nx // 2, grid.ny // 2
    ck = 0
    center = grid.node_to_local(ci, cj, ck)
    east = grid.node_to_local(ci + 1, cj, ck)
    north = grid.node_to_local(ci, cj + 1, ck)
    rx = east[0] - center[0]  # actual east step (km)
    ry = north[1] - center[1]  # actual north step (km)

    deltas = _heading_table(heading_count)
    n = heading_count
    R = [[0.0] * n for _ in range(n)]
    for a in range(n):
        dai, daj = deltas[a]
        for b in range(n):
            dbi, dbj = deltas[b]
            abx, aby = dai * rx, daj * ry
            bcx, bcy = dbi * rx, dbj * ry
            cross = abx * bcy - aby * bcx
            if abs(cross) < 1e-9:
                dot = abx * bcx + aby * bcy
                R[a][b] = 0.0 if dot < 0 else float("inf")
            else:
                ab = math.hypot(abx, aby)
                bc = math.hypot(bcx, bcy)
                ac = math.hypot(abx + bcx, aby + bcy)
                R[a][b] = (ab * bc * ac) / (2.0 * abs(cross))
    _TURN_RADIUS_CACHE[key] = R
    return R


def _cached_threat_exposure(grid, root_node, threat_field):
    """Cache wrapper for _precompute_threat_exposure."""
    key = (id(grid), root_node[0], root_node[1], root_node[2])
    cached = _THREAT_EXPOSURE_CACHE.get(key)
    if cached is not None:
        return cached
    result = _precompute_threat_exposure(grid, root_node, threat_field)
    _THREAT_EXPOSURE_CACHE[key] = result
    return result


@dataclass
class AStarNode:
    """A* 搜索节点."""

    g: float = INF
    parent: Optional[Tuple[int, int, int, int]] = None
    closed: bool = False


def _heading_vector(heading_id: int, heading_count: int) -> Tuple[float, float]:
    return _HEADING_VECTORS[heading_count][heading_id]


def _heading_delta(heading_id: int, heading_count: int) -> Tuple[int, int]:
    return _heading_table(heading_count)[heading_id]


def _heading_angle_rad(heading_id: int, heading_count: int) -> float:
    return _HEADING_ANGLES[heading_count][heading_id]


def _heading_angle_delta(a: int, b: int, heading_count: int) -> float:
    return _HEADING_ANGLE_DELTAS[heading_count][a][b]


def _heading_from_vector(
    dx: float,
    dy: float,
    heading_count: int,
) -> int:
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return 0
    angle = math.atan2(dx, dy) % (2.0 * math.pi)
    best_heading = 0
    best_diff = float("inf")
    angles = _HEADING_ANGLES[heading_count]
    for heading_id, ha in enumerate(angles):
        diff = abs(angle - ha)
        if diff > math.pi:
            diff = 2.0 * math.pi - diff
        if diff < best_diff:
            best_diff = diff
            best_heading = heading_id
    return best_heading


def _initial_heading_ids(
    heading_count: int,
    initial_heading_deg: Optional[float],
) -> List[int]:
    if initial_heading_deg is None:
        return list(range(heading_count))
    angle = math.radians(initial_heading_deg) % (2.0 * math.pi)
    best_heading = 0
    best_diff = float("inf")
    angles = _HEADING_ANGLES[heading_count]
    for heading_id, ha in enumerate(angles):
        diff = abs(angle - ha)
        if diff > math.pi:
            diff = 2.0 * math.pi - diff
        if diff < best_diff:
            best_diff = diff
            best_heading = heading_id
    return [best_heading]


def _heading_neighbors(
    grid: Grid,
    state: Tuple[int, int, int, int],
    heading_count: int,
    min_turn_radius_km: float,
    goal_node: Tuple[int, int, int],
    vertical_open_threat_distance_km: float,
    threat_field,
    evaluator=None,
) -> List[Tuple[Tuple[int, int, int, int], float]]:
    i, j, k, heading_id = state
    result = []
    max_step = max(1, heading_count // 8)
    deltas = _heading_table(heading_count)  # local ref, avoid dict lookup in loop
    ad_mat = _HEADING_ANGLE_DELTAS[heading_count]
    curr_local = grid.node_to_local(i, j, k)
    goal_local = grid.node_to_local(*goal_node)
    goal_dist = vec_len(vec_sub(curr_local, goal_local))
    allow_full_vertical = (
        vertical_open_threat_distance_km > 0.0
        and threat_field.min_distance_to_any_threat(curr_local)
        <= vertical_open_threat_distance_km
    )
    if goal_dist <= vertical_open_threat_distance_km:
        allow_full_vertical = True
    allowed_dks = [0]
    if allow_full_vertical:
        allowed_dks.extend([-1, 1])
    elif k != goal_node[2]:
        allowed_dks.append(1 if goal_node[2] > k else -1)

    dedup_dks = []
    for dk in allowed_dks:
        if dk not in dedup_dks:
            dedup_dks.append(dk)

    allowed_heading_ids = []
    if min_turn_radius_km > 0.0:
        turn_radius = _get_turn_radius_table(grid, heading_count)
        di_prev, dj_prev = deltas[heading_id]
        pi = i - di_prev
        pj = j - dj_prev
        have_prev = 0 <= pi < grid.nx and 0 <= pj < grid.ny
    for delta in range(-max_step, max_step + 1):
        cand_h = (heading_id + delta) % heading_count
        dx, dy = deltas[cand_h]
        if dx == 0 and dy == 0:
            continue
        if min_turn_radius_km > 0.0:
            ni = i + dx
            nj = j + dy
            if not (0 <= ni < grid.nx and 0 <= nj < grid.ny):
                continue
            if have_prev:
                if turn_radius[heading_id][cand_h] < min_turn_radius_km:
                    continue
        allowed_heading_ids.append(cand_h)

    for cand_h in allowed_heading_ids:
        dx, dy = deltas[cand_h]
        for dk in dedup_dks:
            ni = i + dx
            nj = j + dy
            nk = k + dk
            if 0 <= ni < grid.nx and 0 <= nj < grid.ny and 0 <= nk < len(grid.altitudes):
                result.append(((ni, nj, nk, cand_h), ad_mat[heading_id][cand_h]))

    # Sort by FMM gradient alignment: explore goal-directed headings first.
    # This helps bidirectional search find good meeting points earlier (tighter mu).
    if evaluator is not None:
        result.sort(
            key=lambda item: -evaluator.fmm_gradient_alignment(
                i, j, k, deltas[item[0][3]][0],
                deltas[item[0][3]][1], heading_count
            )
        )
    return result


def _state_prev_dir(
    state: Tuple[int, int, int, int],
    heading_count: int,
) -> Tuple[float, float, float]:
    dx, dy = _heading_vector(state[3], heading_count)
    return dx, dy, 0.0


def _step_cost(
    grid: Grid,
    current: Tuple[int, int, int, int],
    neighbor: Tuple[int, int, int, int],
    evaluator: CostEvaluator,
    target_pos: Tuple[float, float, float],
    desired_direction: Tuple[float, float, float],
    heading_count: int,
    use_prev_heading: bool,
) -> Tuple[float, bool]:
    ci, cj, ck, _ = current
    ni, nj, nk, _ = neighbor
    cur_pos = grid.node_to_pos(ci, cj, ck)
    nb_pos = grid.node_to_pos(ni, nj, nk)
    cur_local = grid.node_to_local(ci, cj, ck)
    nb_local = grid.node_to_local(ni, nj, nk)
    t_cur = grid.get_node_threat(ci, cj, ck) if grid.node_threat else None
    t_nb = grid.get_node_threat(ni, nj, nk) if grid.node_threat else None
    prev_dir = _state_prev_dir(current, heading_count) if use_prev_heading else None
    return evaluator.edge_cost(
        cur_pos,
        nb_pos,
        target_pos,
        desired_direction,
        threat_at_p1=t_cur,
        threat_at_p2=t_nb,
        prev_dir=prev_dir,
        dense_nfz=grid.dense_nfz if grid.dense_nfz else None,
        n1=(ci, cj, ck),
        n2=(ni, nj, nk),
        p1_local=cur_local,
        p2_local=nb_local,
        target_local=getattr(evaluator, '_target_local', None),
    )


def _goal_terminal_states(
    grid: Grid,
    goal_node: Tuple[int, int, int],
    heading_count: int,
) -> List[Tuple[int, int, int, int]]:
    del grid
    return [
        (goal_node[0], goal_node[1], goal_node[2], heading_id)
        for heading_id in range(heading_count)
    ]


def _reverse_predecessors(
    grid: Grid,
    state: Tuple[int, int, int, int],
    heading_count: int,
    min_turn_radius_km: float,
    goal_node: Tuple[int, int, int],
    vertical_open_threat_distance_km: float,
    threat_field,
) -> List[Tuple[int, int, int, int]]:
    """返回所有能合法转移到 state 的前驱状态 (直接计算, 不调用 _heading_neighbors)."""
    i, j, k, heading_id = state
    deltas = _heading_table(heading_count)
    di, dj = deltas[heading_id]
    pi = i - di
    pj = j - dj
    if not (0 <= pi < grid.nx and 0 <= pj < grid.ny):
        return []

    max_step = max(1, heading_count // 8)

    # 合法的前驱航向: 正向 transfer 的对称集合
    valid_prev_headings = [
        (heading_id - delta) % heading_count
        for delta in range(-max_step, max_step + 1)
    ]

    # 垂直转移: 在前驱位置评估
    pred_local = grid.node_to_local(pi, pj, k)
    goal_local = grid.node_to_local(*goal_node)
    goal_dist = vec_len(vec_sub(pred_local, goal_local))
    allow_full_vertical = (
        vertical_open_threat_distance_km > 0.0
        and threat_field.min_distance_to_any_threat(pred_local)
        <= vertical_open_threat_distance_km
    ) or goal_dist <= vertical_open_threat_distance_km

    curr_local = grid.node_to_local(i, j, k)
    predecessors: List[Tuple[int, int, int, int]] = []
    if min_turn_radius_km > 0.0:
        turn_radius = _get_turn_radius_table(grid, heading_count)

    for ph in valid_prev_headings:
        if min_turn_radius_km > 0.0:
            dpi, dpj = deltas[ph]
            ppi = pi - dpi
            ppj = pj - dpj
            if 0 <= ppi < grid.nx and 0 <= ppj < grid.ny:
                if turn_radius[ph][heading_id] < min_turn_radius_km:
                    continue

        for pk in (k, k - 1, k + 1):
            if not (0 <= pk < len(grid.altitudes)):
                continue
            if pk == k:
                predecessors.append((pi, pj, pk, ph))
            elif allow_full_vertical:
                predecessors.append((pi, pj, pk, ph))
            elif (goal_node[2] > pk and k > pk) or (goal_node[2] < pk and k < pk):
                predecessors.append((pi, pj, pk, ph))

    return predecessors


def a_star_search(
    grid: Grid,
    start_node: Tuple[int, int, int],
    goal_node: Tuple[int, int, int],
    evaluator: CostEvaluator,
    target_pos: Tuple[float, float, float],
    desired_direction: Tuple[float, float, float],
    heading_count: int,
    min_turn_radius_km: float,
    initial_heading_deg: Optional[float],
    vertical_open_threat_distance_km: float,
) -> Tuple[Optional[List[Tuple[float, float, float]]], float, int]:
    """带离散航向状态的单向 A* 搜索.

    Returns:
        (path, search_time_sec, expanded_nodes).
    """
    t0 = __import__("time").perf_counter()

    nodes: Dict[Tuple[int, int, int, int], AStarNode] = {}

    goal_pos = grid.node_to_pos(*goal_node)
    open_set: List[Tuple[float, int, Tuple[int, int, int, int]]] = []
    counter = 0

    for heading_id in _initial_heading_ids(heading_count, initial_heading_deg):
        state = (start_node[0], start_node[1], start_node[2], heading_id)
        nodes[state] = AStarNode(g=0.0)
        h_init = evaluator.heuristic_by_index(start_node[0], start_node[1], start_node[2], heading_id)
        if h_init < 0:
            h_init = evaluator.heuristic(
                grid.node_to_pos(*start_node), grid.node_to_pos(*goal_node)
            )
        heapq.heappush(open_set, (h_init, counter, state))
        counter += 1

    best_goal_state: Optional[Tuple[int, int, int, int]] = None
    best_goal_cost = INF
    expanded = 0

    while open_set:
        _, _, current = heapq.heappop(open_set)
        cur_node = nodes.get(current)
        if cur_node is None or cur_node.closed:
            continue
        cur_node.closed = True
        expanded += 1

        ci, cj, ck, _ = current
        if (ci, cj, ck) == goal_node:
            if cur_node.g < best_goal_cost:
                best_goal_cost = cur_node.g
                best_goal_state = current
            continue

        for neighbor, _ in _heading_neighbors(
            grid,
            current,
            heading_count,
            min_turn_radius_km,
            goal_node,
            vertical_open_threat_distance_km,
            evaluator.threat_field,
            evaluator=evaluator,
        ):
            ni, nj, nk, nh = neighbor
            nb_node = nodes.get(neighbor)
            if nb_node is not None and nb_node.closed:
                continue
            if nb_node is None:
                nb_node = AStarNode()
                nodes[neighbor] = nb_node

            ec, valid = _step_cost(
                grid,
                current,
                neighbor,
                evaluator,
                target_pos,
                desired_direction,
                heading_count,
                use_prev_heading=cur_node.parent is not None,
            )
            if not valid:
                continue

            new_g = cur_node.g + ec
            if new_g < nb_node.g:
                nb_node.g = new_g
                nb_node.parent = current
                h = evaluator.heuristic_by_index(ni, nj, nk, nh)
                if h < 0:
                    h = evaluator.heuristic(
                        grid.node_to_pos(ni, nj, nk), goal_pos
                    )
                heapq.heappush(open_set, (new_g + h, counter, neighbor))
                counter += 1

    elapsed = __import__("time").perf_counter() - t0

    if best_goal_state is None:
        return None, elapsed, expanded

    path = []
    cur = best_goal_state
    while cur is not None:
        path.append(grid.node_to_pos(*cur[:3]))
        node = nodes.get(cur)
        cur = node.parent if node else None
    path.reverse()
    return path, elapsed, expanded


def bidirectional_a_star_search(
    grid: Grid,
    start_node: Tuple[int, int, int],
    goal_node: Tuple[int, int, int],
    evaluator: CostEvaluator,
    target_pos: Tuple[float, float, float],
    desired_direction: Tuple[float, float, float],
    heading_count: int,
    min_turn_radius_km: float,
    initial_heading_deg: Optional[float],
    vertical_open_threat_distance_km: float,
) -> Tuple[Optional[List[Tuple[float, float, float]]], float, int]:
    """带离散航向状态的双向 A* 搜索.

    Returns:
        (path, search_time_sec, expanded_nodes).
    """
    t0 = __import__("time").perf_counter()

    forward_nodes: Dict[Tuple[int, int, int, int], AStarNode] = {}
    reverse_nodes: Dict[Tuple[int, int, int, int], AStarNode] = {}
    start_pos = grid.node_to_pos(*start_node)
    goal_pos = grid.node_to_pos(*goal_node)
    terminal_states = _goal_terminal_states(
        grid, goal_node, heading_count
    )
    if not terminal_states:
        return None, __import__("time").perf_counter() - t0, 0

    forward_open: List[Tuple[float, int, Tuple[int, int, int, int]]] = []
    reverse_open: List[Tuple[float, int, Tuple[int, int, int, int]]] = []
    counter = 0

    for heading_id in _initial_heading_ids(heading_count, initial_heading_deg):
        state = (start_node[0], start_node[1], start_node[2], heading_id)
        forward_nodes[state] = AStarNode(g=0.0)
        h_init = evaluator.heuristic_by_index(start_node[0], start_node[1], start_node[2], heading_id)
        if h_init < 0:
            h_init = evaluator.heuristic(start_pos, goal_pos)
        heapq.heappush(forward_open, (h_init, counter, state))
        counter += 1

    for state in terminal_states:
        reverse_nodes[state] = AStarNode(g=0.0)
        gi, gj, gk, gh = state
        h_rev_init = evaluator.heuristic_by_index_reverse(gi, gj, gk, gh)
        if h_rev_init < 0:
            h_rev_init = evaluator.heuristic(
                grid.node_to_pos(gi, gj, gk), start_pos
            )
        heapq.heappush(reverse_open, (h_rev_init, counter, state))
        counter += 1

    best_meeting_state: Optional[Tuple[int, int, int, int]] = None
    mu = INF
    expanded = 0

    def min_open_f(
        open_set: List[Tuple[float, int, Tuple[int, int, int, int]]],
        nodes: Dict[Tuple[int, int, int, int], AStarNode],
    ) -> float:
        while open_set:
            f, _, state = open_set[0]
            node = nodes.get(state)
            if node is None or node.closed:
                heapq.heappop(open_set)
                continue
            return f
        return INF

    while forward_open and reverse_open:
        min_f_forward = min_open_f(forward_open, forward_nodes)
        min_f_reverse = min_open_f(reverse_open, reverse_nodes)
        if min_f_forward >= mu and min_f_reverse >= mu:
            break

        expand_forward = min_f_forward <= min_f_reverse

        if expand_forward:
            _, _, current = heapq.heappop(forward_open)
            cur_node = forward_nodes.get(current)
            if cur_node is None or cur_node.closed:
                continue
            cur_node.closed = True
            expanded += 1

            rev_match = reverse_nodes.get(current)
            if rev_match is not None:
                total_cost = cur_node.g + rev_match.g
                if total_cost < mu:
                    mu = total_cost
                    best_meeting_state = current

            for neighbor, _ in _heading_neighbors(
                grid,
                current,
                heading_count,
                min_turn_radius_km,
                goal_node,
                vertical_open_threat_distance_km,
                evaluator.threat_field,
            ):
                nb_node = forward_nodes.get(neighbor)
                if nb_node is not None and nb_node.closed:
                    continue
                if nb_node is None:
                    nb_node = AStarNode()
                    forward_nodes[neighbor] = nb_node

                edge_cost, valid = _step_cost(
                    grid,
                    current,
                    neighbor,
                    evaluator,
                    target_pos,
                    desired_direction,
                    heading_count,
                    use_prev_heading=cur_node.parent is not None,
                )
                if not valid:
                    continue

                new_g = cur_node.g + edge_cost
                if new_g < nb_node.g:
                    nb_node.g = new_g
                    nb_node.parent = current
                    ni, nj, nk, nh = neighbor
                    h = evaluator.heuristic_by_index(ni, nj, nk, nh)
                    if h < 0:
                        h = evaluator.heuristic(
                            grid.node_to_pos(ni, nj, nk), goal_pos
                        )
                    heapq.heappush(forward_open, (new_g + h, counter, neighbor))
                    counter += 1

                    rev_match = reverse_nodes.get(neighbor)
                    if rev_match is not None:
                        total_cost = new_g + rev_match.g
                        if total_cost < mu:
                            mu = total_cost
                            best_meeting_state = neighbor
        else:
            _, _, current = heapq.heappop(reverse_open)
            cur_node = reverse_nodes.get(current)
            if cur_node is None or cur_node.closed:
                continue
            cur_node.closed = True
            expanded += 1

            fwd_match = forward_nodes.get(current)
            if fwd_match is not None:
                total_cost = fwd_match.g + cur_node.g
                if total_cost < mu:
                    mu = total_cost
                    best_meeting_state = current

            for predecessor in _reverse_predecessors(
                grid,
                current,
                heading_count,
                min_turn_radius_km,
                goal_node,
                vertical_open_threat_distance_km,
                evaluator.threat_field,
            ):
                prev_node = reverse_nodes.get(predecessor)
                if prev_node is not None and prev_node.closed:
                    continue
                if prev_node is None:
                    prev_node = AStarNode()
                    reverse_nodes[predecessor] = prev_node

                edge_cost, valid = _step_cost(
                    grid,
                    predecessor,
                    current,
                    evaluator,
                    target_pos,
                    desired_direction,
                    heading_count,
                    use_prev_heading=True,
                )
                if not valid:
                    continue

                new_g = cur_node.g + edge_cost
                if new_g < prev_node.g:
                    prev_node.g = new_g
                    prev_node.parent = current
                    pi, pj, pk, ph = predecessor
                    h_rev = evaluator.heuristic_by_index_reverse(pi, pj, pk, ph)
                    if h_rev < 0:
                        h_rev = evaluator.heuristic(
                            grid.node_to_pos(pi, pj, pk), start_pos
                        )
                    heapq.heappush(reverse_open, (new_g + h_rev, counter, predecessor))
                    counter += 1

                    fwd_match = forward_nodes.get(predecessor)
                    if fwd_match is not None:
                        total_cost = fwd_match.g + new_g
                        if total_cost < mu:
                            mu = total_cost
                            best_meeting_state = predecessor

    elapsed = __import__("time").perf_counter() - t0

    if best_meeting_state is None:
        return None, elapsed, expanded

    forward_path = []
    cur = best_meeting_state
    while cur is not None:
        forward_path.append(grid.node_to_pos(*cur[:3]))
        node = forward_nodes.get(cur)
        cur = node.parent if node else None
    forward_path.reverse()

    reverse_path = []
    cur = reverse_nodes.get(best_meeting_state).parent
    while cur is not None:
        reverse_path.append(grid.node_to_pos(*cur[:3]))
        node = reverse_nodes.get(cur)
        cur = node.parent if node else None

    return forward_path + reverse_path, elapsed, expanded


# ============================================================
# 3D A* (无 heading，26-连通)
# ============================================================


def _neighbors_3d(
    grid: Grid,
    i: int,
    j: int,
    k: int,
) -> List[Tuple[int, int, int]]:
    """26-connected neighbours, in-bounds only."""
    result = []
    for di in (-1, 0, 1):
        ni = i + di
        if not (0 <= ni < grid.nx):
            continue
        for dj in (-1, 0, 1):
            nj = j + dj
            if not (0 <= nj < grid.ny):
                continue
            for dk in (-1, 0, 1):
                if di == 0 and dj == 0 and dk == 0:
                    continue
                nk = k + dk
                if 0 <= nk < len(grid.altitudes):
                    result.append((ni, nj, nk))
    return result


def a_star_search_3d(
    grid: Grid,
    start_node: Tuple[int, int, int],
    goal_node: Tuple[int, int, int],
    evaluator: CostEvaluator,
    target_pos: Tuple[float, float, float],
    desired_direction: Tuple[float, float, float],
) -> Tuple[Optional[List[Tuple[float, float, float]]], float, int]:
    """3D A* 搜索，状态为 (i,j,k)，26-连通，无 heading 约束.

    Returns:
        (path, search_time_sec, expanded_nodes).
    """
    t0 = __import__("time").perf_counter()
    INF = float('inf')

    nodes: Dict[Tuple[int, int, int], AStarNode] = {}

    goal_pos = grid.node_to_pos(*goal_node)
    open_set: List[Tuple[float, int, Tuple[int, int, int]]] = []
    counter = 0

    si, sj, sk = start_node
    state = (si, sj, sk)
    nodes[state] = AStarNode(g=0.0)
    h_init = evaluator.heuristic_by_index(si, sj, sk)
    if h_init < 0:
        h_init = evaluator.heuristic(
            grid.node_to_pos(si, sj, sk), goal_pos
        )
    heapq.heappush(open_set, (h_init, counter, state))
    counter += 1

    best_cost = INF
    best_state: Optional[Tuple[int, int, int]] = None
    expanded = 0

    while open_set:
        _, _, current = heapq.heappop(open_set)
        cur_node = nodes.get(current)
        if cur_node is None or cur_node.closed:
            continue
        cur_node.closed = True
        expanded += 1

        ci, cj, ck = current
        if (ci, cj, ck) == goal_node:
            if cur_node.g < best_cost:
                best_cost = cur_node.g
                best_state = current
            continue

        cur_pos = grid.node_to_pos(ci, cj, ck)
        t_cur = grid.get_node_threat(ci, cj, ck) if grid.node_threat else None

        for ni, nj, nk in _neighbors_3d(grid, ci, cj, ck):
            # NFZ check
            nb_pos = grid.node_to_pos(ni, nj, nk)
            if evaluator.threat_field.is_in_no_fly_zone(nb_pos):
                continue

            t_nb = grid.get_node_threat(ni, nj, nk) if grid.node_threat else None
            ec, valid = evaluator.edge_cost(
                cur_pos, nb_pos, target_pos, desired_direction,
                threat_at_p1=t_cur, threat_at_p2=t_nb,
                prev_dir=None,  # no turn penalty
            )
            if not valid:
                continue

            nb_state = (ni, nj, nk)
            nb_node = nodes.get(nb_state)
            if nb_node is not None and nb_node.closed:
                continue
            if nb_node is None:
                nb_node = AStarNode()
                nodes[nb_state] = nb_node

            new_g = cur_node.g + ec
            if new_g < nb_node.g:
                nb_node.g = new_g
                nb_node.parent = current
                h = evaluator.heuristic_by_index(ni, nj, nk)
                if h < 0:
                    h = evaluator.heuristic(nb_pos, goal_pos)
                heapq.heappush(open_set, (new_g + h, counter, nb_state))
                counter += 1

    elapsed = __import__("time").perf_counter() - t0

    if best_state is None:
        return None, elapsed, expanded

    path = []
    cur = best_state
    while cur is not None:
        path.append(grid.node_to_pos(*cur))
        node = nodes.get(cur)
        cur = node.parent if node else None
    path.reverse()
    return path, elapsed, expanded


def bidirectional_a_star_search_3d(
    grid: Grid,
    start_node: Tuple[int, int, int],
    goal_node: Tuple[int, int, int],
    evaluator: CostEvaluator,
    target_pos: Tuple[float, float, float],
    desired_direction: Tuple[float, float, float],
) -> Tuple[Optional[List[Tuple[float, float, float]]], float, int]:
    """双向 3D A* 搜索，无 heading."""
    t0 = __import__("time").perf_counter()
    INF = float('inf')

    start_pos = grid.node_to_pos(*start_node)
    goal_pos = grid.node_to_pos(*goal_node)

    forward_nodes: Dict[Tuple[int, int, int], AStarNode] = {}
    reverse_nodes: Dict[Tuple[int, int, int], AStarNode] = {}

    # Forward init
    forward_open: List[Tuple[float, int, Tuple[int, int, int]]] = []
    # Reverse init
    reverse_open: List[Tuple[float, int, Tuple[int, int, int]]] = []
    counter = 0

    si, sj, sk = start_node
    f_state = (si, sj, sk)
    forward_nodes[f_state] = AStarNode(g=0.0)
    h_init = evaluator.heuristic_by_index(si, sj, sk)
    if h_init < 0:
        h_init = evaluator.heuristic(start_pos, goal_pos)
    heapq.heappush(forward_open, (h_init, counter, f_state))
    counter += 1

    gi, gj, gk = goal_node
    r_state = (gi, gj, gk)
    reverse_nodes[r_state] = AStarNode(g=0.0)
    h_rev_init = evaluator.heuristic_by_index_reverse(gi, gj, gk)
    if h_rev_init < 0:
        h_rev_init = evaluator.heuristic(goal_pos, start_pos)
    heapq.heappush(reverse_open, (h_rev_init, counter, r_state))
    counter += 1

    mu = INF
    best_meeting: Optional[Tuple[int, int, int]] = None
    expanded = 0

    def _min_f_3d(open_lst, nodes_dict):
        while open_lst:
            f, _, st = open_lst[0]
            nd = nodes_dict.get(st)
            if nd is None or nd.closed:
                heapq.heappop(open_lst)
                continue
            return f
        return INF

    while forward_open and reverse_open:
        min_f_fwd = _min_f_3d(forward_open, forward_nodes)
        min_f_rev = _min_f_3d(reverse_open, reverse_nodes)
        if min_f_fwd >= mu and min_f_rev >= mu:
            break

        expand_forward = min_f_fwd <= min_f_rev

        if expand_forward:
            _, _, current = heapq.heappop(forward_open)
            cur_node = forward_nodes.get(current)
            if cur_node is None or cur_node.closed:
                continue
            cur_node.closed = True
            expanded += 1

            ci, cj, ck = current
            rev_match = reverse_nodes.get(current)
            if rev_match is not None:
                total_cost = cur_node.g + rev_match.g
                if total_cost < mu:
                    mu = total_cost
                    best_meeting = current

            cur_pos = grid.node_to_pos(ci, cj, ck)
            t_cur = grid.get_node_threat(ci, cj, ck) if grid.node_threat else None

            for ni, nj, nk in _neighbors_3d(grid, ci, cj, ck):
                nb_pos = grid.node_to_pos(ni, nj, nk)
                if evaluator.threat_field.is_in_no_fly_zone(nb_pos):
                    continue
                nb_state = (ni, nj, nk)
                nb_node = forward_nodes.get(nb_state)
                if nb_node is not None and nb_node.closed:
                    continue
                if nb_node is None:
                    nb_node = AStarNode()
                    forward_nodes[nb_state] = nb_node

                t_nb = grid.get_node_threat(ni, nj, nk) if grid.node_threat else None
                ec, valid = evaluator.edge_cost(
                    cur_pos, nb_pos, target_pos, desired_direction,
                    threat_at_p1=t_cur, threat_at_p2=t_nb,
                    prev_dir=None,
                )
                if not valid:
                    continue

                new_g = cur_node.g + ec
                if new_g < nb_node.g:
                    nb_node.g = new_g
                    nb_node.parent = current
                    h = evaluator.heuristic_by_index(ni, nj, nk)
                    if h < 0:
                        h = evaluator.heuristic(nb_pos, goal_pos)
                    heapq.heappush(forward_open, (new_g + h, counter, nb_state))
                    counter += 1

                    rev_match_nb = reverse_nodes.get(nb_state)
                    if rev_match_nb is not None:
                        total_cost = new_g + rev_match_nb.g
                        if total_cost < mu:
                            mu = total_cost
                            best_meeting = nb_state
        else:
            _, _, current = heapq.heappop(reverse_open)
            cur_node = reverse_nodes.get(current)
            if cur_node is None or cur_node.closed:
                continue
            cur_node.closed = True
            expanded += 1

            ci, cj, ck = current
            fwd_match = forward_nodes.get(current)
            if fwd_match is not None:
                total_cost = fwd_match.g + cur_node.g
                if total_cost < mu:
                    mu = total_cost
                    best_meeting = current

            cur_pos = grid.node_to_pos(ci, cj, ck)
            t_cur = grid.get_node_threat(ci, cj, ck) if grid.node_threat else None

            # Reverse neighbours: 26-connected, same as forward
            for pi, pj, pk in _neighbors_3d(grid, ci, cj, ck):
                pred_pos = grid.node_to_pos(pi, pj, pk)
                if evaluator.threat_field.is_in_no_fly_zone(pred_pos):
                    continue
                pred_state = (pi, pj, pk)
                pred_node = reverse_nodes.get(pred_state)
                if pred_node is not None and pred_node.closed:
                    continue
                if pred_node is None:
                    pred_node = AStarNode()
                    reverse_nodes[pred_state] = pred_node

                t_pred = grid.get_node_threat(pi, pj, pk) if grid.node_threat else None
                ec, valid = evaluator.edge_cost(
                    pred_pos, cur_pos, target_pos, desired_direction,
                    threat_at_p1=t_pred, threat_at_p2=t_cur,
                    prev_dir=None,
                )
                if not valid:
                    continue

                new_g = cur_node.g + ec
                if new_g < pred_node.g:
                    pred_node.g = new_g
                    pred_node.parent = current
                    h_rev = evaluator.heuristic_by_index_reverse(pi, pj, pk)
                    if h_rev < 0:
                        h_rev = evaluator.heuristic(pred_pos, start_pos)
                    heapq.heappush(reverse_open, (new_g + h_rev, counter, pred_state))
                    counter += 1

                    fwd_match_pred = forward_nodes.get(pred_state)
                    if fwd_match_pred is not None:
                        total_cost = fwd_match_pred.g + new_g
                        if total_cost < mu:
                            mu = total_cost
                            best_meeting = pred_state

    elapsed = __import__("time").perf_counter() - t0

    if best_meeting is None:
        return None, elapsed, expanded

    forward_path = []
    cur = best_meeting
    while cur is not None:
        forward_path.append(grid.node_to_pos(*cur))
        node = forward_nodes.get(cur)
        cur = node.parent if node else None
    forward_path.reverse()

    reverse_path = []
    rev_node = reverse_nodes.get(best_meeting)
    while rev_node is not None and rev_node.parent is not None:
        p = rev_node.parent
        reverse_path.append(grid.node_to_pos(*p))
        rev_node = reverse_nodes.get(p)

    return forward_path + reverse_path, elapsed, expanded


def plan_single_direction(
    grid: Grid,
    start_llh: Tuple[float, float, float],
    target_llh: Tuple[float, float, float],
    sector: ApproachSector,
    target_pos_ecef: Tuple[float, float, float],
    evaluator: CostEvaluator,
    ref_lon: float,
    ref_lat: float,
    heading_count: int,
    min_turn_radius_km: float,
    initial_heading_deg: Optional[float],
    vertical_open_threat_distance_km: float,
) -> Tuple[Optional[List[Tuple[float, float, float]]], float, int]:
    """在单个方向候选下规划到给定目标点.

    Returns:
        (path, search_time_sec, expanded_nodes).
    """
    start_node = grid.pos_to_node(*start_llh)
    goal_node = grid.pos_to_node(*target_llh)

    if evaluator.config.use_heading:
        if evaluator.config.heuristic_mode == "dubins":
            h_threat_fwd = _cached_threat_exposure(grid, goal_node, evaluator.threat_field)
            h_threat_rev = _cached_threat_exposure(grid, start_node, evaluator.threat_field)
            goal_local = grid.node_to_local(*goal_node)
            start_local = grid.node_to_local(*start_node)
            evaluator._target_local = goal_local
            evaluator.set_heading_heuristic(
                h_threat_fwd, h_threat_rev, grid,
                goal_local, start_local, _heading_table(heading_count),
                min_turn_radius_km,
            )
        else:
            evaluator._target_local = grid.node_to_local(*goal_node)

        search_fn = (
            bidirectional_a_star_search
            if evaluator.config.bidirectional
            and not evaluator.config.mode2_direction_active
            else a_star_search
        )
        path, elapsed, expanded = search_fn(
            grid,
            start_node,
            goal_node,
            evaluator,
            target_pos_ecef,
            sector.direction_vec,
            heading_count,
            min_turn_radius_km,
            initial_heading_deg,
            vertical_open_threat_distance_km,
        )
    else:
        evaluator._target_local = grid.node_to_local(*goal_node)
        search_fn = (
            bidirectional_a_star_search_3d
            if evaluator.config.bidirectional
            and not evaluator.config.mode2_direction_active
            else a_star_search_3d
        )
        path, elapsed, expanded = search_fn(
            grid,
            start_node,
            goal_node,
            evaluator,
            target_pos_ecef,
            sector.direction_vec,
        )
    if path is None:
        return None, elapsed, expanded
    return path, elapsed, expanded
