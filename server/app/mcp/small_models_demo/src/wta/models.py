from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# 核心类型从 core/types 导入并在此 re-export，保持向后兼容
from .core.types import Target, FeatureData, BaseData, ModelMetadata  # noqa: F401
from .core.probability import (  # noqa: F401
    binomial_tail_probability,
    max_confident_hits_for_launch_cap,
    min_launches_for_confident_hits,
)

_logger = logging.getLogger("wta")


def log(message: str) -> None:
    _logger.info(message)


# ---------------------------------------------------------------------------
# 配置加载函数
# ---------------------------------------------------------------------------


def _load_structured_data(path: Path) -> Any:
    """按文件后缀加载 YAML/YML/JSON 结构化配置。"""
    suffix = path.suffix.lower()
    with path.open("r", encoding="utf-8") as f:
        if suffix in {".yaml", ".yml"}:
            return yaml.safe_load(f)
        if suffix == ".json":
            return json.load(f)
    raise ValueError(
        f"Unsupported config format for {path}. Expected .yaml, .yml, or .json"
    )


def _parse_feature_data(data: dict[str, Any]) -> FeatureData:
    platforms = list(data["platforms"].keys())
    weapons = list(data["weapons"].keys())
    target_types = list(data["target_types"].keys())

    platform_loadout = {p: int(data["platforms"][p]["loadout"]) for p in platforms}
    weapon_hardpoint_cost = {w: int(data["weapons"][w]["hardpoint"]) for w in weapons}

    weapon_cep: dict[str, float] = {}
    weapon_lethal_radius: dict[str, float] = {}
    for w in weapons:
        wd = data["weapons"][w]
        if "cep" in wd:
            weapon_cep[w] = float(wd["cep"])
        if "lethal_radius" in wd:
            weapon_lethal_radius[w] = float(wd["lethal_radius"])

    compatibility: dict[tuple[str, str], int] = {}
    for p in platforms:
        allowed = set(data["compatibility"].get(p, []))
        for w in weapons:
            compatibility[(p, w)] = 1 if w in allowed else 0

    destroy: dict[tuple[str, str], float] = {}
    hit_rate: dict[tuple[str, str], float] = {}
    default_hit_rate_impact: dict[str, float] = {}
    for tt in target_types:
        tt_data = data["target_types"][tt]
        for w in weapons:
            destroy[(tt, w)] = float(tt_data["damage"].get(w, 0.0))
            hit_rate[(tt, w)] = float(tt_data["hit_rate"].get(w, 0.0))
        if "default_hit_rate_impact" in tt_data:
            default_hit_rate_impact[tt] = float(tt_data["default_hit_rate_impact"])

    return FeatureData(
        platform_loadout=platform_loadout,
        weapon_hardpoint_cost=weapon_hardpoint_cost,
        compatibility=compatibility,
        destroy=destroy,
        hit_rate=hit_rate,
        weapon_cep=weapon_cep,
        weapon_lethal_radius=weapon_lethal_radius,
        risk_excluded=set(),
        platforms=platforms,
        weapons=weapons,
        target_types=target_types,
        default_hit_rate_impact=default_hit_rate_impact,
    )


def load_feature_data(data: dict[str, Any]) -> FeatureData:
    """从内联 dict 加载全局能力参数。"""
    fd = _parse_feature_data(data)
    log(
        f"全局能力加载完成: platforms={len(fd.platforms)}, "
        f"weapons={len(fd.weapons)}, target_types={len(fd.target_types)}"
    )
    return fd


def load_feature_yaml(path: Path) -> FeatureData:
    """从 YAML/JSON 加载全局能力参数。"""
    data = _load_structured_data(path)
    fd = _parse_feature_data(data)
    log(
        f"全局能力加载完成: platforms={len(fd.platforms)}, "
        f"weapons={len(fd.weapons)}, target_types={len(fd.target_types)}"
    )
    return fd


def load_base_data(data: dict[str, Any], feature_data: FeatureData) -> BaseData:
    """从内联 dict 加载单个基地的库存和成本。"""
    base_id = data["base_id"]

    platform_num = {
        p: int(data.get("platforms", {}).get(p, 0)) for p in feature_data.platforms
    }
    weapon_num = {
        w: int(data.get("weapons", {}).get(w, 0)) for w in feature_data.weapons
    }

    costs = data.get("costs", {})
    platform_cost = {
        p: float(costs.get("platform", {}).get(p, 0)) for p in feature_data.platforms
    }
    weapon_cost = {
        w: float(costs.get("weapon", {}).get(w, 0)) for w in feature_data.weapons
    }

    bd = BaseData(
        base_id=base_id,
        platform_num=platform_num,
        weapon_num=weapon_num,
        platform_cost=platform_cost,
        weapon_cost=weapon_cost,
    )
    log(
        f"基地 {base_id} 数据加载完成: "
        f"platform_inventory={bd.platform_num}, "
        f"weapon_inventory={bd.weapon_num}"
    )
    return bd


