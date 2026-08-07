#!/usr/bin/env python3
"""Monte Carlo 仿真：验证 MILP 武器-目标分配方案在随机命中下的表现。

仿真逻辑
========
1. 从 plan.json 读取 MILP 解
2. 逐波次执行发射计划，每次命中为 Bernoulli 试验（用 Binomial 向量化）
3. 波次间命中率根据 HIT_RATE_IMPACT 动态更新：
   - 若影响源目标在上一波被摧毁 → 本波移除其命中率折扣
4. 统计各目标的毁伤分布、达标概率、防空摧毁概率

关键验证指标
============
- P(毁伤达标) vs MILP 设定的 CONFIDENCE_LEVEL：若 MILP 正确，达标率应接近或超过置信度
- 毁伤分布：观察 mean / P5 / P95 与 MILP 确定性毁伤的偏差
- 联合达标率：所有目标同时满足毁伤区间的概率

用法
====
    .venv/bin/python monte_carlo.py --trials 10000 --seed 42
    .venv/bin/python monte_carlo.py --trials 50000 --output-dir output --config scenario.json --plan output/plan.json
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .models import (
    BaseData,
    FeatureData,
    Target,
    load_base_data,
    load_base_yaml,
    load_feature_data,
    load_feature_yaml,
    load_scenario_yaml,
    load_wave_parameters,
    log,
    validate_config,
)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class LaunchInstruction:
    """单条聚合后的发射指令：某波次用某武器向某目标发射多少枚。"""

    wave: int
    weapon: str
    target_id: str
    count: int


@dataclass
class Plan:
    """从 CSV 加载的 MILP 方案。"""

    launches: list[LaunchInstruction]  # 所有发射指令
    wave_count: int
    total_platform_cost: float
    total_weapon_cost: float
    total_cost: float

    def launches_by_wave(self) -> dict[int, list[LaunchInstruction]]:
        grouped: dict[int, list[LaunchInstruction]] = defaultdict(list)
        for li in self.launches:
            grouped[li.wave].append(li)
        return dict(grouped)


@dataclass
class TrialResult:
    """单次仿真的结果。"""

    final_damage: dict[str, float]  # target_id → 最终累计毁伤
    destroyed_wave: dict[str, Optional[int]]  # target_id → 被摧毁波次 (None = 存活)
    requirements_met: dict[str, bool]  # target_id → 是否达标
    all_met: bool


# ---------------------------------------------------------------------------
# 方案加载
# ---------------------------------------------------------------------------


def load_plan(path: Path) -> Plan:
    """从 plan.json 读取 MILP 方案。"""
    plan_path = path

    if not plan_path.exists():
        raise FileNotFoundError(
            f"未找到方案文件: {plan_path}。请先运行 allocator.py 生成 plan.json。"
        )

    with plan_path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)

    sorties = payload.get("sorties", [])
    launches = payload.get("launches", [])
    summary = payload.get("summary", {})

    total_platform_cost = sum(
        int(item["count"]) * float(item["platform_cost_per_sortie"])
        for item in sorties
    )
    total_weapon_cost = sum(
        int(item["count"]) * float(item["weapon_cost_per_round"])
        for item in launches
    )
    launch_instructions = [
        LaunchInstruction(
            wave=int(item["wave"]),
            weapon=item["weapon"],
            target_id=str(item["target_id"]),
            count=int(item["count"]),
        )
        for item in launches
        if item.get("weapon") and int(item.get("count", 0)) > 0
    ]

    wave_count = int(
        summary.get(
            "wave_count",
            max((li.wave for li in launch_instructions), default=1),
        )
    )

    plan = Plan(
        launches=launch_instructions,
        wave_count=wave_count,
        total_platform_cost=total_platform_cost,
        total_weapon_cost=total_weapon_cost,
        total_cost=total_platform_cost + total_weapon_cost,
    )
    log(
        f"方案加载完成: waves={plan.wave_count}, launch_groups={len(plan.launches)}, "
        f"total_cost={plan.total_cost:.4f}"
    )
    return plan


# ---------------------------------------------------------------------------
# 仿真器
# ---------------------------------------------------------------------------


class MonteCarloSimulator:
    """执行 Monte Carlo 仿真。

    核心状态转移
    ----------
    - 每波开始：根据上一波末的存活状态计算有效命中率
    - 每波内：对发射指令做 Binomial(n, p_eff) 抽样 → 累加毁伤
    - 每波末：检查累计毁伤 ≥ loss_air_defense_damage → 标记摧毁
    - 同波内命中率不变（与 MILP 的 same-wave 假设一致）
    """

    def __init__(
        self,
        feature_data: FeatureData,
        targets: list[Target],
        impact_matrix: dict[tuple[str, str], float],
        plan: Plan,
        hit_probability_fallback: float,
    ):
        self.feature_data = feature_data
        self.targets = targets
        self.target_map: dict[str, Target] = {t.target_id: t for t in targets}
        self.target_ids = [t.target_id for t in targets]
        self.impact_matrix = impact_matrix
        self.plan = plan
        self.hit_probability_fallback = hit_probability_fallback

        # 预计算不变量
        self._waves = list(range(1, plan.wave_count + 1))
        self._launches_by_wave = plan.launches_by_wave()

        # 每个目标的影响源列表
        self._influencers: dict[str, list[str]] = {}
        for target in targets:
            self._influencers[target.target_id] = [
                other_id
                for other_id in self.target_ids
                if abs(impact_matrix.get((other_id, target.target_id), 1.0) - 1.0)
                > 1e-9
            ]

        # 基础命中率缓存: (weapon, target_type) → base_probability
        self._base_hit_prob: dict[tuple[str, str], float] = {}
        for target in targets:
            for weapon in feature_data.weapons:
                key = (weapon, target.target_type)
                self._base_hit_prob[key] = feature_data.hit_rate.get(
                    (target.target_type, weapon), hit_probability_fallback
                )

        # 对每个波次，预聚合发射指令: (weapon, target_id, wave) → total_count
        self._launch_groups: dict[tuple[str, str, int], int] = defaultdict(int)
        for li in plan.launches:
            self._launch_groups[(li.weapon, li.target_id, li.wave)] += li.count

        # 只保留有发射的 (weapon, target, wave) 组合
        self._active_pairs: list[tuple[str, str, int]] = sorted(
            self._launch_groups.keys()
        )

    # ------------------------------------------------------------------
    # 命中率计算（依赖当前波次的存活状态）
    # ------------------------------------------------------------------

    def _compute_effective_probs(
        self, destroyed: dict[str, bool]
    ) -> dict[tuple[str, str], float]:
        """根据当前存活状态计算每种 (weapon, target_id) 的有效命中率。

        有效命中率 = 基础命中率 × Π(impact[influencer, target] for influencer in alive)
        """
        probs: dict[tuple[str, str], float] = {}
        for target in self.targets:
            tid = target.target_id
            # 计算影响因子乘积
            impact_factor = 1.0
            for influencer in self._influencers[tid]:
                if not destroyed.get(influencer, False):
                    impact_factor *= self.impact_matrix.get((influencer, tid), 1.0)
            for weapon in self.feature_data.weapons:
                base_p = self._base_hit_prob.get((weapon, target.target_type), 0.0)
                eff_p = base_p * impact_factor
                eff_p = max(0.0, min(1.0, eff_p))
                probs[(weapon, tid)] = eff_p
        return probs

    # ------------------------------------------------------------------
    # 单次试验
    # ------------------------------------------------------------------

    def run_trial(self, rng: np.random.Generator) -> TrialResult:
        """执行一次 Monte Carlo 试验。"""
        cumulative: dict[str, float] = {t.target_id: 0.0 for t in self.targets}
        destroyed: dict[str, bool] = {t.target_id: False for t in self.targets}
        destroyed_wave: dict[str, Optional[int]] = {
            t.target_id: None for t in self.targets
        }

        for wave in self._waves:
            # 波次开始：计算当前有效命中率
            eff_probs = self._compute_effective_probs(destroyed)

            # 执行本波的发射指令
            for wpn, tid, w in self._active_pairs:
                if w != wave:
                    continue
                n = self._launch_groups[(wpn, tid, w)]
                if n <= 0:
                    continue
                p = eff_probs.get((wpn, tid), 0.0)
                if p <= 0:
                    continue
                target_type = self.target_map[tid].target_type
                dmg_per_round = self.feature_data.destroy.get((target_type, wpn), 0.0)
                hits = rng.binomial(n, p)
                cumulative[tid] += hits * dmg_per_round

            # 波次结束：更新摧毁状态
            for target in self.targets:
                tid = target.target_id
                if (
                    not destroyed[tid]
                    and cumulative[tid] >= target.loss_air_defense_damage
                ):
                    destroyed[tid] = True
                    destroyed_wave[tid] = wave

        # 检查毁伤达标
        requirements_met: dict[str, bool] = {}
        for target in self.targets:
            dmg = cumulative[target.target_id]
            requirements_met[target.target_id] = (
                target.damage_requirement_min <= dmg <= target.damage_requirement_max
            )

        all_met = all(requirements_met.values())

        return TrialResult(
            final_damage=cumulative,
            destroyed_wave=destroyed_wave,
            requirements_met=requirements_met,
            all_met=all_met,
        )

    # ------------------------------------------------------------------
    # 批量仿真
    # ------------------------------------------------------------------

    def run(self, n_trials: int, seed: int = 0) -> list[TrialResult]:
        """运行 n_trials 次 Monte Carlo 试验。"""
        rng = np.random.default_rng(seed)
        results: list[TrialResult] = []
        t_start = time.perf_counter()

        for i in range(n_trials):
            results.append(self.run_trial(rng))
            # 每 10% 打印进度
            if n_trials >= 10 and (i + 1) % max(1, n_trials // 10) == 0:
                pct = (i + 1) / n_trials * 100
                elapsed = time.perf_counter() - t_start
                eta = elapsed / (i + 1) * (n_trials - i - 1)
                log(
                    f"  仿真进度: {i + 1}/{n_trials} ({pct:.0f}%) 已耗时={elapsed:.1f}s 预计剩余={eta:.1f}s"
                )

        elapsed = time.perf_counter() - t_start
        log(
            f"仿真完成: trials={n_trials}, 总耗时={elapsed:.2f}s, 平均={elapsed / n_trials * 1e3:.2f}ms/trial"
        )
        return results


# ---------------------------------------------------------------------------
# 统计计算
# ---------------------------------------------------------------------------


@dataclass
class TargetStats:
    """单个目标的仿真统计。"""

    target_id: str
    target_type: str
    damage_min: float
    damage_max: float
    loss_air_defense: float
    planned_attacks: int  # MILP 方案中对该目标的发射总量
    p_requirement_met: float
    mean_damage: float
    std_damage: float
    p5_damage: float
    p50_damage: float
    p95_damage: float
    min_damage: float
    max_damage: float
    p_destroyed: float
    mean_destroyed_wave: Optional[float]  # 平均被摧毁波次 (only for destroyed trials)


@dataclass
class SimulationStats:
    """完整的仿真统计。"""

    n_trials: int
    plan_cost: float
    p_all_met: float
    per_target: dict[str, TargetStats]
    confidence_level: float  # MILP 设定的置信度（用于对比）


def compute_statistics(
    results: list[TrialResult],
    targets: list[Target],
    plan: Plan,
    confidence_level: float,
) -> SimulationStats:
    """从仿真结果计算统计指标。"""
    n = len(results)
    target_ids = [t.target_id for t in targets]

    # 各目标的发射总量
    launches_by_target: dict[str, int] = defaultdict(int)
    for li in plan.launches:
        launches_by_target[li.target_id] += li.count

    per_target: dict[str, TargetStats] = {}
    for target in targets:
        tid = target.target_id
        damages = np.array([r.final_damage[tid] for r in results])
        met = np.array([r.requirements_met[tid] for r in results], dtype=bool)
        destroyed_waves = [r.destroyed_wave[tid] for r in results]
        destroyed_count = sum(1 for w in destroyed_waves if w is not None)

        dw_numeric = [w for w in destroyed_waves if w is not None]
        mean_dw = float(np.mean(dw_numeric)) if dw_numeric else None

        per_target[tid] = TargetStats(
            target_id=tid,
            target_type=target.target_type,
            damage_min=target.damage_requirement_min,
            damage_max=target.damage_requirement_max,
            loss_air_defense=target.loss_air_defense_damage,
            planned_attacks=launches_by_target.get(tid, 0),
            p_requirement_met=float(np.mean(met)),
            mean_damage=float(np.mean(damages)),
            std_damage=float(np.std(damages)),
            p5_damage=float(np.percentile(damages, 5)),
            p50_damage=float(np.percentile(damages, 50)),
            p95_damage=float(np.percentile(damages, 95)),
            min_damage=float(np.min(damages)),
            max_damage=float(np.max(damages)),
            p_destroyed=destroyed_count / n,
            mean_destroyed_wave=mean_dw,
        )

    p_all_met = float(np.mean([r.all_met for r in results]))

    return SimulationStats(
        n_trials=n,
        plan_cost=plan.total_cost,
        p_all_met=p_all_met,
        per_target=per_target,
        confidence_level=confidence_level,
    )


# ---------------------------------------------------------------------------
# 报告输出
# ---------------------------------------------------------------------------


def print_report(
    stats: SimulationStats, milp_damages: Optional[dict[str, float]] = None
) -> None:
    """在终端打印仿真统计报告。"""
    print()
    print("=" * 90)
    print("  Monte Carlo 仿真报告")
    print("=" * 90)
    print(f"  试验次数:         {stats.n_trials:,}")
    print(f"  方案总成本:       {stats.plan_cost:,.2f}")
    print(f"  MILP 置信度设置:  {stats.confidence_level:.2f}")
    print(f"  联合达标率:       {stats.p_all_met:.4f}  ({stats.p_all_met * 100:.1f}%)")
    if stats.p_all_met < stats.confidence_level:
        delta = stats.confidence_level - stats.p_all_met
        print(f"  ⚠ 联合达标率低于 MILP 置信度 {delta:.4f}，方案可能不够保守")
    print()
    header = (
        f"  {'目标':>6} {'类型':>5} {'毁伤区间':>14} {'发射':>6} "
        f"{'达标率':>10} {'均值':>9} {'标准差':>8} {'P5':>9} "
        f"{'P50':>9} {'P95':>9} {'摧毁率':>8} {'摧毁波次':>7}"
    )
    print(header)
    print("  " + "-" * len(header))

    for target_id in sorted(stats.per_target.keys(), key=lambda x: (x.isdigit(), x)):
        ts = stats.per_target[target_id]
        dw_str = (
            f"{ts.mean_destroyed_wave:.1f}"
            if ts.mean_destroyed_wave is not None
            else "N/A"
        )
        range_str = f"[{ts.damage_min:.1f},{ts.damage_max:.1f}]"
        met_str = f"{ts.p_requirement_met:.4f}{' v' if ts.p_requirement_met >= stats.confidence_level else ' x'}"
        print(
            f"  {ts.target_id:>6} {ts.target_type:>5} {range_str:>14} {ts.planned_attacks:>6d} "
            f"{met_str:>10} {ts.mean_damage:>9.4f} {ts.std_damage:>8.4f} "
            f"{ts.p5_damage:>9.4f} {ts.p50_damage:>9.4f} {ts.p95_damage:>9.4f} "
            f"{ts.p_destroyed:>8.4f} {dw_str:>7}"
        )

    print()
    print(f"  v = 该目标达标率 >= MILP 置信度 ({stats.confidence_level:.2f})")
    print(f"  x = 该目标达标率 < MILP 置信度 — 方案对该目标的风险可能被低估")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Monte Carlo 仿真：验证 MILP 武器-目标分配方案"
    )
    parser.add_argument(
        "--trials", type=int, default=10_000, help="仿真试验次数 (默认 10000)"
    )
    parser.add_argument("--seed", type=int, default=42, help="随机种子 (默认 42)")
    parser.add_argument(
        "--config", default="wta/input/scenario.yaml", help="场景配置路径，支持 YAML/JSON"
    )
    parser.add_argument("--plan", default=None, help="分配方案文件路径（plan.json）")
    parser.add_argument(
        "--output", default="output/mc_result.json", help="MC 结果 JSON 输出路径"
    )
    args = parser.parse_args()

    log("Monte Carlo 仿真启动")

    # 1. 加载方案
    output_path = Path(args.output).resolve()
    plan_path = Path(args.plan).resolve() if args.plan else (output_path.parent / "plan.json")
    plan = load_plan(plan_path)

    # 2. 加载问题数据
    from .config_loader import load_config

    config_path = Path(args.config).resolve()

    # 加载默认配置
    import yaml as _yaml
    defaults_path = Path(__file__).resolve().parent / "input" / "_defaults.yaml"
    defaults = _yaml.safe_load(defaults_path.read_text(encoding="utf-8")) if defaults_path.exists() else {}

    cfg = load_config(config_path, defaults)

    # 3. 构建仿真器
    simulator = MonteCarloSimulator(
        feature_data=cfg.feature_data,
        targets=cfg.targets,
        impact_matrix=cfg.impact_matrix,
        plan=plan,
        hit_probability_fallback=cfg.hit_probability,
    )

    # 4. 运行仿真
    log(f"开始仿真: trials={args.trials}, seed={args.seed}")
    results = simulator.run(n_trials=args.trials, seed=args.seed)

    # 5. 统计与报告
    stats = compute_statistics(
        results,
        cfg.targets,
        plan,
        confidence_level=cfg.confidence_level,
    )
    print_report(stats)

    # 6. 导出 JSON
    per_target = []
    for tid in sorted(stats.per_target.keys(), key=lambda x: (x.isdigit(), x)):
        ts = stats.per_target[tid]
        per_target.append(
            {
                "target_id": ts.target_id,
                "target_type": ts.target_type,
                "damage_min": ts.damage_min,
                "damage_max": ts.damage_max,
                "loss_air_defense": ts.loss_air_defense,
                "planned_launches": ts.planned_attacks,
                "p_requirement_met": ts.p_requirement_met,
                "mean_damage": ts.mean_damage,
                "std_damage": ts.std_damage,
                "p5_damage": ts.p5_damage,
                "p50_damage": ts.p50_damage,
                "p95_damage": ts.p95_damage,
                "min_damage": ts.min_damage,
                "max_damage": ts.max_damage,
                "p_destroyed": ts.p_destroyed,
                "mean_destroyed_wave": ts.mean_destroyed_wave,
            }
        )
    mc_result = {
        "p_all_met": stats.p_all_met,
        "n_trials": stats.n_trials,
        "plan_cost": stats.plan_cost,
        "confidence_level": stats.confidence_level,
        "per_target": per_target,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(mc_result, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"结果已导出: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
