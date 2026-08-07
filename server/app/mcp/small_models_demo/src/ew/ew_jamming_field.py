#!/usr/bin/env python3
"""
电子战 SNR 缩放因子场计算。

对指定空间区域离散化，预计算每个点的 SNR 缩放因子和 α·G 乘积:
    factor = 1 / (1 + α × G_ratio(Δθ))
    ag     = α × G_ratio(Δθ)

其中:
    α  = J₀/N₀ = strength × (R_ref / Rj)²
    Rj = 干扰机到雷达的实际距离 (自动计算)
    strength = 用户给定, 干扰机在参考距离 R_ref=100km 处的 J/N₀

    G_ratio = 雷达天线在干扰机方向的归一化增益 (0~1)
    Δθ = 雷达主瓣指向(点P方向) 与 干扰机方向的夹角

    用户只需提供 strength (与位置无关), 距离衰减由 EW 模块根据位置自动计算。

多干扰机时 ag 直接求和:
    ag_total = ag₁ + ag₂ + ...
    factor_total = 1 / (1 + ag_total)

Usage:
    python ew_jamming_field.py
    python ew_jamming_field.py -i input.json -o output.json
"""

from __future__ import annotations

import json
import math
import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

# ==============================================
# 物理常数
# ==============================================
R_EARTH = 6371000.0
KM_PER_DEG = 111.32

# ==============================================
# 默认参数
# ==============================================
DEFAULT_BEAMWIDTH_DEG = 3.0
DEFAULT_SIDELOBE_DB = -25.0
REF_DISTANCE_KM = 100.0    # strength 的参考距离: alpha = strength × (REF/Rj)²


# ==============================================
# 基础数学工具
# ==============================================
def db_to_linear(db: float) -> float:
    return 10.0 ** (db / 10.0)


def linear_to_db(x: float) -> float:
    return 10.0 * math.log10(max(x, 1e-30))


# ==============================================
# 地理计算 (WGS84)
# ==============================================
def haversine_m(lon1: float, lat1: float,
                lon2: float, lat2: float) -> float:
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R_EARTH * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bearing_deg(lon1: float, lat1: float,
                lon2: float, lat2: float) -> float:
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(math.radians(lat2))
    y = (math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
         - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(dlon))
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def elevation_deg(lon1: float, lat1: float, alt1_m: float,
                  lon2: float, lat2: float, alt2_m: float) -> float:
    h_dist = haversine_m(lon1, lat1, lon2, lat2)
    if h_dist < 1.0:
        return 90.0 if alt2_m > alt1_m else -90.0
    return math.degrees(math.atan2(alt2_m - alt1_m, h_dist))


def slant_range_m(lon1: float, lat1: float, alt1_m: float,
                  lon2: float, lat2: float, alt2_m: float) -> float:
    h = haversine_m(lon1, lat1, lon2, lat2)
    v = abs(alt1_m - alt2_m)
    return math.sqrt(h * h + v * v)


# ==============================================
# 3D 角间距
# ==============================================
def angular_separation_deg(az1: float, el1: float,
                           az2: float, el2: float) -> float:
    """两个方向 (az, el 度) 在单位球面上的大圆角距 (°)."""
    a1r, e1r = math.radians(az1), math.radians(el1)
    a2r, e2r = math.radians(az2), math.radians(el2)
    cos_sep = (math.sin(e1r) * math.sin(e2r)
               + math.cos(e1r) * math.cos(e2r) * math.cos(a1r - a2r))
    cos_sep = max(-1.0, min(1.0, cos_sep))
    return math.degrees(math.acos(cos_sep))


# ==============================================
# 天线方向图
# ==============================================
_ANT_GAIN_CACHE: dict[tuple, float] = {}


def antenna_gain_ratio(offset_deg: float,
                       beamwidth_deg: float = DEFAULT_BEAMWIDTH_DEG,
                       sidelobe_db: float = DEFAULT_SIDELOBE_DB) -> float:
    """归一化天线增益 (0~1), cos^n 主瓣 + 旁瓣地板."""
    delta = abs(offset_deg)
    if delta > 180:
        delta = 360 - delta

    cache_key = (int(round(delta)), round(beamwidth_deg, 1))
    cached = _ANT_GAIN_CACHE.get(cache_key)
    if cached is not None:
        return cached

    if delta >= 90:
        ratio = db_to_linear(sidelobe_db)
    else:
        bw_half = max(beamwidth_deg / 2.0, 0.1)
        cosv = math.cos(math.radians(min(delta, 89.9)))
        ref = math.cos(math.radians(min(bw_half, 89.9)))
        n = math.log(0.5) / math.log(max(ref, 1e-6))
        gain_lin = max(cosv, 0.0) ** n
        ratio = max(gain_lin, db_to_linear(sidelobe_db))

    _ANT_GAIN_CACHE[cache_key] = ratio
    return ratio


