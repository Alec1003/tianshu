"""坐标转换工具 — WGS84 / ECEF / ENU 互相转换及向量运算。"""

import math
from typing import Tuple

A = 6378.137  # 长半轴 (km)

B = 6356.752  # 短半轴 (km)

E2 = 1 - (B**2) / (A**2)  # 第一偏心率平方

EARTH_R = 6371.0  # 平均半径 (km)

KM_PER_DEG = 111.32

def ecef_to_llh(x: float, y: float, z: float) -> Tuple[float, float, float]:
    """ECEF (km) → WGS84 (lon_deg, lat_deg, alt_m)."""
    lon = math.degrees(math.atan2(y, x))
    p = math.sqrt(x**2 + y**2)
    lat = math.atan2(z, p * (1 - E2))
    # 迭代求精
    for _ in range(5):
        N = A / math.sqrt(1 - E2 * math.sin(lat) ** 2)
        h = p / math.cos(lat) - N
        lat = math.atan2(z, p * (1 - E2 * N / (N + h)))
    N = A / math.sqrt(1 - E2 * math.sin(lat) ** 2)
    h = p / math.cos(lat) - N
    return (lon, math.degrees(lat), h * 1000.0)

def radar_horizon(radar_z_km: float, point_z_km: float) -> float:
    """雷达视距 (km). 超此距离目标被地球曲率遮挡."""
    if radar_z_km < 0:
        radar_z_km = 0
    if point_z_km < 0:
        point_z_km = 0
    return 112.88 * (math.sqrt(radar_z_km) + math.sqrt(point_z_km))

def llh_to_ecef(
    lon_deg: float, lat_deg: float, alt_m: float
) -> Tuple[float, float, float]:
    """WGS84 → ECEF 地心地固坐标 (km)."""
    lon = math.radians(lon_deg)
    lat = math.radians(lat_deg)
    alt_km = alt_m / 1000.0
    N = A / math.sqrt(1 - E2 * math.sin(lat) ** 2)
    x = (N + alt_km) * math.cos(lat) * math.cos(lon)
    y = (N + alt_km) * math.cos(lat) * math.sin(lon)
    z = (N * (1 - E2) + alt_km) * math.sin(lat)
    return (x, y, z)

def ecef_to_enu(
    x: float,
    y: float,
    z: float,
    ref_lon: float,
    ref_lat: float,
    ref_ecef: Tuple[float, float, float] = None,
) -> Tuple[float, float, float]:
    """ECEF (km) → 局部 ENU (km)."""
    if ref_ecef is None:
        ref_ecef = llh_to_ecef(ref_lon, ref_lat, 0)
    rx, ry, rz = ref_ecef
    dx = x - rx
    dy = y - ry
    dz = z - rz

    rlon = math.radians(ref_lon)
    rlat = math.radians(ref_lat)
    sin_lon, cos_lon = math.sin(rlon), math.cos(rlon)
    sin_lat, cos_lat = math.sin(rlat), math.cos(rlat)

    east = -sin_lon * dx + cos_lon * dy
    north = -sin_lat * cos_lon * dx - sin_lat * sin_lon * dy + cos_lat * dz
    up = cos_lat * cos_lon * dx + cos_lat * sin_lon * dy + sin_lat * dz
    return (east, north, up)

def llh_to_local(
    lon: float, lat: float, alt_m: float, ref_lon: float, ref_lat: float
) -> Tuple[float, float, float]:
    """WGS84 → 局部 Cartesian (east_km, north_km, up_km)."""
    cos_lat = math.cos(math.radians((lat + ref_lat) / 2))
    east = (lon - ref_lon) * KM_PER_DEG * cos_lat
    north = (lat - ref_lat) * KM_PER_DEG
    up = alt_m / 1000.0
    return east, north, up

def local_to_llh(
    east: float, north: float, up: float, ref_lon: float, ref_lat: float
) -> Tuple[float, float, float]:
    """局部 Cartesian → WGS84."""
    cos_lat = math.cos(math.radians(ref_lat))
    lon = ref_lon + east / (KM_PER_DEG * cos_lat)
    lat = ref_lat + north / KM_PER_DEG
    alt_m = up * 1000.0
    return lon, lat, alt_m

def vec_len(v: Tuple[float, float, float]) -> float:
    return math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)

def vec_len_2d(v: Tuple[float, float, float]) -> float:
    return math.sqrt(v[0] ** 2 + v[1] ** 2)

def vec_sub(
    a: Tuple[float, float, float], b: Tuple[float, float, float]
) -> Tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

def vec_dot(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def circumcircle_radius(
    a: Tuple[float, float, float],
    b: Tuple[float, float, float],
    c: Tuple[float, float, float],
) -> float:
    """三点外接圆半径 (km)，仅考虑水平面 (x, y).

    共线时分两种情况:
      - 直行 (ab·bc > 0): 返回 inf，无转弯约束
      - 折返 (ab·bc < 0): 返回 0，只有转弯半径 0 的平台可执行
    """
    abx, aby = b[0] - a[0], b[1] - a[1]
    bcx, bcy = c[0] - b[0], c[1] - b[1]
    cross_2d = abx * bcy - aby * bcx
    if abs(cross_2d) < 1e-9:
        dot_2d = abx * bcx + aby * bcy
        if dot_2d < 0:
            return 0.0
        return float("inf")
    ab_len = math.hypot(abx, aby)
    bc_len = math.hypot(bcx, bcy)
    acx, acy = c[0] - a[0], c[1] - a[1]
    ac_len = math.hypot(acx, acy)
    return (ab_len * bc_len * ac_len) / (2.0 * abs(cross_2d))

def vec_angle(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    """两向量夹角 (弧度)."""
    la = vec_len(a)
    lb = vec_len(b)
    if la < 1e-12 or lb < 1e-12:
        return 0.0
    cos = vec_dot(a, b) / (la * lb)
    return math.acos(max(-1.0, min(1.0, cos)))

def azimuth_elevation_to_vector(
    azimuth_deg: float, elevation_deg: float
) -> Tuple[float, float, float]:
    """方位角+俯仰角 → 单位方向向量 (east, north, up).

    azimuth:   0=北, 90=东, 180=南, 270=西
    elevation: 0=水平, +向上, -向下
    """
    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)
    cos_el = math.cos(el)
    return (
        math.sin(az) * cos_el,  # east
        math.cos(az) * cos_el,  # north
        math.sin(el),  # up
    )
