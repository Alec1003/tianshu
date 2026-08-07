"""MILP 模型构建与求解。"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import pyomo.environ as pyo

from .models import (
    BaseData,
    FeatureData,
    ModelMetadata,
    Target,
    binomial_tail_probability,
    enumerate_alive_subsets,
    log,
    max_confident_hits_for_launch_cap,
    min_launches_for_confident_hits,
)



# ---------------------------------------------------------------------------
# 状态空间构建
# ---------------------------------------------------------------------------


@dataclass
class StateSpace:
    """枚举 AD 影响下的目标状态空间。

    每个目标的状态是所有 influencer 的存活组合的幂集。
    """

    influencer_by_target: dict[str, list[str]]
    state_ids_by_target: dict[str, list[str]]
    alive_subset_by_state: dict[tuple[str, str], tuple[str, ...]]
    impact_factor_by_state: dict[tuple[str, str], float]
    initial_state_by_target: dict[str, str]


def _build_state_space(
    target_ids: list[str],
    impact_matrix: dict[tuple[str, str], float],
    confidence_level: float,
) -> StateSpace:
    """为每个目标枚举所有 influencer 存活/死亡组合。

    Raises:
        ValueError: 如果某目标的 influencer 超过 12 个。
    """
    influencer_by_target: dict[str, list[str]] = {}
    state_ids_by_target: dict[str, list[str]] = {}
    alive_subset_by_state: dict[tuple[str, str], tuple[str, ...]] = {}
    impact_factor_by_state: dict[tuple[str, str], float] = {}
    initial_state_by_target: dict[str, str] = {}

    for target_id in target_ids:
        influencers = [
            other_id
            for other_id in target_ids
            if abs(impact_matrix.get((other_id, target_id), 1.0) - 1.0) > 1e-9
        ]
        if len(influencers) > 12:
            raise ValueError(
                f"Target {target_id} has {len(influencers)} impact sources; "
                "the current exact wave-state MILP would be too large."
            )
        influencer_by_target[target_id] = influencers
        state_ids = []
        for state_index, alive_subset in enumerate(
            enumerate_alive_subsets(influencers)
        ):
            state_id = f"s{state_index}"
            state_ids.append(state_id)
            alive_subset_by_state[(target_id, state_id)] = alive_subset
            factor = 1.0
            for influencer in influencers:
                raw = impact_matrix[(influencer, target_id)]
                if influencer in alive_subset:
                    factor *= raw
                else:
                    factor *= confidence_level + (1.0 - confidence_level) * raw
            impact_factor_by_state[(target_id, state_id)] = factor
            if tuple(influencers) == alive_subset:
                initial_state_by_target[target_id] = state_id
        state_ids_by_target[target_id] = state_ids
        if target_id not in initial_state_by_target:
            raise ValueError(
                f"Unable to identify initial alive state for target {target_id}"
            )
        log(
            f"  影响状态: target={target_id}, influencers={influencers}, "
            f"state_count={len(state_ids)}, initial_state={initial_state_by_target[target_id]}"
        )

    return StateSpace(
        influencer_by_target=influencer_by_target,
        state_ids_by_target=state_ids_by_target,
        alive_subset_by_state=alive_subset_by_state,
        impact_factor_by_state=impact_factor_by_state,
        initial_state_by_target=initial_state_by_target,
    )


# ---------------------------------------------------------------------------
# 置信命中层级预计算
# ---------------------------------------------------------------------------


@dataclass
class HitLevels:
    """武器-目标-波次-状态的置信命中层级预计算结果。"""

    damage_by_pair_wave: dict[tuple[str, str, int], float]
    hit_probability_by_choice: dict[tuple[str, str, int, str], float]
    level_options: dict[tuple[str, str, int, str], list[int]]
    launch_thresholds: dict[tuple[str, str, int, str, int], int]
    choice_index: list[tuple[str, str, int, str, int]]


def _precompute_hit_levels(
    pair_wave_index: list[tuple[str, str, int]],
    target_map: dict[str, Target],
    feature_data: FeatureData,
    base_data: dict[str, BaseData],
    state_ids_by_target: dict[str, list[str]],
    impact_factor_by_state: dict[tuple[str, str], float],
    hit_probability: float,
    confidence_level: float,
) -> HitLevels:
    """为每个 (weapon, target, wave, state) 预计算可达命中层级和对应发射门槛。"""
    damage_by_pair_wave: dict[tuple[str, str, int], float] = {}
    hit_probability_by_choice: dict[tuple[str, str, int, str], float] = {}
    level_options: dict[tuple[str, str, int, str], list[int]] = {}
    launch_thresholds: dict[tuple[str, str, int, str, int], int] = {}
    choice_index: list[tuple[str, str, int, str, int]] = []

    total_launch_cap = {
        weapon: sum(base.weapon_num.get(weapon, 0) for base in base_data.values())
        for weapon in feature_data.weapons
    }

    for weapon, target_id, wave in pair_wave_index:
        target = target_map[target_id]
        damage = feature_data.destroy[(target.target_type, weapon)]
        if damage <= 0:
            continue
        damage_by_pair_wave[(weapon, target_id, wave)] = damage
        desired_hits = math.ceil(target.damage_requirement_max / damage)
        pair_launch_cap = total_launch_cap[weapon]
        for state_id in state_ids_by_target[target_id]:
            impact_factor = impact_factor_by_state[(target_id, state_id)]
            base_probability = feature_data.hit_rate.get(
                (target.target_type, weapon), hit_probability
            )
            effective_probability = base_probability * impact_factor
            effective_probability = max(0.0, min(1.0, effective_probability))
            state_key = (weapon, target_id, wave, state_id)
            hit_probability_by_choice[state_key] = effective_probability
            if effective_probability <= 0 or pair_launch_cap <= 0:
                levels = [0]
            else:
                achievable_hits = max_confident_hits_for_launch_cap(
                    max_trials=pair_launch_cap,
                    probability=effective_probability,
                    confidence=confidence_level,
                )
                max_hits = min(desired_hits, achievable_hits)
                levels = list(range(max_hits + 1))
            level_options[state_key] = levels
            for level in levels:
                if level == 0:
                    threshold = 0
                else:
                    threshold = min_launches_for_confident_hits(
                        required_hits=level,
                        probability=effective_probability,
                        confidence=confidence_level,
                        max_trials=pair_launch_cap,
                    )
                launch_thresholds[(weapon, target_id, wave, state_id, level)] = (
                    threshold
                )
                choice_index.append((weapon, target_id, wave, state_id, level))

    return HitLevels(
        damage_by_pair_wave=damage_by_pair_wave,
        hit_probability_by_choice=hit_probability_by_choice,
        level_options=level_options,
        launch_thresholds=launch_thresholds,
        choice_index=choice_index,
    )


def build_model(
    feature_data: FeatureData,
    base_data: dict[str, BaseData],
    targets: list[Target],
    groups: dict[tuple[str, str], list[tuple[str, ...]]],
    wave_count: int,
    impact_matrix: dict[tuple[str, str], float],
    hit_probability: float,
    confidence_level: float,
) -> tuple[pyo.ConcreteModel, dict[str, Any]]:
    """构建 MILP 模型。

    建模思路：
    1. 把每个"基地-平台类型-合法目标组"视为一个聚合架次桶
    2. 在桶内分配武器到具体目标
    3. 通过挂点、库存、兼容性等约束限制分配
    4. 通过"置信命中层级"变量表达毁伤达标要求
    5. 目标函数最小化平台架次成本 + 武器使用成本

    confidence_level: 置信度，同时用于 confident-hit 门槛和 AD 影响因子 blend。
    """
    model = pyo.ConcreteModel("weapon_target_allocator")

    target_map = {target.target_id: target for target in targets}
    target_ids = [target.target_id for target in targets]
    base_ids = sorted(base_data.keys())
    waves = list(range(1, wave_count + 1))

    sp = _build_state_space(target_ids, impact_matrix, confidence_level)
    influencer_by_target = sp.influencer_by_target
    state_ids_by_target = sp.state_ids_by_target
    alive_subset_by_state = sp.alive_subset_by_state
    impact_factor_by_state = sp.impact_factor_by_state
    initial_state_by_target = sp.initial_state_by_target

    sorties: list[tuple[str, str, str, int]] = []
    group_targets: dict[tuple[str, str, str], tuple[str, ...]] = {}
    for base_id in base_ids:
        for platform in feature_data.platforms:
            if base_data[base_id].platform_num.get(platform, 0) <= 0:
                continue
            for index, target_group in enumerate(
                groups.get((base_id, platform), []), start=1
            ):
                group_id = f"{platform}_g{index}"
                group_targets[(base_id, platform, group_id)] = target_group
                for wave in waves:
                    sorties.append((base_id, platform, group_id, wave))

    if not sorties:
        raise ValueError("No feasible base-platform-target-group sorties are defined.")
    log(f"候选架次桶生成完成: sortie_buckets={len(sorties)}")

    x_index: list[tuple[str, str, str, str, str, int]] = []
    x_by_sortie_wave: dict[
        tuple[str, str, str, int], list[tuple[str, str, str, str, str, int]]
    ] = defaultdict(list)
    x_by_weapon_base: dict[
        tuple[str, str], list[tuple[str, str, str, str, str, int]]
    ] = defaultdict(list)
    launches_by_pair_wave: dict[
        tuple[str, str, int], list[tuple[str, str, str, str, str, int]]
    ] = defaultdict(list)
    launches_by_target_wave: dict[
        tuple[str, str, int], list[tuple[str, str, str, str, str, int]]
    ] = defaultdict(list)

    for base_id, platform, group_id, wave in sorties:
        for weapon in feature_data.weapons:
            if feature_data.compatibility.get((platform, weapon), 0) == 0:
                continue
            if base_data[base_id].weapon_num.get(weapon, 0) <= 0:
                continue
            for target_id in group_targets[(base_id, platform, group_id)]:
                target = target_map[target_id]
                damage = feature_data.destroy[(target.target_type, weapon)]
                if damage <= 0:
                    continue
                if (target_id, weapon) in feature_data.risk_excluded:
                    continue
                index = (base_id, platform, group_id, weapon, target_id, wave)
                x_index.append(index)
                x_by_sortie_wave[(base_id, platform, group_id, wave)].append(index)
                x_by_weapon_base[(base_id, weapon)].append(index)
                launches_by_pair_wave[(weapon, target_id, wave)].append(index)
                launches_by_target_wave[(target_id, wave)].append(index)

    if not x_index:
        raise ValueError(
            "No feasible (base, platform, group, weapon, target, wave) allocation arcs were generated."
        )
    log(f"可行分配弧生成完成: allocation_arcs={len(x_index)}")

    pair_wave_index: list[tuple[str, str, int]] = sorted(launches_by_pair_wave.keys())
    state_index = [
        (target_id, wave, state_id)
        for target_id in target_ids
        for wave in waves
        for state_id in state_ids_by_target[target_id]
    ]
    target_wave_index = [
        (target_id, wave) for target_id in target_ids for wave in waves
    ]

    hl = _precompute_hit_levels(
        pair_wave_index,
        target_map,
        feature_data,
        base_data,
        state_ids_by_target,
        impact_factor_by_state,
        hit_probability,
        confidence_level,
    )
    damage_by_pair_wave = hl.damage_by_pair_wave
    hit_probability_by_choice = hl.hit_probability_by_choice
    level_options = hl.level_options
    launch_thresholds = hl.launch_thresholds
    choice_index = hl.choice_index

    if not pair_wave_index:
        raise ValueError(
            "No weapon-target-wave pair can contribute positive damage under the current inputs."
        )
    log(f"武器-目标-波次对生成完成: pair_waves={len(pair_wave_index)}")

    model.SORTIES = pyo.Set(initialize=sorties, dimen=4)
    model.X_INDEX = pyo.Set(initialize=x_index, dimen=6)
    model.TARGET_WAVE = pyo.Set(initialize=target_wave_index, dimen=2)
    model.STATE_INDEX = pyo.Set(initialize=state_index, dimen=3)
    model.PAIR_WAVE = pyo.Set(initialize=pair_wave_index, dimen=3)
    model.CHOICE_INDEX = pyo.Set(initialize=choice_index, dimen=5)

    model.sorties_used = pyo.Var(model.SORTIES, domain=pyo.NonNegativeIntegers)
    model.launches = pyo.Var(model.X_INDEX, domain=pyo.NonNegativeIntegers)
    model.state_select = pyo.Var(model.STATE_INDEX, domain=pyo.Binary)
    model.hit_choice = pyo.Var(model.CHOICE_INDEX, domain=pyo.Binary)
    model.destroyed = pyo.Var(model.TARGET_WAVE, domain=pyo.Binary)

    model.SortieInventory = pyo.ConstraintList()
    for base_id, platform, group_id, wave in sorties:
        model.SortieInventory.add(
            model.sorties_used[(base_id, platform, group_id, wave)]
            <= base_data[base_id].platform_num[platform]
        )

    model.PlatformInventory = pyo.ConstraintList()
    for base_id in base_ids:
        for platform in feature_data.platforms:
            relevant_sorties = [
                sortie
                for sortie in sorties
                if sortie[0] == base_id and sortie[1] == platform
            ]
            if not relevant_sorties:
                continue
            # 平台不可跨波复用，因此所有波次累计出动架次不能超过库存。
            model.PlatformInventory.add(
                sum(model.sorties_used[sortie] for sortie in relevant_sorties)
                <= base_data[base_id].platform_num[platform]
            )

    model.HardpointLimit = pyo.ConstraintList()
    model.SortiePresence = pyo.ConstraintList()
    for sortie in sorties:
        base_id, platform, group_id, wave = sortie
        relevant_x = x_by_sortie_wave.get(sortie, [])
        if not relevant_x:
            model.HardpointLimit.add(model.sorties_used[sortie] == 0)
            continue
        model.HardpointLimit.add(
            sum(
                feature_data.weapon_hardpoint_cost[index[3]] * model.launches[index]
                for index in relevant_x
            )
            <= feature_data.platform_loadout[platform] * model.sorties_used[sortie]
        )
        # 有发射就必须有架次: Σ launches <= M * sorties_used
        max_launches_for_bucket = sum(
            base_data[base_id].weapon_num.get(index[3], 0) for index in relevant_x
        )
        if max_launches_for_bucket > 0:
            model.SortiePresence.add(
                sum(model.launches[index] for index in relevant_x)
                <= max_launches_for_bucket * model.sorties_used[sortie]
            )

    model.WeaponInventory = pyo.ConstraintList()
    for base_id in base_ids:
        for weapon in feature_data.weapons:
            relevant_x = x_by_weapon_base.get((base_id, weapon), [])
            if not relevant_x:
                continue
            model.WeaponInventory.add(
                sum(model.launches[index] for index in relevant_x)
                <= base_data[base_id].weapon_num[weapon]
            )

    model.StateChoice = pyo.ConstraintList()
    for target_id in target_ids:
        for wave in waves:
            state_ids = state_ids_by_target[target_id]
            model.StateChoice.add(
                sum(
                    model.state_select[(target_id, wave, state_id)]
                    for state_id in state_ids
                )
                == 1
            )
            if wave == 1:
                initial_state = initial_state_by_target[target_id]
                model.StateChoice.add(
                    model.state_select[(target_id, wave, initial_state)] == 1
                )
            else:
                for influencer in influencer_by_target[target_id]:
                    relevant_states = [
                        state_id
                        for state_id in state_ids
                        if influencer in alive_subset_by_state[(target_id, state_id)]
                    ]
                    model.StateChoice.add(
                        sum(
                            model.state_select[(target_id, wave, state_id)]
                            for state_id in relevant_states
                        )
                        == 1 - model.destroyed[(influencer, wave - 1)]
                    )

    model.HitLevelChoice = pyo.ConstraintList()
    for weapon, target_id, wave in pair_wave_index:
        state_ids = state_ids_by_target[target_id]
        model.HitLevelChoice.add(
            sum(
                model.hit_choice[(weapon, target_id, wave, state_id, level)]
                for state_id in state_ids
                for level in level_options[(weapon, target_id, wave, state_id)]
            )
            == 1
        )
        for state_id in state_ids:
            model.HitLevelChoice.add(
                sum(
                    model.hit_choice[(weapon, target_id, wave, state_id, level)]
                    for level in level_options[(weapon, target_id, wave, state_id)]
                )
                == model.state_select[(target_id, wave, state_id)]
            )

    model.ConfidentHitSupport = pyo.ConstraintList()
    for weapon, target_id, wave in pair_wave_index:
        relevant_x = launches_by_pair_wave[(weapon, target_id, wave)]
        model.ConfidentHitSupport.add(
            sum(model.launches[index] for index in relevant_x)
            >= sum(
                launch_thresholds[(weapon, target_id, wave, state_id, level)]
                * model.hit_choice[(weapon, target_id, wave, state_id, level)]
                for state_id in state_ids_by_target[target_id]
                for level in level_options[(weapon, target_id, wave, state_id)]
            )
        )

    max_damage_by_target: dict[str, float] = {}
    max_launches_to_target_wave: dict[tuple[str, int], int] = {}
    for target in targets:
        upper_bound = 0.0
        for weapon in feature_data.weapons:
            upper_bound += sum(
                base.weapon_num.get(weapon, 0) for base in base_data.values()
            ) * feature_data.destroy.get((target.target_type, weapon), 0.0)
        max_damage_by_target[target.target_id] = max(
            upper_bound, target.damage_requirement_max, target.loss_air_defense_damage
        )
        for wave in waves:
            max_launches_to_target_wave[(target.target_id, wave)] = sum(
                base.weapon_num.get(weapon, 0)
                for base in base_data.values()
                for weapon in feature_data.weapons
                if feature_data.destroy.get((target.target_type, weapon), 0.0) > 0
            )

    epsilon = 1e-6
    model.DestroyedTransition = pyo.ConstraintList()
    model.FinalDamageRange = pyo.ConstraintList()
    model.NoPostKillAttack = pyo.ConstraintList()
    for target in targets:
        target_id = target.target_id
        for wave in waves:
            cumulative_damage_expr = sum(
                damage_by_pair_wave[(weapon, pair_target_id, pair_wave)]
                * level
                * model.hit_choice[(weapon, pair_target_id, pair_wave, state_id, level)]
                for weapon, pair_target_id, pair_wave in pair_wave_index
                if pair_target_id == target_id and pair_wave <= wave
                for state_id in state_ids_by_target[target_id]
                for level in level_options[(weapon, target_id, pair_wave, state_id)]
            )
            model.DestroyedTransition.add(
                cumulative_damage_expr
                >= target.loss_air_defense_damage * model.destroyed[(target_id, wave)]
            )
            model.DestroyedTransition.add(
                cumulative_damage_expr
                <= (target.loss_air_defense_damage - epsilon)
                + max_damage_by_target[target_id] * model.destroyed[(target_id, wave)]
            )
            if wave > 1:
                model.DestroyedTransition.add(
                    model.destroyed[(target_id, wave - 1)]
                    <= model.destroyed[(target_id, wave)]
                )
                relevant_x = launches_by_target_wave.get((target_id, wave), [])
                if relevant_x:
                    model.NoPostKillAttack.add(
                        sum(model.launches[index] for index in relevant_x)
                        <= max_launches_to_target_wave[(target_id, wave)]
                        * (1 - model.destroyed[(target_id, wave - 1)])
                    )
        final_cumulative_damage_expr = sum(
            damage_by_pair_wave[(weapon, pair_target_id, pair_wave)]
            * level
            * model.hit_choice[(weapon, pair_target_id, pair_wave, state_id, level)]
            for weapon, pair_target_id, pair_wave in pair_wave_index
            if pair_target_id == target_id
            for state_id in state_ids_by_target[target_id]
            for level in level_options[(weapon, target_id, pair_wave, state_id)]
        )
        model.FinalDamageRange.add(
            final_cumulative_damage_expr >= target.damage_requirement_min
        )
        model.FinalDamageRange.add(
            final_cumulative_damage_expr <= target.damage_requirement_max
        )
    model.TotalCost = pyo.Objective(
        expr=sum(
            base_data[base_id].platform_cost[platform]
            * model.sorties_used[(base_id, platform, group_id, wave)]
            for base_id, platform, group_id, wave in sorties
        )
        + sum(
            base_data[index[0]].weapon_cost[index[3]] * model.launches[index]
            for index in x_index
        ),
        sense=pyo.minimize,
    )

    log(
        "模型构建完成: "
        f"sortie_vars={len(list(model.SORTIES))}, "
        f"launch_vars={len(list(model.X_INDEX))}, "
        f"state_vars={len(list(model.STATE_INDEX))}, "
        f"hit_choice_vars={len(list(model.CHOICE_INDEX))}, "
        f"destroyed_vars={len(list(model.TARGET_WAVE))}"
    )
    log(
        "约束规模: "
        f"sortie_inventory={len(model.SortieInventory)}, "
        f"platform_inventory={len(model.PlatformInventory)}, "
        f"hardpoint={len(model.HardpointLimit)}, "
        f"sortie_presence={len(model.SortiePresence)}, "
        f"weapon_inventory={len(model.WeaponInventory)}, "
        f"state_choice={len(model.StateChoice)}, "
        f"hit_level_choice={len(model.HitLevelChoice)}, "
        f"confident_hit_support={len(model.ConfidentHitSupport)}, "
        f"destroyed_transition={len(model.DestroyedTransition)}, "
        f"final_damage_range={len(model.FinalDamageRange)}, "
        f"no_post_kill_attack={len(model.NoPostKillAttack)}"
    )

    metadata = ModelMetadata(
        sorties=sorties,
        group_targets=group_targets,
        targets=targets,
        waves=waves,
        pair_wave_index=pair_wave_index,
        state_ids_by_target=state_ids_by_target,
        alive_subset_by_state=alive_subset_by_state,
        impact_factor_by_state=impact_factor_by_state,
        level_options=level_options,
        damage_by_pair_wave=damage_by_pair_wave,
        hit_probability_by_choice=hit_probability_by_choice,
        launch_thresholds=launch_thresholds,
        influencer_by_target=influencer_by_target,
    )
    return model, metadata


def ensure_feasible_coverage(
    feature_data: FeatureData,
    base_data: dict[str, BaseData],
    targets: list[Target],
    groups: dict[tuple[str, str], list[tuple[str, ...]]],
) -> None:
    """在建模前做一轮快速可达性检查。

    如果某个目标根本没有任何"基地-平台-武器-目标组"组合能覆盖到，
    就尽早报错，而不是把不可行性留给求解器。
    """
    coverable_targets: set[str] = set()
    for target in targets:
        for (base_id, platform), group_list in groups.items():
            if base_data[base_id].platform_num.get(platform, 0) <= 0:
                continue
            for group in group_list:
                if target.target_id not in group:
                    continue
                for weapon in feature_data.weapons:
                    if base_data[base_id].weapon_num.get(weapon, 0) <= 0:
                        continue
                    if feature_data.compatibility.get((platform, weapon), 0) == 0:
                        continue
                    if feature_data.destroy[(target.target_type, weapon)] > 0:
                        coverable_targets.add(target.target_id)
                        break
    missing_targets = sorted(
        target.target_id
        for target in targets
        if target.target_id not in coverable_targets
    )
    if missing_targets:
        raise ValueError(
            f"Targets are not coverable under current groups/inventory: {missing_targets}"
        )
    log(f"可达性检查通过: coverable_targets={sorted(coverable_targets)}")


def solve_model(model: pyo.ConcreteModel) -> pyo.results.results_.SolverResults:
    """调用 HiGHS 求解模型。mip_gap=0 要求证明到最优。"""
    solver = pyo.SolverFactory("appsi_highs")
    if solver is None or not solver.available(False):
        raise RuntimeError(
            "Pyomo HiGHS solver is unavailable. Ensure 'highspy' is installed in the active environment."
        )
    solver.config.mip_gap = 0.0  # 必须证明到最优，不提前退出
    log("开始调用 HiGHS 求解 MILP")
    try:
        results = solver.solve(model)
    except RuntimeError as exc:
        raise RuntimeError(
            "MILP 未找到可行解。请优先检查目标毁伤区间是否过窄、"
            "loss_air_defense_damage 是否与波次/平台数量冲突、以及 HIT_RATE_IMPACT 是否过强。"
        ) from exc
    log(
        f"求解完成: status={results.solver.status}, "
        f"termination={results.solver.termination_condition}"
    )
    return results
