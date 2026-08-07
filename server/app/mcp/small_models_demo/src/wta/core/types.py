"""核心数据类型 — 问题域中不依赖任何求解器的纯数据模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Target:
    """单个目标。

    frozen=True 保证 target 在 MILP 构建期间不会被意外修改。
    """

    target_id: str
    target_type: str
    damage_requirement_min: float
    damage_requirement_max: float
    loss_air_defense_damage: float
    risk_distance: float = float("inf")


@dataclass
class FeatureData:
    """全局武器/平台/目标类型能力参数 — 一次加载，全局共享。"""

    platform_loadout: dict[str, int]
    weapon_hardpoint_cost: dict[str, int]
    compatibility: dict[tuple[str, str], int]
    destroy: dict[tuple[str, str], float]
    hit_rate: dict[tuple[str, str], float]
    weapon_cep: dict[str, float]
    weapon_lethal_radius: dict[str, float]
    risk_excluded: set[tuple[str, str]]
    platforms: list[str]
    weapons: list[str]
    target_types: list[str]
    default_hit_rate_impact: dict[str, float]


@dataclass
class BaseData:
    """单个基地的库存和成本。"""

    base_id: str
    platform_num: dict[str, int]
    weapon_num: dict[str, int]
    platform_cost: dict[str, float]
    weapon_cost: dict[str, float]


@dataclass
class ModelMetadata:
    """build_model() 返回的模型元数据 — 替代裸 dict。

    包含所有在 MILP 构建期间预计算、结果提取时需要的索引和映射。
    """

    sorties: list[tuple[str, str, str, int]]
    """(base_id, platform, group_id, wave) 架次桶列表。"""

    group_targets: dict[tuple[str, str, str], tuple[str, ...]]
    """(base_id, platform, group_id) -> 目标组元组。"""

    targets: list[Target]
    """目标列表。"""

    waves: list[int]
    """波次列表，从 1 开始。"""

    pair_wave_index: list[tuple[str, str, int]]
    """排序后的 (weapon, target_id, wave) 组合列表。"""

    state_ids_by_target: dict[str, list[str]]
    """target_id -> [state_id, ...] 每个目标的状态 ID 列表。"""

    alive_subset_by_state: dict[tuple[str, str], tuple[str, ...]]
    """(target_id, state_id) -> 存活 influencer 子集。"""

    impact_factor_by_state: dict[tuple[str, str], float]
    """(target_id, state_id) -> 综合影响因子。"""

    level_options: dict[tuple[str, str, int, str], list[int]]
    """(weapon, target_id, wave, state_id) -> 可选命中层级列表。"""

    damage_by_pair_wave: dict[tuple[str, str, int], float]
    """(weapon, target_id, wave) -> 单发毁伤值。"""

    hit_probability_by_choice: dict[tuple[str, str, int, str], float]
    """(weapon, target_id, wave, state_id) -> 有效命中概率。"""

    launch_thresholds: dict[tuple[str, str, int, str, int], int]
    """(weapon, target_id, wave, state_id, level) -> 达到该层级所需的最小发射数。"""

    influencer_by_target: dict[str, list[str]]
    """target_id -> 对其有影响的 AD 目标 ID 列表。"""