# ==============================================
# SNR 缩放因子场
# ==============================================
@dataclass
class JammingField:
    """单部干扰机的 SNR 缩放因子场.

    每个网格点存储两个值:
      ag_products = α × G_ratio(Δθ)     ← 多部干扰机叠加时直接求和
      factors     = 1 / (1 + ag)         ← 当前单部干扰下的缩放因子

    SINR = SNR × factor, factor 范围 0~1:
      1.0 → 无干扰影响 (旁瓣方向)
      →0 → 强干扰, Pd 被压制 (主瓣方向)

    多干扰机:
      ag_total = field1.ag_products + field2.ag_products + ...
      factor_total = 1 / (1 + ag_total)
    """

    lon_grid: np.ndarray       # (nlon,) 经度
    lat_grid: np.ndarray       # (nlat,) 纬度
    alt_grid: np.ndarray       # (nalt,) 高度 (km)
    factors: np.ndarray        # (nlon, nlat, nalt) 当前 SNR 缩放因子
    ag_products: np.ndarray    # (nlon, nlat, nalt) α×G_ratio, 多机叠加用

    radar_id: str = ""         # 雷达唯一标识, 对应 threat.id
    radar_position: tuple = field(default=(0, 0, 0))
    jammer_position: tuple = field(default=(0, 0, 0))
    strength: float = 0.0

    def _grid_index(self, lon: float, lat: float, alt_km: float) -> tuple:
        """LLH → 网格索引."""
        ilon = int(round((lon - self.lon_grid[0])
                         / (self.lon_grid[1] - self.lon_grid[0])))
        ilat = int(round((lat - self.lat_grid[0])
                         / (self.lat_grid[1] - self.lat_grid[0])))
        ialt = int(round((alt_km - self.alt_grid[0])
                         / (self.alt_grid[1] - self.alt_grid[0])))
        ilon = max(0, min(len(self.lon_grid) - 1, ilon))
        ilat = max(0, min(len(self.lat_grid) - 1, ilat))
        ialt = max(0, min(len(self.alt_grid) - 1, ialt))
        return ilon, ilat, ialt

    def lookup(self, lon: float, lat: float, alt_km: float) -> float:
        """查询当前干扰机下的 SNR 缩放因子."""
        ilon, ilat, ialt = self._grid_index(lon, lat, alt_km)
        return float(self.factors[ilon, ilat, ialt])

    def lookup_ag(self, lon: float, lat: float, alt_km: float) -> float:
        """查询 α×G_ratio 乘积, 用于多机叠加."""
        ilon, ilat, ialt = self._grid_index(lon, lat, alt_km)
        return float(self.ag_products[ilon, ilat, ialt])

    def in_bounds(self, lon: float, lat: float, alt_km: float) -> bool:
        """点是否在网格范围内."""
        return (self.lon_grid[0] <= lon <= self.lon_grid[-1]
                and self.lat_grid[0] <= lat <= self.lat_grid[-1]
                and self.alt_grid[0] <= alt_km <= self.alt_grid[-1])

    def _frac_index(self, arr: np.ndarray, val: float) -> tuple:
        """返回 arr 中 val 的分数索引: (idx_lo, frac).
        frac: 0→idx_lo, 1→idx_lo+1."""
        step = arr[1] - arr[0]
        f = (val - arr[0]) / step
        idx = int(f)
        idx = max(0, min(len(arr) - 2, idx))
        frac = f - idx
        frac = max(0.0, min(1.0, frac))
        return idx, frac

    def interpolate_ag(self, lon: float, lat: float, alt_km: float) -> float:
        """三线性插值查询 α×G_ratio, 超出网格钳位到边界."""
        lon_c = max(self.lon_grid[0], min(self.lon_grid[-1], lon))
        lat_c = max(self.lat_grid[0], min(self.lat_grid[-1], lat))
        alt_c = max(self.alt_grid[0], min(self.alt_grid[-1], alt_km))

        ilon, flon = self._frac_index(self.lon_grid, lon_c)
        ilat, flat = self._frac_index(self.lat_grid, lat_c)
        ialt, falt = self._frac_index(self.alt_grid, alt_c)

        # 三线性插值
        c000 = self.ag_products[ilon,     ilat,     ialt]
        c100 = self.ag_products[ilon + 1, ilat,     ialt]
        c010 = self.ag_products[ilon,     ilat + 1, ialt]
        c110 = self.ag_products[ilon + 1, ilat + 1, ialt]
        c001 = self.ag_products[ilon,     ilat,     ialt + 1]
        c101 = self.ag_products[ilon + 1, ilat,     ialt + 1]
        c011 = self.ag_products[ilon,     ilat + 1, ialt + 1]
        c111 = self.ag_products[ilon + 1, ilat + 1, ialt + 1]

        c00 = c000 * (1 - flon) + c100 * flon
        c01 = c001 * (1 - flon) + c101 * flon
        c10 = c010 * (1 - flon) + c110 * flon
        c11 = c011 * (1 - flon) + c111 * flon

        c0 = c00 * (1 - flat) + c10 * flat
        c1 = c01 * (1 - flat) + c11 * flat

        return float(c0 * (1 - falt) + c1 * falt)

    def interpolate_factor(self, lon: float, lat: float, alt_km: float) -> float:
        """三线性插值查询 SNR 缩放因子, 超出网格钳位到边界."""
        ag = self.interpolate_ag(lon, lat, alt_km)
        return 1.0 / (1.0 + ag)

    def to_dict(self) -> dict:
        return {
            "radar_id": self.radar_id,
            "lon_grid": self.lon_grid.tolist(),
            "lat_grid": self.lat_grid.tolist(),
            "alt_grid_km": self.alt_grid.tolist(),
            "factors": self.factors.tolist(),
            "ag_products": self.ag_products.tolist(),
            "radar_position": list(self.radar_position),
            "jammer_position": list(self.jammer_position),
            "strength": self.strength,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "JammingField":
        return cls(
            radar_id=d.get("radar_id", ""),
            lon_grid=np.array(d["lon_grid"]),
            lat_grid=np.array(d["lat_grid"]),
            alt_grid=np.array(d["alt_grid_km"]),
            factors=np.array(d["factors"]),
            ag_products=np.array(d.get("ag_products", d["factors"])),
            radar_position=tuple(d["radar_position"]),
            jammer_position=tuple(d["jammer_position"]),
            strength=d.get("strength", d.get("alpha", 0.0)),
        )

    def save_pkl(self, path: str) -> None:
        """保存为 pickle 文件, 可通过 load_jamming_field() 加载并查询."""
        import pickle
        data = self.to_dict()
        with open(path, "wb") as f:
            pickle.dump(data, f)

    @classmethod
    def load_pkl(cls, path: str) -> "JammingField":
        """从 pickle 文件加载."""
        import pickle
        with open(path, "rb") as f:
            data = pickle.load(f)
        return cls.from_dict(data)


def save_fields_pkl(
    fields: list[JammingField],
    path: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """保存多个雷达的干扰场为 pickle dict.

    格式: {"fields": {radar_id: field_dict, ...}, "metadata": {...}}
    加载: lookup = load_ew_lookup('ew_fields.pkl')
          factor = lookup['R1'].lookup(lon, lat, alt_km)
    画图: plot_jamming_from_pkl('ew_fields.pkl')
    """
    import pickle
    data: dict[str, Any] = {}
    data["fields"] = {}
    for f in fields:
        rid = f.radar_id or f"radar_{id(f)}"
        data["fields"][rid] = f.to_dict()
    if metadata is not None:
        data["metadata"] = metadata
    with open(path, "wb") as fh:
        pickle.dump(data, fh)


def load_ew_lookup(path: str) -> dict[str, JammingField]:
    """从 pickle 文件加载, 返回 {radar_id: JammingField} 字典."""
    import pickle
    with open(path, "rb") as fh:
        data = pickle.load(fh)
    # 兼容旧格式: list
    if isinstance(data, list):
        result = {}
        for i, d in enumerate(data):
            rid = d.get("radar_id", f"radar_{i}")
            result[rid] = JammingField.from_dict(d)
        return result
    # 新格式: {"fields": {...}, "metadata": {...}}
    if "fields" in data:
        return {rid: JammingField.from_dict(d) for rid, d in data["fields"].items()}
    # 旧格式: {radar_id: field_dict}
    return {rid: JammingField.from_dict(d) for rid, d in data.items()}


def load_ew_metadata(path: str) -> dict[str, Any] | None:
    """从 pickle 文件读取输入元数据 (radars, jammers, region 等)."""
    import pickle
    with open(path, "rb") as fh:
        data = pickle.load(fh)
    return data.get("metadata") if isinstance(data, dict) else None


def compute_jamming_field(
    radar_position: tuple[float, float, float],
    jammer_position: tuple[float, float, float],
    strength: float,
    region: dict[str, float],
    resolution_km: float = 10.0,
    beamwidth_deg: float = DEFAULT_BEAMWIDTH_DEG,
    sidelobe_db: float = DEFAULT_SIDELOBE_DB,
    radar_id: str = "",
) -> JammingField:
    """
    计算单部干扰机对单部雷达的 SNR 缩放因子场。

    strength: 干扰机在参考距离 REF_DISTANCE_KM 处的 J/N₀ 比值。
              alpha = strength × (REF/Rj)², Rj 自动计算。
    radar_id: 雷达唯一标识, 与 threat.id 对应。
    """
    rlon, rlat, ralt = radar_position
    jlon, jlat, jalt = jammer_position

    # 干扰机到雷达的实际距离 → alpha 距离衰减
    rj_m = slant_range_m(rlon, rlat, ralt, jlon, jlat, jalt)
    rj_km = rj_m / 1000.0
    if rj_km < 1.0:
        rj_km = 1.0  # 避免除零
    alpha = strength * (REF_DISTANCE_KM / rj_km) ** 2

    # 干扰机相对雷达的方向 (固定)
    jam_az = bearing_deg(rlon, rlat, jlon, jlat)
    jam_el = elevation_deg(rlon, rlat, ralt, jlon, jlat, jalt)

    # 构建网格
    lat_ref = (region["lat_min"] + region["lat_max"]) / 2
    dlon = abs(resolution_km / (KM_PER_DEG * math.cos(math.radians(lat_ref))))
    dlat = abs(resolution_km / KM_PER_DEG)
    dalt = resolution_km

    lon_vals = np.arange(region["lon_min"], region["lon_max"] + dlon / 2, dlon)
    lat_vals = np.arange(region["lat_min"], region["lat_max"] + dlat / 2, dlat)
    alt_vals = np.arange(region["alt_min_km"], region["alt_max_km"] + dalt / 2, dalt)

    nlon, nlat, nalt = len(lon_vals), len(lat_vals), len(alt_vals)
    factors = np.ones((nlon, nlat, nalt), dtype=np.float32)
    ag_products = np.zeros((nlon, nlat, nalt), dtype=np.float32)

    total = nlon * nlat * nalt
    count = 0

    for ilon, lon in enumerate(lon_vals):
        for ilat, lat in enumerate(lat_vals):
            for ialt, alt_km in enumerate(alt_vals):
                alt_m = alt_km * 1000
                pt_az = bearing_deg(rlon, rlat, lon, lat)
                pt_el = elevation_deg(rlon, rlat, ralt, lon, lat, alt_m)

                # 3D 角间距: 雷达看目标 vs 雷达看干扰机
                sep_deg = angular_separation_deg(pt_az, pt_el,
                                                 jam_az, jam_el)

                g_ratio = antenna_gain_ratio(sep_deg, beamwidth_deg, sidelobe_db)

                # 两个保存值:
                #   ag = α × G_ratio      — 多机叠加时直接求和
                #   factor = 1/(1 + ag)   — 当前单机缩放因子
                ag = alpha * g_ratio
                ag_products[ilon, ilat, ialt] = float(ag)
                factors[ilon, ilat, ialt] = float(1.0 / (1.0 + ag))

                count += 1

    return JammingField(
        radar_id=radar_id,
        lon_grid=lon_vals,
        lat_grid=lat_vals,
        alt_grid=alt_vals,
        factors=factors,
        ag_products=ag_products,
        radar_position=radar_position,
        jammer_position=jammer_position,
        strength=strength,
    )


# ==============================================
# 多干扰机叠加
# ==============================================
def merge_jamming_fields(*fields: JammingField) -> JammingField:
    """合并多部干扰机的因子场.

    对每部干扰机分别调用 compute_jamming_field, 然后传入此函数:
        field1 = compute_jamming_field(radar, jammer1, strength1, ...)
        field2 = compute_jamming_field(radar, jammer2, strength2, ...)
        combined = merge_jamming_fields(field1, field2)

    ag_total = Σ ag_i, factor = 1 / (1 + ag_total).
    要求所有 field 使用相同的雷达和网格 (否则报错).
    """
    if not fields:
        raise ValueError("至少需要一个 field")
    base = fields[0]

    # 验证网格一致
    for f in fields[1:]:
        if (f.lon_grid.shape != base.lon_grid.shape
                or not np.allclose(f.lon_grid, base.lon_grid)):
            raise ValueError("所有 field 必须使用相同的网格 (lon_grid 不一致)")
        if (f.lat_grid.shape != base.lat_grid.shape
                or not np.allclose(f.lat_grid, base.lat_grid)):
            raise ValueError("所有 field 必须使用相同的网格 (lat_grid 不一致)")
        if (f.alt_grid.shape != base.alt_grid.shape
                or not np.allclose(f.alt_grid, base.alt_grid)):
            raise ValueError("所有 field 必须使用相同的网格 (alt_grid 不一致)")

    # ag 求和 → factor
    ag_total = sum(f.ag_products for f in fields)
    factors = 1.0 / (1.0 + ag_total)

    return JammingField(
        lon_grid=base.lon_grid.copy(),
        lat_grid=base.lat_grid.copy(),
        alt_grid=base.alt_grid.copy(),
        factors=factors.astype(np.float32),
        ag_products=ag_total.astype(np.float32),
        radar_position=base.radar_position,
        jammer_position=(-1, -1, -1),
        strength=float(ag_total.max()),
    )


# ==============================================
# 多雷达 × 多干扰机 批量计算
# ==============================================
def compute_all_fields(
    radars: list[dict],
    jammers: list[dict],
    strength_matrix: list[list[float]],
    region: dict[str, float],
    resolution_km: float = 10.0,
) -> list[JammingField]:
    """多雷达 × 多干扰机批量计算.

    radars:     [{"position": [lon,lat,alt_m], "beamwidth_deg": 3.0, ...}, ...]
    jammers:    [{"position": [lon,lat,alt_m]}, ...]

    strength_matrix[r][j]: 干扰机 j 对雷达 r 在参考距离 (100km) 处的 J/N₀.
                           距离衰减由函数内部根据实际 Rj 自动计算.
                           0 表示该 jammer 不干扰该 radar.
                           形状 (n_radars × n_jammers).

    返回: n_radars 个 JammingField, 每个已将对该雷达有效的干扰机合并.
    """
    n_radars = len(radars)
    n_jammers = len(jammers)

    if len(strength_matrix) != n_radars:
        raise ValueError(
            f"strength_matrix 行数 ({len(strength_matrix)}) != radars 数 ({n_radars})")
    for r in range(n_radars):
        if len(strength_matrix[r]) != n_jammers:
            raise ValueError(
                f"strength_matrix[{r}] 列数 ({len(strength_matrix[r])}) != jammers 数 ({n_jammers})")

    results = []
    for r_idx, r in enumerate(radars):
        radar_pos = (r["position"][0], r["position"][1], r["position"][2])
        radar_id = r.get("id", f"radar_{r_idx}")
        bw = r.get("beamwidth_deg", DEFAULT_BEAMWIDTH_DEG)
        sl = r.get("sidelobe_db", DEFAULT_SIDELOBE_DB)

        ag_total = None
        n_active = 0

        for j_idx, j in enumerate(jammers):
            strength = strength_matrix[r_idx][j_idx]
            if strength <= 0:
                continue

            jammer_pos = (j["position"][0], j["position"][1], j["position"][2])
            field = compute_jamming_field(
                radar_position=radar_pos,
                jammer_position=jammer_pos,
                strength=strength,
                region=region,
                resolution_km=resolution_km,
                beamwidth_deg=bw,
                sidelobe_db=sl,
                radar_id=radar_id,
            )

            if ag_total is None:
                ag_total = field.ag_products.copy()
            else:
                ag_total += field.ag_products
            n_active += 1

        if ag_total is None:
            ag_total = np.zeros((1, 1, 1), dtype=np.float32)
            factors = np.ones((1, 1, 1), dtype=np.float32)
            lon_vals = np.array([region["lon_min"]])
            lat_vals = np.array([region["lat_min"]])
            alt_vals = np.array([region["alt_min_km"]])
        else:
            factors = 1.0 / (1.0 + ag_total)
            lon_vals = field.lon_grid
            lat_vals = field.lat_grid
            alt_vals = field.alt_grid

        results.append(JammingField(
            radar_id=radar_id,
            lon_grid=lon_vals,
            lat_grid=lat_vals,
            alt_grid=alt_vals,
            factors=factors.astype(np.float32),
            ag_products=ag_total.astype(np.float32),
            radar_position=radar_pos,
            jammer_position=(-1, -1, -1),
            strength=float(ag_total.max()) if ag_total.size > 0 else 0.0,
        ))

    return results


def _estimate_grid_size(region: dict, resolution_km: float) -> tuple:
    lat_ref = (region["lat_min"] + region["lat_max"]) / 2
    dlon = abs(resolution_km / (KM_PER_DEG * math.cos(math.radians(lat_ref))))
    dlat = abs(resolution_km / KM_PER_DEG)
    dalt = resolution_km
    nlon = max(1, int((region["lon_max"] - region["lon_min"]) / dlon) + 1)
    nlat = max(1, int((region["lat_max"] - region["lat_min"]) / dlat) + 1)
    nalt = max(1, int((region["alt_max_km"] - region["alt_min_km"]) / dalt) + 1)
    return nlon, nlat, nalt


# ==============================================
# CLI
# ==============================================
EXAMPLE_INPUT = {
    "radars": [
        {
            "id": "E2D雷达",
            "position": [51.0, 35.0, 50],
            "detection_range_km": 100.0,
            "beamwidth_deg": 3.0,
            "sidelobe_db": -25.0,
        },
    ],
    "jammers": [
        {"position": [51.5, 34.5, 9000]},
    ],
    "strength_matrix": [
        [100.0]
    ],
    "region": {
        "lon_min": 50.5, "lon_max": 51.5,
        "lat_min": 34.5, "lat_max": 35.5,
        "alt_min_km": 1.0, "alt_max_km": 15.0,
    },
    "resolution_km": 2.0,
}


def _parse_input(d: dict[str, Any]):
    radars = d.get("radars", [d.get("radar", {})])
    jammers = d.get("jammers", [d.get("jammer", {})])

    # strength_matrix: 兼容旧格式 alpha_matrix
    strength_matrix = d.get("strength_matrix", d.get("alpha_matrix", []))

    # 兼容旧格式: 单 radar/jammer 自动包装
    if "radar" in d and "radars" not in d:
        radars = [d["radar"]]
    if "jammer" in d and "jammers" not in d:
        strength = d["jammer"].get("strength", d["jammer"].get("alpha", 100.0))
        jammers = [{"position": d["jammer"]["position"]}]
        if not strength_matrix:
            strength_matrix = [[strength]]

    reg = d["region"]
    resolution = d.get("resolution_km", 10.0)
    return radars, jammers, strength_matrix, reg, resolution


# ==============================================
# 可视化
# ==============================================

def _setup_cjk_font():
    """配置 matplotlib 中文字体 (macOS / Linux 自动检测)."""
    try:
        import matplotlib
        import matplotlib.font_manager as fm
    except ImportError:
        return

    # macOS
    for name in ["PingFang SC", "Heiti SC", "STHeiti", "Apple LiGothic"]:
        for f in fm.fontManager.ttflist:
            if f.name == name:
                matplotlib.rcParams["font.family"] = [name]
                return
    # Linux
    for name in ["WenQuanYi Micro Hei", "Noto Sans CJK SC", "Noto Sans SC",
                 "Droid Sans Fallback", "SimHei"]:
        for f in fm.fontManager.ttflist:
            if f.name == name:
                matplotlib.rcParams["font.family"] = [name]
                return

_setup_cjk_font()

# 自定义顺色图: 深红(重度压制) → 橙 → 黄 → 浅黄(无影响)
# 直观: 红色区域 = 雷达被压制, 黄色区域 = 雷达正常工作
_JAMMING_COLORS = [
    "#8b0000",  # 0.00: 深红 — 完全压制 (factor<0.05)
    "#c62828",  # 0.05: 红 — 重度压制
    "#e53935",  # 0.10: 亮红
    "#f57c00",  # 0.20: 橙 — 中度压制
    "#fbc02d",  # 0.30: 金 — 轻度压制
    "#fff176",  # 0.50: 浅黄 — 弱影响
    "#fff9c4",  # 0.70: 淡黄 — 微影响
    "#fafafa",  # 0.90: 近白 — 几乎无影响
    "#eeeeee",  # 0.99: 灰白 — 无影响 (雷达正常)
]

FACTOR_LABELS = [
    "0.00 完全压制",
    "0.05 重度压制",
    "0.10 强压制",
    "0.20 中度压制",
    "0.30 轻度压制",
    "0.50 弱影响",
    "0.70 微影响",
    "0.90 基本无影响",
    "0.99 无影响",
]


def _pick_display_alts(alt_grid: np.ndarray, jammers: list[dict]) -> list[tuple[int, float]]:
    """选择最多 3 个代表高度: 最低、最接近干扰机、最高."""
    all_alts = list(alt_grid)
    n = len(all_alts)
    if n <= 3:
        return [(i, all_alts[i]) for i in range(n)]

    # jammer 高度 (km)
    jammer_alts = [j["position"][2] / 1000.0 for j in jammers]
    jammer_alt = sum(jammer_alts) / len(jammer_alts) if jammer_alts else all_alts[n // 2]

    # 最接近 jammer 高度
    mid_idx = min(range(n), key=lambda i: abs(all_alts[i] - jammer_alt))

    indices = {0, mid_idx, n - 1}
    return [(i, all_alts[i]) for i in sorted(indices)]


def _build_jamming_cmap():
    """构建离散压制因子 colormap."""
    from matplotlib.colors import ListedColormap
    return ListedColormap(_JAMMING_COLORS, name="jamming")


def plot_jamming_fields(
    fields: list[JammingField],
    radars: list[dict],
    jammers: list[dict],
    strength_matrix: list[list[float]],
    output_path: str = None,
):
    """干扰因子场可视化 — 最多 3 高度 × N 雷达.

    改进要点:
      - 顺色图 (深红=压制, 浅黄=无影响), 告别易混淆的发散色 RdBu_r
      - 最多 3 个代表高度层 (最低 / 干扰机 / 最高)
      - 离散色条带中文标签
      - 干扰机位置标注因子具体值
      - 更大更清晰的字体
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import BoundaryNorm
    except ImportError:
        print("matplotlib 未安装，跳过绘图")
        return

    from pathlib import Path as P

    n_radars = len(fields)
    n_cols = n_radars

    # ---- 选择代表高度 ----
    alt_choices = _pick_display_alts(fields[0].alt_grid, jammers)
    n_rows = len(alt_choices)

    jamming_cmap = _build_jamming_cmap()

    # ---- 构建图形 ----
    sub_w, sub_h = 6.0, 5.0
    fig, axes = plt.subplots(
        n_rows, n_cols,
        figsize=(sub_w * n_cols + 1.5, sub_h * n_rows + 1.2),
        squeeze=False,
        constrained_layout=True,
    )

    factor_boundaries = [0.0, 0.05, 0.10, 0.20, 0.30, 0.50, 0.70, 0.90, 0.99, 1.0]
    norm = BoundaryNorm(factor_boundaries, ncolors=len(_JAMMING_COLORS), clip=True)

    for r_idx, field in enumerate(fields):
        rlon, rlat, ralt = field.radar_position
        radar_id = radars[r_idx].get("id", f"Radar{r_idx}")
        det_range = radars[r_idx].get("detection_range_km", 100.0)
        bw = radars[r_idx].get("beamwidth_deg", DEFAULT_BEAMWIDTH_DEG)

        lat_s = KM_PER_DEG
        lon_s = KM_PER_DEG * math.cos(math.radians(rlat))
        r_alt_km = ralt / 1000.0

        X, Y = np.meshgrid(field.lon_grid, field.lat_grid)

        for row, (k, alt_km) in enumerate(alt_choices):
            ax = axes[row, r_idx]

            f_2d = field.factors[:, :, k].T
            dh = alt_km - r_alt_km
            d_horiz_km = np.hypot(
                (X - rlon) * lon_s,
                (Y - rlat) * lat_s,
            )
            dist_3d_km = np.sqrt(d_horiz_km ** 2 + dh ** 2)
            f_2d = np.where(dist_3d_km <= det_range, f_2d, np.nan)

            # ---- 填色 (离散边界) ----
            cs = ax.contourf(
                X, Y, f_2d,
                levels=factor_boundaries,
                cmap=jamming_cmap,
                norm=norm,
                extend="both",
                antialiased=True,
            )

            # ---- 探测范围截面圈 ----
            if abs(dh) < det_range:
                r_cut = math.sqrt(max(0, det_range ** 2 - dh ** 2))
                ring = np.linspace(0, 2 * np.pi, 120)
                ax.plot(
                    rlon + r_cut * np.cos(ring) / lon_s,
                    rlat + r_cut * np.sin(ring) / lat_s,
                    color="#333333", linewidth=1.5, linestyle="--", alpha=0.6,
                    label="detection range" if row == 0 else "",
                )

            # ---- 干扰机 & 因子标注 ----
            for j_idx, j in enumerate(jammers):
                s_ij = (strength_matrix[r_idx][j_idx]
                        if r_idx < len(strength_matrix)
                           and j_idx < len(strength_matrix[r_idx])
                        else 0)
                if s_ij <= 0:
                    continue

                jlon, jlat, jalt_m = j["position"]
                j_alt_km = jalt_m / 1000.0

                # 干扰机在该层的因子值 (双线性插值)
                try:
                    factor_at_jammer = _interp_factor_2d(
                        field, k, jlon, jlat,
                    )
                    label = f"J{j_idx}\nf={factor_at_jammer:.3f}"
                except Exception:
                    label = f"J{j_idx}"

                # 干扰机位置三角形
                ax.plot(jlon, jlat, "^",
                        color="#c0392b", markersize=11,
                        markeredgecolor="white", markeredgewidth=1.2,
                        zorder=10)

                # 如果当前高度层接近 jammer 高度 → 标注因子值
                if abs(alt_km - j_alt_km) < max(2.0, (fields[0].alt_grid[1] - fields[0].alt_grid[0]) * 1.5):
                    ax.annotate(
                        label,
                        xy=(jlon, jlat),
                        xytext=(8, 8), textcoords="offset points",
                        fontsize=9, fontweight="bold",
                        color="#8b0000",
                        bbox=dict(boxstyle="round,pad=0.3",
                                  facecolor="white", edgecolor="#cccccc", alpha=0.85),
                        zorder=12,
                    )

            # ---- 雷达位置 ----
            ax.plot(rlon, rlat, "s", color="#1a237e", markersize=10,
                    markeredgecolor="white", markeredgewidth=1.0,
                    zorder=10)
            # 雷达名称标注
            ax.annotate(
                radar_id,
                xy=(rlon, rlat),
                xytext=(6, -10), textcoords="offset points",
                fontsize=9, fontweight="bold", color="#1a237e",
                zorder=11,
            )

            # ---- 坐标轴 ----
            ax.set_aspect(1.0 / math.cos(math.radians(rlat)))
            ax.grid(True, alpha=0.12, linestyle=":")
            ax.tick_params(labelsize=10)

            # ---- 行/列标题 ----
            if r_idx == 0:
                alt_label = f"{alt_km:.1f} km"
                if row == 0:
                    alt_label += " (低空)"
                elif row == n_rows - 1:
                    alt_label += " (高空)"
                else:
                    alt_label += " (中空)"
                ax.set_ylabel(f"{alt_label}\nLat (°)", fontsize=11, fontweight="bold")
            else:
                ax.set_ylabel("Lat (°)", fontsize=10)
            if row == 0:
                ax.set_title(
                    f"{radar_id}\nR={det_range:.0f} km  bw={bw:.1f}°",
                    fontsize=11, fontweight="bold",
                )
            ax.set_xlabel("Lon (°)", fontsize=10)

    # ---- 离散颜色条 ----
    cbar = fig.colorbar(
        plt.cm.ScalarMappable(norm=norm, cmap=jamming_cmap),
        ax=axes, shrink=0.90, pad=0.02, aspect=50,
        ticks=[0.025, 0.075, 0.15, 0.25, 0.40, 0.60, 0.80, 0.945, 0.995],
    )
    cbar.ax.set_yticklabels([
        "0.00\n完全压制",
        "0.05\n重度压制",
        "0.10\n强压制",
        "0.20\n中度",
        "0.30\n轻度",
        "0.50\n弱影响",
        "0.70\n微影响",
        "0.90\n基本无影响",
        "1.0\n无影响",
    ], fontsize=8)
    cbar.set_label("SNR 缩放因子 (越小压制越强)", fontsize=10, fontweight="bold")

    fig.suptitle(
        "电子战干扰因子场  |  行: 高度层  |  列: 雷达  |  "
        "▲ 干扰机  ■ 雷达  |  虚线 = 探测范围在该高度的水平截面",
        fontsize=13, fontweight="bold", y=1.01,
    )

    if output_path is None:
        output_path = str(P(__file__).resolve().parent / "ew_jamming_field.png")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close()
    print(f"图表已保存: {output_path}")


def _interp_factor_2d(field: JammingField, alt_idx: int,
                      lon: float, lat: float) -> float:
    """双线性插值查因子值 (2D)."""
    lon_g, lat_g = field.lon_grid, field.lat_grid
    ilon = np.searchsorted(lon_g, lon) - 1
    ilat = np.searchsorted(lat_g, lat) - 1
    ilon = max(0, min(len(lon_g) - 2, ilon))
    ilat = max(0, min(len(lat_g) - 2, ilat))

    f00 = field.factors[ilon,     ilat,     alt_idx]
    f10 = field.factors[ilon + 1, ilat,     alt_idx]
    f01 = field.factors[ilon,     ilat + 1, alt_idx]
    f11 = field.factors[ilon + 1, ilat + 1, alt_idx]

    tx = (lon - lon_g[ilon]) / (lon_g[ilon + 1] - lon_g[ilon])
    ty = (lat - lat_g[ilat]) / (lat_g[ilat + 1] - lat_g[ilat])
    return (f00 * (1 - tx) * (1 - ty)
            + f10 * tx * (1 - ty)
            + f01 * (1 - tx) * ty
            + f11 * tx * ty)


def plot_jamming_overview(
    fields: list[JammingField],
    radars: list[dict],
    jammers: list[dict],
    strength_matrix: list[list[float]],
    merged_factors: np.ndarray = None,
    output_path: str = None,
):
    """单张总览图 — 多雷达合并因子的单高度层视图 (PPT 专用).

    用 pcolormesh 替代 contourf, 色彩过渡更自然.
    叠加雷达探测范围圈、干扰机位置和因子值.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib 未安装，跳过绘图")
        return

    from pathlib import Path as P

    if merged_factors is not None:
        # ---- 合并因子: 选干扰机高度层 ----
        jammer_alt = sum(j["position"][2] for j in jammers) / len(jammers) / 1000.0
        alt_grid = fields[0].alt_grid
        k = min(range(len(alt_grid)), key=lambda i: abs(alt_grid[i] - jammer_alt))
        alt_km = alt_grid[k]

        f_merged = merged_factors[:, :, k].T  # (nlat, nlon)

        field0 = fields[0]
        X, Y = np.meshgrid(field0.lon_grid, field0.lat_grid)

        fig, ax = plt.subplots(figsize=(12, 9), constrained_layout=True)

        # pcolormesh 平滑填色
        jamming_cmap = _build_jamming_cmap()
        from matplotlib.colors import BoundaryNorm
        factor_boundaries = [0.0, 0.05, 0.10, 0.20, 0.30, 0.50, 0.70, 0.90, 0.99, 1.0]
        bnorm = BoundaryNorm(factor_boundaries, ncolors=len(_JAMMING_COLORS), clip=True)

        im = ax.pcolormesh(
            X, Y, f_merged,
            cmap=jamming_cmap, norm=bnorm,
            shading="auto", antialiased=True,
        )

        # 雷达 & 探测范围圈
        for r_idx, field in enumerate(fields):
            rlon, rlat, ralt = field.radar_position
            det_range = radars[r_idx].get("detection_range_km", 100.0)
            radar_id = radars[r_idx].get("id", f"R{r_idx}")

            lat_s = KM_PER_DEG
            lon_s = KM_PER_DEG * math.cos(math.radians(rlat))
            r_alt_km = ralt / 1000.0
            dh = alt_km - r_alt_km

            if abs(dh) < det_range:
                r_cut = math.sqrt(max(0, det_range ** 2 - dh ** 2))
                ring = np.linspace(0, 2 * np.pi, 150)
                ax.plot(
                    rlon + r_cut * np.cos(ring) / lon_s,
                    rlat + r_cut * np.sin(ring) / lat_s,
                    color="#333333", linewidth=1.8, linestyle="--", alpha=0.55,
                )

            ax.plot(rlon, rlat, "s", color="#1a237e", markersize=14,
                    markeredgecolor="white", markeredgewidth=1.5, zorder=10)
            ax.annotate(
                f"{radar_id}\nR={det_range:.0f}km",
                xy=(rlon, rlat),
                xytext=(8, -14), textcoords="offset points",
                fontsize=10, fontweight="bold", color="#1a237e",
                bbox=dict(boxstyle="round,pad=0.3",
                          facecolor="white", edgecolor="#1a237e", alpha=0.85),
                zorder=12,
            )

        # 干扰机
        for j_idx, j in enumerate(jammers):
            jlon, jlat, jalt_m = j["position"]
            j_alt_km = jalt_m / 1000.0
            ax.plot(jlon, jlat, "^", color="#c0392b", markersize=14,
                    markeredgecolor="white", markeredgewidth=1.5, zorder=10)
            try:
                f_j = _interp_factor_2d(fields[0], k, jlon, jlat)
                jam_label = f"J{j_idx}  f={f_j:.3f}"
            except Exception:
                jam_label = f"J{j_idx}"
            ax.annotate(
                jam_label,
                xy=(jlon, jlat),
                xytext=(10, 8), textcoords="offset points",
                fontsize=10, fontweight="bold", color="#8b0000",
                bbox=dict(boxstyle="round,pad=0.3",
                          facecolor="white", edgecolor="#c0392b", alpha=0.85),
                zorder=12,
            )

        ax.set_aspect(1.0 / math.cos(math.radians(np.mean(Y))))
        ax.grid(True, alpha=0.12, linestyle=":")
        ax.set_xlabel("经度 Lon (°)", fontsize=13, fontweight="bold")
        ax.set_ylabel("纬度 Lat (°)", fontsize=13, fontweight="bold")
        ax.set_title(
            f"电子战干扰因子场 — 合并视图 (高度 {alt_km:.1f} km)\n"
            "■ 雷达  ▲ 干扰机  |  深红=完全压制  浅黄=雷达正常",
            fontsize=14, fontweight="bold",
        )
        ax.tick_params(labelsize=11)

        # 颜色条
        cbar = fig.colorbar(
            plt.cm.ScalarMappable(norm=bnorm, cmap=jamming_cmap),
            ax=ax, shrink=0.82, pad=0.02, aspect=50,
            ticks=[0.025, 0.075, 0.15, 0.25, 0.40, 0.60, 0.80, 0.945, 0.995],
        )
        cbar.ax.set_yticklabels([
            "0.00 完全压制", "0.05 重度", "0.10 强压制",
            "0.20 中度", "0.30 轻度", "0.50 弱",
            "0.70 微影响", "0.90 基本无", "1.0 无影响",
        ], fontsize=9)
        cbar.set_label("SNR 缩放因子", fontsize=11, fontweight="bold")

        if output_path is None:
            output_path = str(P(__file__).resolve().parent / "ew_overview.png")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=180, bbox_inches="tight",
                    facecolor="white", edgecolor="none")
        plt.close()
        print(f"总览图已保存: {output_path}")

    # ---- 若没有 merged_factors, 画第一张 field 的单高度视图 ----
    else:
        first = fields[0]
        jammer_alt = sum(j["position"][2] for j in jammers) / len(jammers) / 1000.0
        alt_grid = first.alt_grid
        k = min(range(len(alt_grid)), key=lambda i: abs(alt_grid[i] - jammer_alt))
        alt_km = alt_grid[k]

        X, Y = np.meshgrid(first.lon_grid, first.lat_grid)
        f_2d = first.factors[:, :, k].T

        fig, ax = plt.subplots(figsize=(12, 9), constrained_layout=True)

        jamming_cmap = _build_jamming_cmap()
        from matplotlib.colors import BoundaryNorm
        factor_boundaries = [0.0, 0.05, 0.10, 0.20, 0.30, 0.50, 0.70, 0.90, 0.99, 1.0]
        bnorm = BoundaryNorm(factor_boundaries, ncolors=len(_JAMMING_COLORS), clip=True)

        im = ax.pcolormesh(X, Y, f_2d, cmap=jamming_cmap, norm=bnorm,
                           shading="auto", antialiased=True)

        for r_idx, field in enumerate(fields):
            rlon, rlat, ralt = field.radar_position
            det_range = radars[r_idx].get("detection_range_km", 100.0)
            radar_id = radars[r_idx].get("id", f"R{r_idx}")
            lat_s = KM_PER_DEG
            lon_s = KM_PER_DEG * math.cos(math.radians(rlat))
            r_alt_km = ralt / 1000.0
            dh = alt_km - r_alt_km
            if abs(dh) < det_range:
                r_cut = math.sqrt(max(0, det_range ** 2 - dh ** 2))
                ring = np.linspace(0, 2 * np.pi, 150)
                ax.plot(rlon + r_cut * np.cos(ring) / lon_s,
                        rlat + r_cut * np.sin(ring) / lat_s,
                        color="#333333", linewidth=1.8, linestyle="--", alpha=0.55)
            ax.plot(rlon, rlat, "s", color="#1a237e", markersize=14,
                    markeredgecolor="white", markeredgewidth=1.5, zorder=10)
            ax.annotate(f"{radar_id}",
                        xy=(rlon, rlat), xytext=(8, -14),
                        textcoords="offset points",
                        fontsize=10, fontweight="bold", color="#1a237e",
                        bbox=dict(boxstyle="round,pad=0.3",
                                  facecolor="white", edgecolor="#1a237e", alpha=0.85),
                        zorder=12)

        for j_idx, j in enumerate(jammers):
            jlon, jlat = j["position"][0], j["position"][1]
            ax.plot(jlon, jlat, "^", color="#c0392b", markersize=14,
                    markeredgecolor="white", markeredgewidth=1.5, zorder=10)
            try:
                f_j = _interp_factor_2d(first, k, jlon, jlat)
                jam_label = f"J{j_idx}  f={f_j:.3f}"
            except Exception:
                jam_label = f"J{j_idx}"
            ax.annotate(jam_label,
                        xy=(jlon, jlat), xytext=(10, 8),
                        textcoords="offset points",
                        fontsize=10, fontweight="bold", color="#8b0000",
                        bbox=dict(boxstyle="round,pad=0.3",
                                  facecolor="white", edgecolor="#c0392b", alpha=0.85),
                        zorder=12)

        ax.set_aspect(1.0 / math.cos(math.radians(np.mean(Y))))
        ax.grid(True, alpha=0.12, linestyle=":")
        ax.set_xlabel("经度 Lon (°)", fontsize=13, fontweight="bold")
        ax.set_ylabel("纬度 Lat (°)", fontsize=13, fontweight="bold")
        ax.set_title(
            f"电子战干扰因子场 (高度 {alt_km:.1f} km)  |  "
            "深红=完全压制  浅黄=雷达正常",
            fontsize=14, fontweight="bold",
        )
        ax.tick_params(labelsize=11)
        cbar = fig.colorbar(
            plt.cm.ScalarMappable(norm=bnorm, cmap=jamming_cmap),
            ax=ax, shrink=0.82, pad=0.02, aspect=50,
            ticks=[0.025, 0.075, 0.15, 0.25, 0.40, 0.60, 0.80, 0.945, 0.995],
        )
        cbar.ax.set_yticklabels([
            "0.00 完全压制", "0.05 重度", "0.10 强压制",
            "0.20 中度", "0.30 轻度", "0.50 弱",
            "0.70 微影响", "0.90 基本无", "1.0 无影响",
        ], fontsize=9)
        cbar.set_label("SNR 缩放因子", fontsize=11, fontweight="bold")

        if output_path is None:
            output_path = str(P(__file__).resolve().parent / "ew_overview.png")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=180, bbox_inches="tight",
                    facecolor="white", edgecolor="none")
        plt.close()
        print(f"总览图已保存: {output_path}")


def plot_jamming_from_pkl(pkl_path: str, output_path: str = None,
                         overview_path: str = None):
    """从 pickle 文件读取干扰场数据并画图.

    用法: python3 ew/ew_jamming_field.py --plot-from-pkl ew_fields.pkl
    """
    lookup = load_ew_lookup(pkl_path)
    metadata = load_ew_metadata(pkl_path)

    if metadata is None:
        print("警告: pkl 中无输入元数据, 无法画图")
        return

    radars = metadata["radars"]
    jammers = metadata["jammers"]
    strength_matrix = metadata["strength_matrix"]

    fields = [lookup[r["id"]] for r in radars]

    # 多雷达网格图
    plot_jamming_fields(fields, radars, jammers, strength_matrix, output_path)

    # 总览图: 逐点取最小因子 (最严重压制) 作为"任一雷达被压制"指标
    merged_factors = np.min(np.stack([f.factors for f in fields]), axis=0)
    plot_jamming_overview(
        fields, radars, jammers, strength_matrix,
        merged_factors=merged_factors,
        output_path=overview_path,
    )


def main():
    parser = argparse.ArgumentParser(description="EW SNR缩放因子场计算")
    parser.add_argument("-i", "--input", help="输入 JSON 文件路径")
    parser.add_argument("-o", "--output", help="输出 JSON 文件路径")
    parser.add_argument("--pkl", help="输出 pickle 文件路径 (可查询 lon/lat/alt → factor)")
    parser.add_argument("--no-plot", action="store_true", help="跳过绘图")
    parser.add_argument("--plot-output", help="画图输出路径 (默认: 当前目录下)")
    parser.add_argument("--plot-from-pkl", help="从 pickle 文件直接画图 (不重新计算)")
    args = parser.parse_args()

    # 模式 1: 从 pkl 画图
    if args.plot_from_pkl:
        plot_jamming_from_pkl(args.plot_from_pkl, output_path=args.plot_output)
        return

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            input_data = json.load(f)
    else:
        print("未指定输入文件，使用示例数据运行...\n")
        input_data = EXAMPLE_INPUT

    radars, jammers, strength_matrix, region, resolution = _parse_input(input_data)
    fields = compute_all_fields(radars, jammers, strength_matrix, region, resolution)

    for r_idx, field in enumerate(fields):
        f = field.factors
        print(f"\n--- 雷达 {r_idx}: {field.radar_position} ---")
        print(f"  ag max={field.ag_products.max():.1f}  mean={field.ag_products.mean():.3f}")
        print(f"  factor min={f.min():.4f}  max={f.max():.4f}  mean={f.mean():.4f}")
        print(f"  网格: {f.shape} (lon×lat×alt)")

    if not args.no_plot:
        plot_jamming_fields(fields, radars, jammers, strength_matrix, output_path=args.plot_output)

    # 保存 pkl (含元数据)
    pkl_path = args.pkl
    if pkl_path is None:
        if args.input:
            pkl_path = str(Path(args.input).with_suffix(".pkl"))
        else:
            pkl_path = str(Path(__file__).resolve().parent / "ew_fields.pkl")
    metadata = {
        "radars": radars,
        "jammers": jammers,
        "strength_matrix": strength_matrix,
        "region": region,
        "resolution_km": resolution,
    }
    save_fields_pkl(fields, pkl_path, metadata=metadata)
    print(f"pickle 已保存: {pkl_path}")
    print(f"  查询: from src.ew.ew_jamming_field import load_ew_lookup")
    print(f"        lookup = load_ew_lookup('{pkl_path}')")
    print(f"        factor = lookup['radar_id'].lookup(lon, lat, alt_km)")
    print(f"  画图: python3 ew/ew_jamming_field.py --plot-from-pkl {pkl_path}")

    if args.output:
        out_path = Path(args.output)
        result = [f.to_dict() for f in fields]
        out_path.write_text(
            json.dumps(result, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nJSON 已写入 {args.output}")


if __name__ == "__main__":
    main()