def load_base_yaml(path: Path, feature_data: FeatureData) -> BaseData:
    """从 YAML/JSON 加载单个基地的库存和成本。"""
    data = _load_structured_data(path)
    return load_base_data(data, feature_data)


def load_scenario_yaml(path: Path) -> dict[str, Any]:
    """从 YAML/JSON 加载场景配置，返回配置 dict。"""
    config = _load_structured_data(path)
    log(f"场景配置加载完成: {path}")
    return config


# ---------------------------------------------------------------------------
# 校验与目标解析
# ---------------------------------------------------------------------------


def validate_config(
    config: dict[str, Any],
    feature_data: FeatureData,
    base_data: dict[str, BaseData],
) -> tuple[list[Target], dict[tuple[str, str], list[tuple[str, ...]]]]:
    global_loss = config.get("solver", {}).get("loss_air_defense_damage", None)
    targets = [_parse_target_config(item, global_loss) for item in config["targets"]]
    target_ids = {t.target_id for t in targets}

    for t in targets:
        if t.target_type not in feature_data.target_types:
            raise ValueError(
                f"Unknown target type '{t.target_type}' for target '{t.target_id}'"
            )

    groups: dict[tuple[str, str], list[tuple[str, ...]]] = {}
    ptg = config.get("sortie_groups") or config.get("platform_target_groups")

    if ptg is None:
        # 未指定时自动生成：每个基地的每个平台，每个目标各自为一个组
        target_ids_sorted = sorted(target_ids)
        for bid in base_data:
            for plat in feature_data.platforms:
                if base_data[bid].platform_num.get(plat, 0) > 0:
                    groups[(bid, plat)] = [(tid,) for tid in target_ids_sorted]
    else:
        for base_id, platform_map in ptg.items():
            if base_id not in base_data:
                raise ValueError(f"Unknown base '{base_id}' in sortie_groups")
            for platform_name, group_spec in platform_map.items():
                if platform_name not in feature_data.platforms:
                    raise ValueError(f"Unknown platform '{platform_name}'")
                if base_data[base_id].platform_num.get(platform_name, 0) <= 0:
                    continue
                if group_spec == "all":
                    groups[(base_id, platform_name)] = [
                        (tid,) for tid in sorted(target_ids)
                    ]
                else:
                    normalized_groups = []
                    for group in group_spec:
                        if isinstance(group, (str, int)):
                            raw_group = (group,)
                        else:
                            raw_group = tuple(group)
                        norm = tuple(str(tid) for tid in raw_group)
                        unknown = set(norm) - target_ids
                        if unknown:
                            raise ValueError(
                                f"Unknown target ids {sorted(unknown)} in group "
                                f"{group} for ({base_id}, {platform_name})"
                            )
                        normalized_groups.append(norm)
                    groups[(base_id, platform_name)] = normalized_groups

    log(f"配置校验完成: targets={len(targets)}, grouped_platforms={len(groups)}")
    for t in targets:
        log(
            f"  目标: id={t.target_id}, type={t.target_type}, "
            f"damage_range=({t.damage_requirement_min},{t.damage_requirement_max}), "
            f"loss_air_defense_damage={t.loss_air_defense_damage}"
        )
    for (bid, plat), gl in groups.items():
        rendered = ["{" + ",".join(g) + "}" for g in gl]
        log(f"  目标组: base={bid}, platform={plat}, groups={rendered}")
    return targets, groups


def _parse_target_config(
    item: dict[str, Any], global_loss_air_defense_damage: Any
) -> Target:
    # 兼容 "damage": [min, max] 和 "damage": scalar 两种写法
    raw = item.get("damage")
    if isinstance(raw, (list, tuple)):
        if len(raw) != 2:
            raise ValueError(f"damage must have length 2: {raw}")
        dmg_min, dmg_max = float(raw[0]), float(raw[1])
    elif raw is not None:
        dmg_min = dmg_max = float(raw)
    else:
        dmg_min = float(item.get("damage_min", item.get("damage_requirement_min", 0)))
        dmg_max = float(item.get("damage_max", item.get("damage_requirement_max", 0)))

    if dmg_min > dmg_max:
        raise ValueError(
            f"damage interval invalid for target {item.get('id', '?')}: "
            f"{dmg_min} > {dmg_max}"
        )

    loss_ad = item.get("loss_air_defense_damage", global_loss_air_defense_damage)
    if loss_ad is None:
        loss_ad = dmg_min
    loss_ad = float(loss_ad)
    if loss_ad < 0:
        raise ValueError(f"loss_air_defense_damage must be >= 0")

    risk_distance = float(item.get("risk_distance", float("inf")))

    return Target(
        target_id=str(item["id"]),
        target_type=str(item["type"]),
        damage_requirement_min=dmg_min,
        damage_requirement_max=dmg_max,
        loss_air_defense_damage=loss_ad,
        risk_distance=risk_distance,
    )


