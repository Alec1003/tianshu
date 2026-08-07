"""
方向候选点生成器。

- mode2: 生成入射角参考点，用于定义末端方向代价参考
- mode3/4: 生成攻击点候选，路径规划直接以候选攻击点为目标
"""

import math
from dataclasses import dataclass, field
from typing import List, Tuple

from .core.geo import azimuth_elevation_to_vector, vec_len


@dataclass
class ApproachSector:
    """单个方向候选."""
    azimuth_deg: float       # 进入方位角 (0=北, 90=东)
    elevation_deg: float     # 进入俯仰角 (+向上, -向下)
    direction_vec: Tuple[float, float, float]  # 单位方向向量
    point_local: Tuple[float, float, float]    # 候选点/参考点 (east, north, up) km
    point_label: str = ""
    point_kind: str = "target"


@dataclass
class TargetSectors:
    """一个目标的全部方向候选."""
    target_id: str
    target_pos: Tuple[float, float, float]  # (east, north, up) km
    radius_km: float
    sectors: List[ApproachSector] = field(default_factory=list)


def generate_direction_reference_sectors(
    target_id: str,
    target_pos: Tuple[float, float, float],
    directions: List[Tuple[float, float]],  # [(azimuth_deg, elevation_deg), ...]
    reference_radius_km: float = 50.0,
) -> TargetSectors:
    """为目标生成入射角参考点.

    参考点 = target_pos - direction_vec * reference_radius_km
    路径仍然规划到目标，只是用参考点定义期望入射方向。

    Args:
        target_id: 目标标识
        target_pos: 目标在局部坐标系的位置 (east, north, up) km
        directions: 预设进入方向列表 [(azimuth, elevation), ...]
        reference_radius_km: 入射角参考点距离 (km)

    Returns:
        TargetSectors 包含全部参考点方向信息
    """
    sectors = []
    for az, el in directions:
        direction = azimuth_elevation_to_vector(az, el)
        reference_point = (
            target_pos[0] - direction[0] * reference_radius_km,
            target_pos[1] - direction[1] * reference_radius_km,
            target_pos[2] - direction[2] * reference_radius_km,
        )
        sectors.append(ApproachSector(
            azimuth_deg=az,
            elevation_deg=el,
            direction_vec=direction,
            point_local=reference_point,
            point_label=f"ref_{az:.0f}_{el:.0f}",
            point_kind="approach_ref",
        ))

    return TargetSectors(
        target_id=target_id,
        target_pos=target_pos,
        radius_km=reference_radius_km,
        sectors=sectors,
    )


def generate_uniform_approach_reference_sectors(
    target_id: str,
    target_pos: Tuple[float, float, float],
    reference_radius_km: float,
    reference_up_height_km: float,
    reference_count: int,
) -> TargetSectors:
    """围绕目标均匀生成入射角参考点."""
    count = max(1, reference_count)
    reference_up = target_pos[2] + reference_up_height_km
    sectors = []
    for idx in range(count):
        azimuth = (360.0 * idx / count) % 360.0
        rad = math.radians(azimuth)
        point = (
            target_pos[0] + reference_radius_km * math.sin(rad),
            target_pos[1] + reference_radius_km * math.cos(rad),
            reference_up,
        )
        to_target = (
            target_pos[0] - point[0],
            target_pos[1] - point[1],
            target_pos[2] - point[2],
        )
        dist_2d = math.sqrt(to_target[0] ** 2 + to_target[1] ** 2)
        elevation = math.degrees(math.atan2(to_target[2], dist_2d)) if dist_2d > 1e-9 else -90.0
        approach_azimuth = math.degrees(math.atan2(to_target[0], to_target[1]))
        if approach_azimuth < 0:
            approach_azimuth += 360
        direction_len = vec_len(to_target)
        unit_direction = (
            to_target[0] / direction_len,
            to_target[1] / direction_len,
            to_target[2] / direction_len,
        )
        sectors.append(
            ApproachSector(
                azimuth_deg=approach_azimuth,
                elevation_deg=elevation,
                direction_vec=unit_direction,
                point_local=point,
                point_label=f"approach_ref_{idx + 1:02d}",
                point_kind="approach_ref",
            )
        )

    return TargetSectors(
        target_id=target_id,
        target_pos=target_pos,
        radius_km=reference_radius_km,
        sectors=sectors,
    )


def generate_attack_point_sectors(
    target_id: str,
    target_pos: Tuple[float, float, float],
    attack_point_radius_km: float,
    attack_point_up_height_km: float,
    attack_point_count: int,
) -> TargetSectors:
    """围绕目标生成均匀分布的攻击点候选.

    候选点位于以目标为圆心、半径为 attack_point_radius_km 的圆周上，
    高度统一抬高 attack_point_up_height_km。
    """
    count = max(1, attack_point_count)
    point_up = target_pos[2] + attack_point_up_height_km

    sectors = []
    for idx in range(count):
        azimuth = (360.0 * idx / count) % 360.0
        rad = math.radians(azimuth)
        point = (
            target_pos[0] + attack_point_radius_km * math.sin(rad),
            target_pos[1] + attack_point_radius_km * math.cos(rad),
            point_up,
        )
        to_target = (
            target_pos[0] - point[0],
            target_pos[1] - point[1],
            target_pos[2] - point[2],
        )
        dist_2d = math.sqrt(to_target[0] ** 2 + to_target[1] ** 2)
        elevation = math.degrees(math.atan2(to_target[2], dist_2d)) if dist_2d > 1e-9 else -90.0
        approach_azimuth = math.degrees(math.atan2(to_target[0], to_target[1]))
        if approach_azimuth < 0:
            approach_azimuth += 360
        direction_len = vec_len(to_target)
        unit_direction = (
            to_target[0] / direction_len,
            to_target[1] / direction_len,
            to_target[2] / direction_len,
        )
        sectors.append(ApproachSector(
            azimuth_deg=approach_azimuth,
            elevation_deg=elevation,
            direction_vec=unit_direction,
            point_local=point,
            point_label=f"attack_{idx + 1:02d}",
            point_kind="attack_point",
        ))

    return TargetSectors(
        target_id=target_id,
        target_pos=target_pos,
        radius_km=attack_point_radius_km,
        sectors=sectors,
    )


def calculate_arrival_angle(
    path_end: Tuple[float, float, float],
    target: Tuple[float, float, float],
) -> Tuple[float, float]:
    """计算路径末端实际进入角度 (azimuth, elevation).

    Returns:
        (azimuth_deg, elevation_deg)
    """
    dx = target[0] - path_end[0]
    dy = target[1] - path_end[1]
    dz = target[2] - path_end[2]
    dist_2d = math.sqrt(dx*dx + dy*dy)

    azimuth = math.degrees(math.atan2(dx, dy))  # atan2(x,y): 0=北, 90=东
    if azimuth < 0:
        azimuth += 360

    elevation = math.degrees(math.atan2(dz, dist_2d))

    return azimuth, elevation
