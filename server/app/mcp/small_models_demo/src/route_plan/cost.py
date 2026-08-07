"""
代价评估器。

边代价 = 距离代价 + 威胁代价 + 方向偏离惩罚
"""

import math
from dataclasses import dataclass
from typing import Optional, Tuple

from .threats import ThreatField
from .core.geo import (
    EARTH_R,
    ecef_to_enu,
    vec_len,
    vec_sub,
    vec_angle,
)


@dataclass
class CostConfig:
    """代价权重配置."""

    distance_weight: float = 1.0  # 距离权重
    threat_weight: float = 100.0  # 威胁积分权重
    direction_weight: float = 50.0  # 方向偏离惩罚权重 (在目标附近生效)
    turn_weight: float = 30.0  # 转向惩罚权重 (弧度→代价)
    min_turn_radius_km: float = 0.0  # 运行时根据平台类型从 aircraft/missile_turn_radius_km 解析
    aircraft_turn_radius_km: float = 10.0  # 飞行器默认最小转弯半径, 0=不启用
    missile_turn_radius_km: float = 6.0  # 导弹默认最小转弯半径, 0=不启用
    mode2_direction_active: bool = False  # 运行时按 mode2 开关的方向约束
    bidirectional: bool = True  # 是否使用双向A*
    use_heading: bool = True  # 是否使用 heading 状态空间
    heuristic_mode: str = "ecef"  # "ecef", "fmm", or "dubins"
    direction_activation_radius_km: float = 0.0  # 运行时设为该 pair 的 approach_ref_radius_km
    edge_samples: int = 4  # 沿边威胁采样点数
    rcs_scale: float = 1.0  # 平台 RCS 缩放因子, 在 SNR 层面缩放后经 Swerling 曲线影响 Pd
    dubins_weight: float = 1.0  # Dubins 几何部分权重乘数，放大 heading 区分度