# ---------------------------------------------------------------------------
# 波次参数
# ---------------------------------------------------------------------------


def load_wave_parameters(
    config: dict[str, Any], targets: list[Target], feature_data: FeatureData | None = None
) -> tuple[int, dict[tuple[str, str], float]]:
    solver = config.get("solver", {})
    wave_count = int(solver.get("waves", 1))
    if wave_count <= 0:
        raise ValueError(f"waves must be positive, got {wave_count}")

    target_ids = [t.target_id for t in targets]
    impact_matrix: dict[tuple[str, str], float] = {}

    # 初始化为全 1.0（无影响）
    for src in target_ids:
        for dst in target_ids:
            impact_matrix[(src, dst)] = 1.0

    raw_impact = config.get("hit_rate_impact")
    if raw_impact is not None:
        for i, row in enumerate(raw_impact):
            src = target_ids[i]
            for j, val in enumerate(row):
                dst = target_ids[j]
                v = float(val)
                if v > 0:
                    impact_matrix[(src, dst)] = v
    elif feature_data is not None and feature_data.default_hit_rate_impact:
        # 用户未提供 hit_rate_impact 矩阵，使用各目标类型的 default_hit_rate_impact 兜底
        for t in targets:
            src = t.target_id
            factor = feature_data.default_hit_rate_impact.get(t.target_type, 1.0)
            if abs(factor - 1.0) > 1e-9:
                for dst in target_ids:
                    impact_matrix[(src, dst)] = factor

    log(f"波次参数加载完成: waves={wave_count}, impact_pairs={len(impact_matrix)}")
    return wave_count, impact_matrix


# ---------------------------------------------------------------------------
# CEP 风险约束
# ---------------------------------------------------------------------------


def enforce_cep_risk_constraints(
    feature_data: FeatureData,
    targets: list[Target],
    risk_confidence: float,
) -> None:
    """根据 CEP + 杀伤半径 + 风险距离过滤武器-目标兼容性。"""
    if not feature_data.weapon_cep:
        return

    try:
        from .weapon_target_matching import (
            WeaponPhysics,
            TargetRisk,
            match_weapons_to_targets,
        )
    except ImportError:
        from weapon_target_matching import (
            WeaponPhysics,
            TargetRisk,
            match_weapons_to_targets,
        )

    wlist = [
        WeaponPhysics(
            name=w,
            cep=feature_data.weapon_cep.get(w, 0),
            lethal_radius=feature_data.weapon_lethal_radius.get(w, 0.0),
        )
        for w in feature_data.weapons
    ]
    tlist = [
        TargetRisk(target_id=t.target_id, risk_distance=t.risk_distance)
        for t in targets
    ]

    result = match_weapons_to_targets(wlist, tlist, confidence=risk_confidence)

    feature_data.risk_excluded = {
        (target_id, weapon) for weapon, target_id, *_ in result.excluded_pairs
    }

    for wpn, tid, ir, rd in sorted(result.excluded_pairs):
        log(
            f"  风险约束禁用: weapon={wpn} target={tid} (波及半径={ir:.1f}m > risk_distance={rd:.0f}m)"
        )

    if feature_data.risk_excluded:
        log(
            f"CEP风险约束: 禁用 {len(feature_data.risk_excluded)} 条 (置信度={risk_confidence:.2f}, k={result.k_factor:.2f})"
        )
    else:
        log(
            f"CEP风险约束: 所有组合通过 (置信度={risk_confidence:.2f}, k={result.k_factor:.2f})"
        )


# ---------------------------------------------------------------------------
# 状态枚举
# ---------------------------------------------------------------------------


def enumerate_alive_subsets(items: list[str]) -> list[tuple[str, ...]]:
    subsets: list[tuple[str, ...]] = []
    for mask in range(1 << len(items)):
        subset = tuple(items[i] for i in range(len(items)) if (mask >> i) & 1)
        subsets.append(subset)
    return subsets
