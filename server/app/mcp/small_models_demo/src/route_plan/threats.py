"""
威胁场计算模块 — 基于物理检测概率 Pd。

威胁度量从纯几何转向物理模型：
- geometry_factor 返回检测概率 Pd (0~1)，基于雷达方程 + Swerling I 模型
- 威胁代价 = Pd_total × length = 预期被探测距离

支持的威胁几何体：
- 球体 (sphere):              全向预警雷达
- 圆锥体 (cone):              定向火控雷达、舰载机雷达 (含天线方向图)
- 圆柱体 (cylinder):          极端天气、禁飞区
- 椭圆柱体 (elliptic_cylinder): CAP 巡逻区域
- 椭球体 (ellipsoid):          纺锤形传感器覆盖、探测范围

坐标系：内部使用局部 ENU (East-North-Up)，单位为 km。
输入输出使用 WGS84 (lon_deg, lat_deg, alt_m)。
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .core.geo import (
    EARTH_R,
    ecef_to_enu,
    ecef_to_llh,
    llh_to_ecef,
    llh_to_local,
    radar_horizon,
    vec_angle,
    vec_dot,
    vec_len,
    vec_len_2d,
    vec_sub,
)

# ============================================================
# 检测概率物理参数
# ============================================================
PFA = 1e-6                     # 雷达虚警概率
SNR_MIN_DB = 18.0              # 最小可检测信噪比 (dB)
SNR_MIN_LINEAR = 10.0 ** (SNR_MIN_DB / 10.0)  # ≈ 63.1
DEFAULT_SIDELOBE_DB = -25.0    # 默认天线旁瓣电平 (dB)
DEFAULT_BEAMWIDTH_DEG = 3.0    # 默认 3dB 波束宽度 (°)

# 天线方向图缓存
_ANT_GAIN_CACHE: Dict[tuple, float] = {}


def _db_to_linear(db: float) -> float:
    return 10.0 ** (db / 10.0)


def _linear_to_db(x: float) -> float:
    return 10.0 * math.log10(max(x, 1e-30))


def _antenna_gain_ratio(offset_deg: float,
                        beamwidth_deg: float = DEFAULT_BEAMWIDTH_DEG,
                        sidelobe_db: float = DEFAULT_SIDELOBE_DB) -> float:
    """天线增益比 (0~1)，cos^n 主瓣模型 + 旁瓣地板。

    offset_deg=0 → ratio=1 (主瓣中心)
    offset_deg > beamwidth/2 → ratio ≈ db_to_linear(sidelobe_db) (旁瓣)
    """
    delta = abs(offset_deg)
    if delta > 180:
        delta = 360 - delta

    cache_key = (int(round(delta)), round(beamwidth_deg, 1))
    cached = _ANT_GAIN_CACHE.get(cache_key)
    if cached is not None:
        return cached

    if delta >= 90:
        ratio = _db_to_linear(sidelobe_db)
    else:
        bw_half = max(beamwidth_deg / 2.0, 0.1)
        cosv = math.cos(math.radians(min(delta, 89.9)))
        ref = math.cos(math.radians(min(bw_half, 89.9)))
        n = math.log(0.5) / math.log(max(ref, 1e-6))
        gain_lin = max(cosv, 0.0) ** n
        ratio = max(gain_lin, _db_to_linear(sidelobe_db))

    _ANT_GAIN_CACHE[cache_key] = ratio
    return ratio


def _snr_to_pd(snr_linear: float) -> float:
    """Swerling I 模型: SNR → Pd."""
    if snr_linear <= 0:
        return 0.0
    return PFA ** (1.0 / (1.0 + snr_linear))


def _pd_at_range(dist_km: float, max_range_km: float,
                 gain_ratio: float = 1.0,
                 jam_factor: float = 1.0,
                 rcs_scale: float = 1.0) -> float:
    """给定距离、最大探测距离、天线增益比、干扰因子、RCS 缩放 → Pd.

    dist_km: 当前点到雷达的距离
    max_range_km: SNR=SNR_min 处距离 (Pd≈0.8)
    gain_ratio: 天线方向图衰减比 (0~1, 1=主瓣中心)
    jam_factor: EW 干扰 SNR 缩放因子 (SINR = SNR × factor), 1.0=无干扰
    rcs_scale: RCS 缩放因子 (σ/σ_ref), SNR ∝ rcs_scale, 经 Swerling 曲线影响 Pd
    """
    if dist_km <= 0 or max_range_km <= 0:
        return 1.0 if dist_km < 1e-9 else 0.0

    # 有效探测距离 (考虑天线增益, R_eff ∝ G^(1/2) 因为 R^4 ∝ G^2)
    r_eff = max_range_km * math.sqrt(gain_ratio)
    if r_eff <= 0:
        return 0.0

    # SNR ∝ (R_eff/R)^4, R_eff 处 SNR=SNR_MIN
    snr = SNR_MIN_LINEAR * (r_eff / dist_km) ** 4

    # SINR = SNR × jamming_factor × rcs_scale (RCS 线性缩放信号功率)
    sinr = snr * jam_factor * rcs_scale

    if sinr < 1e-3:
        return 0.0

    pd = _snr_to_pd(sinr)
    return pd if pd >= 1e-6 else 0.0


# ============================================================
# 威胁几何体
# ============================================================


@dataclass
class SphereThreat:
    """球体威胁 — 全向预警雷达.

    radius 为最大探测距离 (Pd≈0.9 处)。
    geometry_factor 返回物理检测概率 Pd。
    """

    center: Tuple[float, float, float]  # (east, north, up) km
    radius: float  # km — 最大探测距离 (Pd≈0.9)
    threat_level: float  # 威胁权重 (1.0=标准预警雷达)
    id: str = ""

    def contains(self, point: Tuple[float, float, float]) -> bool:
        return vec_len(vec_sub(point, self.center)) <= self.radius

    def geometry_factor(self, point: Tuple[float, float, float],
                        jam_factor: float = 1.0,
                        rcs_scale: float = 1.0) -> float:
        """Pd(R), 基于雷达方程 R^(-4) + Swerling I."""
        dist = vec_len(vec_sub(point, self.center))
        radar_h = self.center[2]
        point_h = point[2]
        if dist > radar_horizon(radar_h, point_h):
            return 0.0
        return _pd_at_range(dist, self.radius, jam_factor=jam_factor, rcs_scale=rcs_scale)


@dataclass
class ConeThreat:
    """圆锥体威胁 — 定向火控雷达、舰载机雷达.

    顶点在 apex，沿 direction 方向展开，
    angle_deg 为半波束宽度 (3dB 点)，
    max_range_km 为沿 boresight 的最大探测距离。
    """

    apex: Tuple[float, float, float]  # 顶点 (east, north, up) km
    direction: Tuple[float, float, float]  # 主轴单位向量
    angle_deg: float  # 半波束宽度 (度)
    max_range_km: float  # boresight 最大探测距离 (km)
    threat_level: float  # 威胁权重 (1.0=标准火控雷达)
    id: str = ""

    def contains(self, point: Tuple[float, float, float]) -> bool:
        to_point = vec_sub(point, self.apex)
        dist = vec_len(to_point)
        if dist > self.max_range_km or dist < 1e-9:
            return False
        angle = vec_angle(to_point, self.direction)
        return angle <= math.radians(self.angle_deg)

    def geometry_factor(self, point: Tuple[float, float, float],
                        jam_factor: float = 1.0,
                        rcs_scale: float = 1.0) -> float:
        """Pd(R, θ), 含天线方向图衰减."""
        to_point = vec_sub(point, self.apex)
        dist = vec_len(to_point)
        if dist < 1e-9:
            return 1.0

        radar_h = self.apex[2]
        point_h = point[2]
        if dist > radar_horizon(radar_h, point_h):
            return 0.0

        angle = vec_angle(to_point, self.direction)
        offset_deg = math.degrees(angle)

        # 天线增益比: 1 (boresight) → sidelobe (大偏角)
        gain_ratio = _antenna_gain_ratio(offset_deg, self.angle_deg * 2)
        if gain_ratio <= 1e-9:
            return 0.0

        return _pd_at_range(dist, self.max_range_km, gain_ratio, jam_factor=jam_factor, rcs_scale=rcs_scale)


@dataclass
class CylinderThreat:
    """圆柱体威胁 — 极端天气、禁飞区.

    非雷达威胁，保持线性衰减模型。
    """

    center_2d: Tuple[float, float]  # (east, north) km
    radius: float  # km
    height: float  # km (高度上限)
    threat_level: float  # 0~1
    id: str = ""

    def contains(self, point: Tuple[float, float, float]) -> bool:
        h_dist = vec_len_2d(
            (point[0] - self.center_2d[0], point[1] - self.center_2d[1])
        )
        return h_dist <= self.radius and point[2] <= self.height

    def geometry_factor(self, point: Tuple[float, float, float]) -> float:
        if point[2] > self.height:
            return 0.0
        h_dist = vec_len_2d(
            (point[0] - self.center_2d[0], point[1] - self.center_2d[1])
        )
        if h_dist >= self.radius:
            return 0.0
        return (1.0 - h_dist / self.radius) * (1.0 - point[2] / self.height)


@dataclass
class EllipticCylinderThreat:
    """椭圆柱体威胁 — CAP 巡逻区域.

    非雷达威胁，保持线性衰减模型。
    """

    center_2d: Tuple[float, float]  # (east, north) km — 椭圆中心
    semi_major: float  # 半长轴 (km), 沿巡逻方向
    semi_minor: float  # 半短轴 (km), 垂直于巡逻方向
    azimuth_deg: float  # 长轴方位角 (度, 北偏东)
    height: float  # 高度上限 (km)
    threat_level: float  # 0~1
    id: str = ""

    def contains(self, point: Tuple[float, float, float]) -> bool:
        return self.geometry_factor(point) > 1e-9

    def geometry_factor(self, point: Tuple[float, float, float]) -> float:
        if point[2] > self.height:
            return 0.0
        dx, dy = point[0] - self.center_2d[0], point[1] - self.center_2d[1]
        az = math.radians(self.azimuth_deg)
        cos_a, sin_a = math.cos(az), math.sin(az)
        xr = dx * cos_a + dy * sin_a
        yr = -dx * sin_a + dy * cos_a
        if self.semi_major <= 0 or self.semi_minor <= 0:
            return 0.0
        q = (xr / self.semi_major) ** 2 + (yr / self.semi_minor) ** 2
        if q >= 1.0:
            return 0.0
        radial_factor = 1.0 - math.sqrt(q)
        height_factor = 1.0 - point[2] / self.height
        return radial_factor * height_factor


@dataclass
class EllipsoidThreat:
    """椭球体威胁 — 纺锤形传感器/探测范围.

    semi_c 为主轴最大探测距离 (Pd≈0.9), semi_a/semi_b 为横向有效半轴。
    几何因子返回 Pd。
    """

    center: Tuple[float, float, float]  # (east, north, up) km
    direction: Tuple[float, float, float]  # 长轴单位向量
    semi_a: float  # 短半轴 1 (km), 垂直于 direction
    semi_b: float  # 短半轴 2 (km), 垂直于 direction
    semi_c: float  # 长半轴 (km), 沿 direction — 最大探测距离
    threat_level: float  # 威胁权重
    id: str = ""

    def __post_init__(self):
        if self.semi_a <= 0 or self.semi_b <= 0 or self.semi_c <= 0:
            raise ValueError("ellipsoid semi-axes must be positive")
        self._axis_a: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._axis_b: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._compute_axes()

    def _compute_axes(self):
        dx, dy, dz = self.direction
        if abs(dz) < 0.9:
            ref = (0.0, 0.0, 1.0)
        else:
            ref = (1.0, 0.0, 0.0)
        ax = ref[1] * dz - ref[2] * dy
        ay = ref[2] * dx - ref[0] * dz
        az = ref[0] * dy - ref[1] * dx
        length = math.hypot(ax, math.hypot(ay, az))
        self._axis_a = (ax / length, ay / length, az / length)
        bx = dy * self._axis_a[2] - dz * self._axis_a[1]
        by = dz * self._axis_a[0] - dx * self._axis_a[2]
        bz = dx * self._axis_a[1] - dy * self._axis_a[0]
        length_b = math.hypot(bx, math.hypot(by, bz))
        self._axis_b = (bx / length_b, by / length_b, bz / length_b)

    def _ellipsoid_q(self, point: Tuple[float, float, float]) -> float:
        vx, vy, vz = point[0] - self.center[0], point[1] - self.center[1], point[2] - self.center[2]
        vc = vx * self.direction[0] + vy * self.direction[1] + vz * self.direction[2]
        va = vx * self._axis_a[0] + vy * self._axis_a[1] + vz * self._axis_a[2]
        vb = vx * self._axis_b[0] + vy * self._axis_b[1] + vz * self._axis_b[2]
        return (va / self.semi_a) ** 2 + (vb / self.semi_b) ** 2 + (vc / self.semi_c) ** 2

    def contains(self, point: Tuple[float, float, float]) -> bool:
        return self._ellipsoid_q(point) <= 1.0

    def geometry_factor(self, point: Tuple[float, float, float],
                        jam_factor: float = 1.0,
                        rcs_scale: float = 1.0) -> float:
        """Pd, 基于椭球归一化距离映射到雷达方程."""
        dist = vec_len(vec_sub(point, self.center))
        max_semi = max(self.semi_a, self.semi_b, self.semi_c)
        if dist >= max_semi:
            return 0.0
        radar_h = self.center[2]
        point_h = point[2]
        if dist > radar_horizon(radar_h, point_h):
            return 0.0
        q = self._ellipsoid_q(point)
        if q >= 1.0:
            return 0.0
        # 用归一化距离 q 映射到等效距离: R_eff/R_max ≈ 1-sqrt(q)
        r_ratio = 1.0 - math.sqrt(q)
        if r_ratio <= 0:
            return 0.0
        return _pd_at_range(dist, max_semi * r_ratio, jam_factor=jam_factor, rcs_scale=rcs_scale)


# ============================================================
# 威胁场管理器
# ============================================================


@dataclass
class ThreatField:
    """管理所有威胁体，提供统一的点代价查询."""

    spheres: List[SphereThreat] = field(default_factory=list)
    cones: List[ConeThreat] = field(default_factory=list)
    cylinders: List[CylinderThreat] = field(default_factory=list)
    elliptic_cylinders: List[EllipticCylinderThreat] = field(default_factory=list)
    ellipsoids: List[EllipsoidThreat] = field(default_factory=list)
    no_fly_zones: List[CylinderThreat] = field(default_factory=list)
    nfz_ellipsoids: List[EllipsoidThreat] = field(default_factory=list)
    ref_lon: Optional[float] = None
    ref_lat: Optional[float] = None
    jamming_fields: dict = field(default_factory=dict)  # {threat_id: JammingField}
    jamming_metadata: dict = field(default_factory=dict)  # {radars, jammers, strength_matrix, ...}

    def set_jamming(self, fields: dict, metadata: dict = None) -> None:
        """注入 EW 干扰场及元数据, key=threat.id."""
        self.jamming_fields = fields
        if metadata is not None:
            self.jamming_metadata = metadata

    def _local_to_llh(self, local_point: Tuple[float, float, float]
                      ) -> Tuple[float, float, float]:
        """ENU (east_km, north_km, up_km) → (lon, lat, alt_m)."""
        if self.ref_lon is None or self.ref_lat is None:
            return local_point
        from .core.geo import local_to_llh
        return local_to_llh(local_point[0], local_point[1], local_point[2],
                            self.ref_lon, self.ref_lat)

    def _get_jam_factor(self, threat_id: str,
                        local_point: Tuple[float, float, float]) -> float:
        """查询该威胁对应的 EW 场, 返回 SNR 缩放因子."""
        if not self.jamming_fields:
            return 1.0
        jf = self.jamming_fields.get(threat_id)
        if jf is None:
            return 1.0
        lon, lat, alt_m = self._local_to_llh(local_point)
        alt_km = alt_m / 1000.0
        return jf.interpolate_factor(lon, lat, alt_km)

    def _point_to_local(
        self, point: Tuple[float, float, float]
    ) -> Tuple[float, float, float]:
        """接受局部 ENU 或 ECEF，统一转换为局部 ENU."""
        if self.ref_lon is None or self.ref_lat is None:
            return point
        if vec_len(point) > EARTH_R * 0.5:
            # ECEF → LLH → ENU: 避免 ecef_to_enu 的平面近似曲率误差
            llh = ecef_to_llh(point[0], point[1], point[2])
            return llh_to_local(llh[0], llh[1], llh[2], self.ref_lon, self.ref_lat)
        return point

    def is_in_no_fly_zone(self, point: Tuple[float, float, float]) -> bool:
        local_point = self._point_to_local(point)
        if any(nfz.contains(local_point) for nfz in self.no_fly_zones):
            return True
        return any(nfz.contains(local_point) for nfz in self.nfz_ellipsoids)

    def min_distance_to_any_threat(self, point: Tuple[float, float, float]) -> float:
        """返回点到任意软威胁几何体边界的最小近似距离(km)."""
        local_point = self._point_to_local(point)
        distances = []

        for s in self.spheres:
            distances.append(max(0.0, vec_len(vec_sub(local_point, s.center)) - s.radius))

        for c in self.cones:
            to_point = vec_sub(local_point, c.apex)
            axial = vec_dot(to_point, c.direction)
            radial_sq = max(0.0, vec_len(to_point) ** 2 - axial ** 2)
            radial = math.sqrt(radial_sq)
            cone_radius = max(0.0, axial * math.tan(math.radians(c.angle_deg)))
            radial_gap = max(0.0, radial - cone_radius)
            axial_gap = 0.0
            if axial < 0.0:
                axial_gap = -axial
            elif axial > c.max_range_km:
                axial_gap = axial - c.max_range_km
            distances.append(math.hypot(radial_gap, axial_gap))

        for cy in self.cylinders:
            dx = local_point[0] - cy.center_2d[0]
            dy = local_point[1] - cy.center_2d[1]
            radial_gap = max(0.0, math.hypot(dx, dy) - cy.radius)
            vertical_gap = 0.0
            if local_point[2] < 0.0:
                vertical_gap = -local_point[2]
            elif local_point[2] > cy.height:
                vertical_gap = local_point[2] - cy.height
            distances.append(math.hypot(radial_gap, vertical_gap))

        for ec in self.elliptic_cylinders:
            dx, dy = local_point[0] - ec.center_2d[0], local_point[1] - ec.center_2d[1]
            az = math.radians(ec.azimuth_deg)
            cos_a, sin_a = math.cos(az), math.sin(az)
            xr = dx * cos_a + dy * sin_a
            yr = -dx * sin_a + dy * cos_a
            q = 0.0
            if ec.semi_major > 0.0 and ec.semi_minor > 0.0:
                q = (xr / ec.semi_major) ** 2 + (yr / ec.semi_minor) ** 2
            if q <= 1.0:
                radial_gap = 0.0
            else:
                scale = 1.0 / math.sqrt(q)
                bx = xr * scale
                by = yr * scale
                radial_gap = math.hypot(xr - bx, yr - by)
            vertical_gap = 0.0
            if local_point[2] < 0.0:
                vertical_gap = -local_point[2]
            elif local_point[2] > ec.height:
                vertical_gap = local_point[2] - ec.height
            distances.append(math.hypot(radial_gap, vertical_gap))

        for el in self.ellipsoids:
            vx = local_point[0] - el.center[0]
            vy = local_point[1] - el.center[1]
            vz = local_point[2] - el.center[2]
            dist = math.hypot(vx, math.hypot(vy, vz))
            q = el._ellipsoid_q(local_point)
            if q <= 1.0:
                distances.append(0.0)
            elif q > 0:
                distances.append(dist * (1.0 - 1.0 / math.sqrt(q)))

        if not distances:
            return float("inf")
        return min(distances)

    def total_threat_cost(self, point: Tuple[float, float, float],
                          rcs_scale: float = 1.0) -> float:
        """计算综合检测概率: Pd_total = 1 - ∏(1 - threat_level_i × Pd_i).

        每个雷达威胁查找其对应 id 的 EW 干扰场,
        rcs_scale 在 SNR 层面缩放信号功率，经 Swerling 曲线影响 Pd。
        非雷达威胁不受干扰/RCS 影响。
        """
        local_point = self._point_to_local(point)

        pd_total = 0.0
        for s in self.spheres:
            jam_f = self._get_jam_factor(s.id, local_point)
            pd_i = s.geometry_factor(local_point, jam_factor=jam_f, rcs_scale=rcs_scale)
            if pd_i > 0:
                pd_total = 1.0 - (1.0 - pd_total) * (1.0 - s.threat_level * pd_i)
        for c in self.cones:
            jam_f = self._get_jam_factor(c.id, local_point)
            pd_i = c.geometry_factor(local_point, jam_factor=jam_f, rcs_scale=rcs_scale)
            if pd_i > 0:
                pd_total = 1.0 - (1.0 - pd_total) * (1.0 - c.threat_level * pd_i)
        for el in self.ellipsoids:
            jam_f = self._get_jam_factor(el.id, local_point)
            pd_i = el.geometry_factor(local_point, jam_factor=jam_f, rcs_scale=rcs_scale)
            if pd_i > 0:
                pd_total = 1.0 - (1.0 - pd_total) * (1.0 - el.threat_level * pd_i)
        # 非雷达威胁不受干扰/RCS 影响
        for cy in self.cylinders:
            pd_total += cy.threat_level * cy.geometry_factor(local_point)
        for ec in self.elliptic_cylinders:
            pd_total += ec.threat_level * ec.geometry_factor(local_point)
        return min(pd_total, 1.0)

    def point_threat_hits(self, point: Tuple[float, float, float],
                          rcs_scale: float = 1.0) -> List[dict]:
        """返回点处命中的威胁明细."""
        local_point = self._point_to_local(point)
        hits = []
        for s in self.spheres:
            jam_f = self._get_jam_factor(s.id, local_point)
            factor = s.geometry_factor(local_point, jam_factor=jam_f, rcs_scale=rcs_scale)
            if factor > 0:
                hits.append(
                    {
                        "id": s.id or "sphere",
                        "type": "sphere",
                        "value": s.threat_level * factor,
                    }
                )
        for c in self.cones:
            jam_f = self._get_jam_factor(c.id, local_point)
            factor = c.geometry_factor(local_point, jam_factor=jam_f, rcs_scale=rcs_scale)
            if factor > 0:
                hits.append(
                    {
                        "id": c.id or "cone",
                        "type": "cone",
                        "value": c.threat_level * factor,
                    }
                )
        for cy in self.cylinders:
            factor = cy.geometry_factor(local_point)
            if factor > 0:
                hits.append(
                    {
                        "id": cy.id or "cylinder",
                        "type": "cylinder",
                        "value": cy.threat_level * factor,
                    }
                )
        for ec in self.elliptic_cylinders:
            factor = ec.geometry_factor(local_point)
            if factor > 0:
                hits.append(
                    {
                        "id": ec.id or "elliptic_cylinder",
                        "type": "elliptic_cylinder",
                        "value": ec.threat_level * factor,
                    }
                )
        for el in self.ellipsoids:
            jam_f = self._get_jam_factor(el.id, local_point)
            factor = el.geometry_factor(local_point, jam_factor=jam_f, rcs_scale=rcs_scale)
            if factor > 0:
                hits.append(
                    {
                        "id": el.id or "ellipsoid",
                        "type": "ellipsoid",
                        "value": el.threat_level * factor,
                    }
                )
        hits.sort(key=lambda item: (-item["value"], item["id"]))
        return hits

    def edge_threat_hits(
        self,
        p1: Tuple[float, float, float],
        p2: Tuple[float, float, float],
        num_samples: int = 8,
        rcs_scale: float = 1.0,
    ) -> List[dict]:
        """返回一条边沿线命中的威胁汇总."""
        accum = {}
        max_value = {}
        if num_samples == 0:
            sample_pts = [p1, p2]
            denom = 2
        else:
            sample_pts = []
            for i in range(num_samples + 1):
                t = i / num_samples
                sample_pts.append((
                    p1[0] + t * (p2[0] - p1[0]),
                    p1[1] + t * (p2[1] - p1[1]),
                    p1[2] + t * (p2[2] - p1[2]),
                ))
            denom = num_samples + 1
        for pt in sample_pts:
            for hit in self.point_threat_hits(pt, rcs_scale=rcs_scale):
                key = (hit["id"], hit["type"])
                accum[key] = accum.get(key, 0.0) + hit["value"]
                max_value[key] = max(max_value.get(key, 0.0), hit["value"])
        result = []
        for (threat_id, threat_type), value_sum in accum.items():
            result.append(
                {
                    "id": threat_id,
                    "type": threat_type,
                    "avg_value": value_sum / denom,
                    "max_value": max_value[(threat_id, threat_type)],
                }
            )
        result.sort(key=lambda item: (-item["max_value"], item["id"]))
        return result

    def edge_threat_cost(
        self,
        p1: Tuple[float, float, float],
        p2: Tuple[float, float, float],
        num_samples: int = 8,
        rcs_scale: float = 1.0,
    ) -> float:
        """沿边采样，积分威胁代价.

        返回: 积分后的威胁暴露值 (类似于 RCS 积分)
        """
        length = vec_len(vec_sub(p2, p1))
        if length < 1e-9:
            return self.total_threat_cost(p1, rcs_scale=rcs_scale) * 0.0

        if num_samples == 0:
            return (self.total_threat_cost(p1, rcs_scale=rcs_scale)
                    + self.total_threat_cost(p2, rcs_scale=rcs_scale)) * length

        total = 0.0
        for i in range(num_samples + 1):
            t = i / num_samples
            px = p1[0] + t * (p2[0] - p1[0])
            py = p1[1] + t * (p2[1] - p1[1])
            pz = p1[2] + t * (p2[2] - p1[2])
            total += self.total_threat_cost((px, py, pz), rcs_scale=rcs_scale)

        avg_threat = total / (num_samples + 1)
        return avg_threat * length