class CostEvaluator:
    """边代价评估器."""

    def __init__(
        self,
        threat_field: ThreatField,
        config: CostConfig = None,
        ref_lon: Optional[float] = None,
        ref_lat: Optional[float] = None,
    ):
        self.threat_field = threat_field
        self.config = config or CostConfig()
        self.ref_lon = ref_lon
        self.ref_lat = ref_lat
        self._fmm_dist_fwd = None  # FMM distance-to-goal (forward search)
        self._fmm_dist_rev = None  # FMM distance-to-start (reverse search)
        self._fmm_grid = None  # Grid reference for index lookup
        # Heading-aware heuristic
        self._h_threat_fwd = None  # threat exposure to goal
        self._h_threat_rev = None  # threat exposure to start
        self._goal_local = None    # goal ENU for heading angle calc
        self._start_local = None   # start ENU for reverse heading angle calc
        self._heading_count = 0
        self._min_turn_radius_km = 0.0
        self._dubins_weight = self.config.dubins_weight

    def set_fmm_heuristic(self, fmm_dist, grid):
        """Set FMM distance map for forward search (distance to goal)."""
        self._fmm_dist_fwd = fmm_dist
        self._fmm_grid = grid

    def set_fmm_heuristic_reverse(self, fmm_dist):
        """Set FMM distance map for reverse search (distance to start)."""
        self._fmm_dist_rev = fmm_dist

    def set_heading_heuristic(
        self, h_threat_fwd, h_threat_rev, grid,
        goal_local, start_local, heading_table, min_turn_radius_km,
        dubins_weight=None,
    ):
        """Set heading-aware heuristic data."""
        self._h_threat_fwd = h_threat_fwd
        self._h_threat_rev = h_threat_rev
        self._fmm_grid = grid
        self._goal_local = goal_local
        self._start_local = start_local
        self._heading_table = heading_table  # list of (di, dj)
        self._min_turn_radius_km = min_turn_radius_km
        if dubins_weight is not None:
            self._dubins_weight = dubins_weight

    def clear_fmm_heuristic(self):
        """Clear FMM distance maps."""
        self._fmm_dist_fwd = None
        self._fmm_dist_rev = None
        self._fmm_grid = None

    def _point_threat(self, pt: Tuple[float, float, float]) -> float:
        return self.threat_field.total_threat_cost(pt, rcs_scale=self.config.rcs_scale)

    def _to_local(self, pt: Tuple[float, float, float]) -> Tuple[float, float, float]:
        if self.ref_lon is None or self.ref_lat is None:
            return pt
        if vec_len(pt) > EARTH_R * 0.5:
            return ecef_to_enu(pt[0], pt[1], pt[2], self.ref_lon, self.ref_lat)
        return pt

    def edge_cost(
        self,
        p1: Tuple[float, float, float],
        p2: Tuple[float, float, float],
        target: Tuple[float, float, float],
        desired_direction: Tuple[float, float, float],
        threat_at_p1: float = None,
        threat_at_p2: float = None,
        prev_dir: Tuple[float, float, float] = None,
        dense_nfz=None,
        n1: Tuple[int, int, int] = None,
        n2: Tuple[int, int, int] = None,
        p1_local: Tuple[float, float, float] = None,
        p2_local: Tuple[float, float, float] = None,
        target_local: Tuple[float, float, float] = None,
    ) -> Tuple[float, bool]:
        """计算边的综合代价，同时检查是否穿越禁飞区.

        dense_nfz: 2x 分辨率 NFZ 网格, n1/n2: 端点网格索引.
        p1_local/p2_local/target_local: 预计算的 local 坐标, 传入后跳过 _to_local.
        """
        length = vec_len(vec_sub(p2, p1))
        cfg = self.config
        if length < 1e-9:
            return (0.0, True)

        # NFZ 检查
        dense_ok = False
        if dense_nfz is not None and n1 is not None and n2 is not None:
            di, dj, dk = n1[0] + n2[0], n1[1] + n2[1], n1[2] + n2[2]
            dn, dm, dl = len(dense_nfz), len(dense_nfz[0]), len(dense_nfz[0][0])
            if 0 <= di < dn and 0 <= dj < dm and 0 <= dk < dl:
                dense_ok = True
                if dense_nfz[di][dj][dk]:
                    return (float("inf"), False)
        if not dense_ok:
            nfz_samples = max(3, int(length / 20))
            for i in range(nfz_samples + 1):
                t = i / nfz_samples
                px = p1[0] + t * (p2[0] - p1[0])
                py = p1[1] + t * (p2[1] - p1[1])
                pz = p1[2] + t * (p2[2] - p1[2])
                if self.threat_field.is_in_no_fly_zone((px, py, pz)):
                    return (float("inf"), False)

        dist_cost = cfg.distance_weight * length

        # 威胁代价
        if cfg.edge_samples == 0:
            t1 = threat_at_p1 if threat_at_p1 is not None else self._point_threat(p1)
            t2 = threat_at_p2 if threat_at_p2 is not None else self._point_threat(p2)
            threat_cost = cfg.threat_weight * (t1 + t2) * length
        elif cfg.rcs_scale == 1.0 and threat_at_p1 is not None and threat_at_p2 is not None:
            avg_threat = (threat_at_p1 + threat_at_p2) / 2
            mx = (p1[0] + p2[0]) / 2
            my = (p1[1] + p2[1]) / 2
            mz = (p1[2] + p2[2]) / 2
            avg_threat = (avg_threat + self._point_threat((mx, my, mz))) / 2
            threat_cost = cfg.threat_weight * avg_threat * length
        else:
            total_threat = 0.0
            n = cfg.edge_samples
            for i in range(n + 1):
                t = i / n
                px = p1[0] + t * (p2[0] - p1[0])
                py = p1[1] + t * (p2[1] - p1[1])
                pz = p1[2] + t * (p2[2] - p1[2])
                total_threat += self._point_threat((px, py, pz))
            threat_cost = cfg.threat_weight * (total_threat / (n + 1)) * length

        # 3. 转向惩罚：拐弯越急、距离越长代价越大
        turn_penalty = 0.0
        if prev_dir is not None:
            pl1 = p1_local if p1_local is not None else self._to_local(p1)
            pl2 = p2_local if p2_local is not None else self._to_local(p2)
            cur_dir = vec_sub(pl2, pl1)
            cur_h = (cur_dir[0], cur_dir[1], 0.0)
            prev_h = (prev_dir[0], prev_dir[1], 0.0)
            cur_len = vec_len(cur_h)
            prev_len = vec_len(prev_h)
            if cur_len > 1e-9 and prev_len > 1e-9:
                cur_dir_n = (
                    cur_h[0] / cur_len,
                    cur_h[1] / cur_len,
                    0.0,
                )
                prev_dir_n = (
                    prev_h[0] / prev_len,
                    prev_h[1] / prev_len,
                    0.0,
                )
                angle = vec_angle(prev_dir_n, cur_dir_n)
                turn_penalty = cfg.turn_weight * angle * length

        # 4. 方向偏离惩罚 (仅在 mode2 方向约束开启时生效)
        dir_penalty = 0.0
        if cfg.mode2_direction_active:
            pl2 = p2_local if p2_local is not None else self._to_local(p2)
            tl = target_local if target_local is not None else self._to_local(target)
            dist_to_target = vec_len(vec_sub(pl2, tl))
            if dist_to_target < cfg.direction_activation_radius_km:
                to_target = vec_sub(tl, pl2)
                d = vec_len(to_target)
                if d > 1e-9:
                    approach_dir = (
                        to_target[0] / d,
                        to_target[1] / d,
                        to_target[2] / d,
                    )
                    angle = vec_angle(approach_dir, desired_direction)
                    proximity = (
                        1.0
                        - dist_to_target / cfg.direction_activation_radius_km
                    )
                    dir_penalty = cfg.direction_weight * angle * proximity

        return (dist_cost + threat_cost + turn_penalty + dir_penalty, True)

    def heuristic(
        self,
        point: Tuple[float, float, float],
        target: Tuple[float, float, float],
    ) -> float:
        """A* 启发函数：ECEF 弦长 (近似弧长)."""
        return vec_len(vec_sub(point, target))

    def heuristic_by_index(self, i: int, j: int, k: int, heading_id: int = None) -> float:
        """FMM-based or heading-aware heuristic for forward search (km-equiv to goal).

        heading_id=None: current FMM or -1 fallback.
        heading_id set: heading-aware = dw * (line + R*θ) + tw * h_threat.
        """
        if heading_id is not None and self._h_threat_fwd is not None and self._fmm_grid is not None:
            try:
                ht = self._h_threat_fwd[i][j][k]
                if ht >= float('inf'):
                    return float('inf')
            except IndexError:
                return float('inf')
            cur_local = self._fmm_grid.node_to_local(i, j, k)
            dx = self._goal_local[0] - cur_local[0]
            dy = self._goal_local[1] - cur_local[1]
            straight_km = math.hypot(dx, dy)
            if straight_km > 1e-9:
                h_dx, h_dy = self._heading_table[heading_id]
                dot = (h_dx * dx + h_dy * dy) / straight_km
                dot = max(-1.0, min(1.0, dot))
                theta = math.acos(dot)  # [0, π]
            else:
                theta = 0.0
            h_dubins = straight_km + self._min_turn_radius_km * theta
            cfg = self.config
            return cfg.distance_weight * h_dubins + cfg.threat_weight * ht

        if self._fmm_dist_fwd is not None and self._fmm_grid is not None:
            try:
                d = self._fmm_dist_fwd[i][j][k]
                if d < float('inf'):
                    return d
            except IndexError:
                pass
        return -1.0

    def heuristic_by_index_reverse(self, i: int, j: int, k: int, heading_id: int = None) -> float:
        """FMM-based or heading-aware heuristic for reverse search (km-equiv to start).

        heading_id=None: current FMM or -1 fallback.
        heading_id set: heading-aware = dw * (line + R*θ) + tw * h_threat_rev.
        """
        if heading_id is not None and self._h_threat_rev is not None and self._fmm_grid is not None:
            try:
                ht = self._h_threat_rev[i][j][k]
                if ht >= float('inf'):
                    return float('inf')
            except IndexError:
                return float('inf')
            cur_local = self._fmm_grid.node_to_local(i, j, k)
            dx = self._start_local[0] - cur_local[0]
            dy = self._start_local[1] - cur_local[1]
            straight_km = math.hypot(dx, dy)
            if straight_km > 1e-9:
                h_dx, h_dy = self._heading_table[heading_id]
                dot = (h_dx * dx + h_dy * dy) / straight_km
                dot = max(-1.0, min(1.0, dot))
                theta = math.acos(dot)
            else:
                theta = 0.0
            h_dubins = straight_km + self._min_turn_radius_km * theta
            cfg = self.config
            return cfg.distance_weight * h_dubins + cfg.threat_weight * ht

        if self._fmm_dist_rev is not None and self._fmm_grid is not None:
            try:
                d = self._fmm_dist_rev[i][j][k]
                if d < float('inf'):
                    return d
            except IndexError:
                pass
        return -1.0

    def fmm_gradient_alignment(
        self, i: int, j: int, k: int, dx: int, dy: int, heading_count: int
    ) -> float:
        """Alignment score of heading (dx,dy) with FMM negative gradient at (i,j,k).

        Returns a score where HIGHER = better aligned with direction toward goal.
        The negative gradient points toward the goal (steepest FMM descent).

        Uses the forward FMM map (distance to goal). Returns 0.0 if FMM unavailable.
        """
        fmm = self._fmm_dist_fwd
        grid = self._fmm_grid
        if fmm is None or grid is None:
            return 0.0
        nx, ny, nz = grid.nx, grid.ny, len(grid.altitudes)
        INF = float('inf')

        def _d(ci, cj, ck):
            try:
                v = fmm[ci][cj][ck]
                return v if v < INF else INF
            except IndexError:
                return INF

        center = _d(i, j, k)
        if center >= INF:
            return 0.0

        # Gradient in grid-index space (east, north)
        i_plus = _d(i + 1, j, k) if i + 1 < nx else INF
        i_minus = _d(i - 1, j, k) if i - 1 >= 0 else INF
        j_plus = _d(i, j + 1, k) if j + 1 < ny else INF
        j_minus = _d(i, j - 1, k) if j - 1 >= 0 else INF

        if i_plus < INF and i_minus < INF:
            grad_i = i_plus - i_minus
        elif i_plus < INF:
            grad_i = i_plus - center
        elif i_minus < INF:
            grad_i = center - i_minus
        else:
            grad_i = 0.0

        if j_plus < INF and j_minus < INF:
            grad_j = j_plus - j_minus
        elif j_plus < INF:
            grad_j = j_plus - center
        elif j_minus < INF:
            grad_j = center - j_minus
        else:
            grad_j = 0.0

        # Normalize gradient magnitude
        grad_len = (grad_i * grad_i + grad_j * grad_j) ** 0.5
        if grad_len < 1e-9:
            return 0.0

        # Heading direction (dx=east, dy=north) normalized
        h_len = (dx * dx + dy * dy) ** 0.5
        if h_len < 1e-9:
            return 0.0

        # Negative gradient = direction toward goal
        # Alignment = dot(heading, -gradient) / (|heading| * |gradient|)
        # Higher = more aligned with goal direction
        alignment = -(dx * grad_i + dy * grad_j) / (h_len * grad_len)
        return alignment  # -1 (away) to +1 (toward)
