"""武器-目标分配优化 — 单次 MILP + MC 验证。

AD 影响因子的 (1-c) 残留体现已被编码进 MILP 内部，无需两阶段迭代。
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import pyomo.environ as pyo

from .models import (
    BaseData,
    FeatureData,
    ModelMetadata,
    Target,
    log,
)
from .milp_core import build_model, solve_model
from .monte_carlo import (
    LaunchInstruction,
    MonteCarloSimulator,
    Plan,
    compute_statistics,
    print_report,
)



# ---------------------------------------------------------------------------
# 结果导出
# ---------------------------------------------------------------------------


def _build_plan_from_model(
    model: pyo.ConcreteModel,
    metadata: ModelMetadata,
    base_data: dict[str, BaseData],
) -> Plan:
    """从已求解的 Pyomo 模型构建 Plan 对象。"""
    instructions: list[LaunchInstruction] = []
    total_weapon_cost = 0.0
    for index in model.X_INDEX:
        val = pyo.value(model.launches[index])
        if not val or int(round(val)) <= 0:
            continue
        base_id, _platform, _group_id, weapon, target_id, wave = index
        count = int(round(val))
        instructions.append(
            LaunchInstruction(
                wave=int(wave),
                weapon=weapon,
                target_id=target_id,
                count=count,
            )
        )
        total_weapon_cost += count * base_data[base_id].weapon_cost.get(weapon, 0)

    total_platform_cost = 0.0
    for base_id, platform, group_id, wave in metadata.sorties:
        sv = pyo.value(model.sorties_used[(base_id, platform, group_id, wave)])
        if sv and int(round(sv)) > 0:
            total_platform_cost += int(round(sv)) * base_data[
                base_id
            ].platform_cost.get(platform, 0)

    return Plan(
        launches=instructions,
        wave_count=max((li.wave for li in instructions), default=1),
        total_platform_cost=total_platform_cost,
        total_weapon_cost=total_weapon_cost,
        total_cost=float(pyo.value(model.TotalCost)),
    )


def _mc_validate_plan(
    model: pyo.ConcreteModel,
    metadata: ModelMetadata,
    feature_data: FeatureData,
    base_data: dict[str, BaseData],
    targets: list[Target],
    impact_matrix: dict[tuple[str, str], float],
    hit_probability: float,
    confidence_level: float,
    n_trials: int,
    seed: int = 42,
):
    """从 model 构建 Plan，运行 MC 仿真，输出毁伤评估。"""
    plan = _build_plan_from_model(model, metadata, base_data)

    simulator = MonteCarloSimulator(
        feature_data=feature_data,
        targets=targets,
        impact_matrix=impact_matrix,
        plan=plan,
        hit_probability_fallback=hit_probability,
    )
    results = simulator.run(n_trials=n_trials, seed=seed)

    stats = compute_statistics(results, targets, plan, confidence_level)
    print_report(stats)
    return stats


def export_results(
    output_dir: Path,
    model: pyo.ConcreteModel,
    metadata: ModelMetadata,
    feature_data: FeatureData,
    base_data: dict[str, BaseData],
) -> dict[str, Any]:
    """导出 plan.json，并返回结构化方案。"""
    output_dir.mkdir(parents=True, exist_ok=True)

    sorties: list[dict[str, Any]] = []
    for base_id, platform, group_id, wave in metadata.sorties:
        value = pyo.value(model.sorties_used[(base_id, platform, group_id, wave)])
        if value and int(round(value)) > 0:
            sorties.append(
                {
                    "base_id": base_id,
                    "platform": platform,
                    "group_id": group_id,
                    "wave": int(wave),
                    "targets": list(
                        metadata.group_targets[(base_id, platform, group_id)]
                    ),
                    "count": int(round(value)),
                    "platform_cost_per_sortie": base_data[base_id].platform_cost[
                        platform
                    ],
                }
            )

    launches: list[dict[str, Any]] = []
    for index in model.X_INDEX:
        value = pyo.value(model.launches[index])
        if value and int(round(value)) > 0:
            base_id, platform, group_id, weapon, target_id, wave = index
            launches.append(
                {
                    "base_id": base_id,
                    "platform": platform,
                    "group_id": group_id,
                    "wave": int(wave),
                    "weapon": weapon,
                    "target_id": target_id,
                    "count": int(round(value)),
                    "weapon_cost_per_round": base_data[base_id].weapon_cost[weapon],
                }
            )

    total_platform_cost = sum(
        item["count"] * item["platform_cost_per_sortie"] for item in sorties
    )
    total_weapon_cost = sum(
        item["count"] * item["weapon_cost_per_round"] for item in launches
    )
    payload = {
        "summary": {
            "wave_count": len(metadata.waves),
            "total_platform_cost": total_platform_cost,
            "total_weapon_cost": total_weapon_cost,
            "total_cost": total_platform_cost + total_weapon_cost,
        },
        "sorties": sorted(
            sorties,
            key=lambda item: (
                item["base_id"],
                item["platform"],
                item["group_id"],
                item["wave"],
            ),
        ),
        "launches": sorted(
            launches,
            key=lambda item: (
                item["wave"],
                item["base_id"],
                item["platform"],
                item["group_id"],
                item["weapon"],
                item["target_id"],
            ),
        ),
    }
    (output_dir / "plan.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


# ---------------------------------------------------------------------------
# 终端打印
# ---------------------------------------------------------------------------


def print_detailed_results(
    model: pyo.ConcreteModel,
    metadata: ModelMetadata,
    base_data: dict[str, BaseData],
) -> None:
    """在终端打印详细求解结果。"""
    print("sorties:")
    has_sortie = False
    for base_id, platform, group_id, wave in metadata.sorties:
        value = pyo.value(model.sorties_used[(base_id, platform, group_id, wave)])
        rounded_value = int(round(value or 0))
        if rounded_value > 0:
            has_sortie = True
            targets = ",".join(metadata.group_targets[(base_id, platform, group_id)])
            print(
                f"  wave={wave} base={base_id} platform={platform} group={group_id} "
                f"targets=[{targets}] sorties={int(round(value))} "
                f"platform_cost={base_data[base_id].platform_cost[platform]:.2f}"
            )
    if not has_sortie:
        print("  none")

    print("launches:")
    has_launch = False
    for index in model.X_INDEX:
        value = pyo.value(model.launches[index])
        rounded_value = int(round(value or 0))
        if rounded_value > 0:
            has_launch = True
            base_id, platform, group_id, weapon, target_id, wave = index
            print(
                f"  wave={wave} base={base_id} platform={platform} group={group_id} "
                f"weapon={weapon} target={target_id} launches={rounded_value} "
                f"weapon_cost={base_data[base_id].weapon_cost[weapon]:.2f}"
            )
    if not has_launch:
        print("  none")

    print("target_damage:")
    for target in metadata.targets:
        cumulative_damage = 0.0
        for wave in metadata.waves:
            pair_summaries = []
            wave_damage = 0.0
            chosen_state = "unknown"
            for state_id in metadata.state_ids_by_target[target.target_id]:
                selected = pyo.value(
                    model.state_select[(target.target_id, wave, state_id)]
                )
                if selected and selected > 0.5:
                    chosen_state = (
                        f"{state_id}:alive={metadata.alive_subset_by_state[(target.target_id, state_id)]},"
                        f"impact={metadata.impact_factor_by_state[(target.target_id, state_id)]:.4f}"
                    )
                    break
            for weapon, pair_target_id, pair_wave in metadata.pair_wave_index:
                if pair_target_id != target.target_id or pair_wave != wave:
                    continue
                for state_id in metadata.state_ids_by_target[target.target_id]:
                    for level in metadata.level_options[
                        (weapon, target.target_id, wave, state_id)
                    ]:
                        chosen = pyo.value(
                            model.hit_choice[
                                (weapon, target.target_id, wave, state_id, level)
                            ]
                        )
                        if chosen and chosen > 0.5 and level > 0:
                            damage = (
                                metadata.damage_by_pair_wave[
                                    (weapon, target.target_id, wave)
                                ]
                                * level
                            )
                            wave_damage += damage
                            pair_summaries.append(
                                f"{weapon}:state={state_id},hits={level},damage={damage:.4f},"
                                f"hit_rate={metadata.hit_probability_by_choice[(weapon, target.target_id, wave, state_id)]:.4f}"
                            )
            cumulative_damage += wave_damage
            destroyed = int(
                round(pyo.value(model.destroyed[(target.target_id, wave)]) or 0)
            )
            detail_str = "; ".join(pair_summaries) if pair_summaries else "none"
            print(
                f"  target={target.target_id} type={target.target_type} "
                f"wave={wave} range=({target.damage_requirement_min:.4f},{target.damage_requirement_max:.4f}) "
                f"loss_air_defense={target.loss_air_defense_damage:.4f} "
                f"wave_damage={wave_damage:.4f} cumulative={cumulative_damage:.4f} "
                f"destroyed={destroyed} state={chosen_state} detail={detail_str}"
            )


# ---------------------------------------------------------------------------
# 两阶段辅助函数
# ---------------------------------------------------------------------------


def _identify_ad_targets(
    targets: list[Target],
    impact_matrix: dict[tuple[str, str], float],
) -> tuple[list[str], dict[str, list[str]]]:
    """找出 AD 目标及其影响关系。"""
    ad_target_ids: set[str] = set()
    influencer_of: dict[str, list[str]] = {}
    for t in targets:
        influencers = [
            other_id
            for other_id in (tt.target_id for tt in targets)
            if abs(impact_matrix.get((other_id, t.target_id), 1.0) - 1.0) > 1e-9
        ]
        influencer_of[t.target_id] = influencers
        for inf in influencers:
            ad_target_ids.add(inf)
    return sorted(ad_target_ids), influencer_of


def _run_milp_stage(
    stage_label: str,
    feature_data: FeatureData,
    base_data: dict[str, BaseData],
    targets: list[Target],
    groups: dict[tuple[str, str], list[tuple[str, ...]]],
    wave_count: int,
    impact_matrix: dict[tuple[str, str], float],
    hit_probability: float,
    confidence_level: float,
) -> tuple[pyo.ConcreteModel, ModelMetadata]:
    """执行单阶段 MILP 求解并打印结果。"""
    log(f"--- {stage_label} ---")
    model, metadata = build_model(
        feature_data=feature_data,
        base_data=base_data,
        targets=targets,
        groups=groups,
        wave_count=wave_count,
        impact_matrix=impact_matrix,
        hit_probability=hit_probability,
        confidence_level=confidence_level,
    )
    results = solve_model(model)
    status = results.solver.status
    termination = results.solver.termination_condition
    if termination not in {
        pyo.TerminationCondition.optimal,
        pyo.TerminationCondition.feasible,
    }:
        raise RuntimeError(
            f"{stage_label} 求解失败: status={status}, termination={termination}"
        )

    total_cost = pyo.value(model.TotalCost)
    log(f"{stage_label} 完成: cost={total_cost:.4f}, status={status}")
    print(f"\n===== {stage_label} =====")
    print(f"status={status}")
    print(f"termination={termination}")
    print(f"total_cost={total_cost:.4f}")
    print_detailed_results(model, metadata, base_data)
    return model, metadata


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def run_allocation(
    config_path: Path,
    output_path: Path,
    mc_trials: int = 5000,
    defaults: dict = None,
) -> dict:
    """执行完整分配管线（MILP + MC），返回结构化结果。

    Args:
        config_path: 场景配置文件路径。
        output_path: 结果 JSON 输出路径。
        mc_trials: Monte Carlo 仿真次数。
        defaults: 默认配置字典，深度合并到用户配置。
    """
    log("=== 程序启动 (单次 MILP) ===")

    from .config_loader import Config, load_config

    cfg = load_config(config_path, defaults)
    feature_data = cfg.feature_data
    base_data = cfg.base_data
    targets = cfg.targets
    groups = cfg.groups
    wave_count = cfg.wave_count
    impact_matrix = cfg.impact_matrix
    confidence = cfg.confidence_level
    hit_prob = cfg.hit_probability

    n_targets = len(targets)
    per_target_confidence = confidence ** (1.0 / n_targets)
    log(
        f"联合置信度 {confidence:.4f} -> 每目标置信度 {per_target_confidence:.4f} "
        f"(目标总数={n_targets})"
    )

    ad_target_ids, _ = _identify_ad_targets(targets, impact_matrix)
    log(f"AD 目标: {ad_target_ids}")

    model, metadata = _run_milp_stage(
        "MILP 求解",
        feature_data,
        base_data,
        targets,
        groups,
        wave_count,
        impact_matrix,
        hit_prob,
        per_target_confidence,
    )

    # plan.json 写入 output 同目录，供 monte_carlo 独立运行使用
    plan_payload = export_results(output_path.parent, model, metadata, feature_data, base_data)

    mc_stats = _mc_validate_plan(
        model,
        metadata,
        feature_data,
        base_data,
        targets,
        impact_matrix,
        hit_prob,
        confidence,
        n_trials=mc_trials,
    )

    total_cost = pyo.value(model.TotalCost)

    mc_per_target = []
    for tid in sorted(mc_stats.per_target.keys(), key=lambda x: (x.isdigit(), x)):
        ts = mc_stats.per_target[tid]
        mc_per_target.append(
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

    return {
        "total_cost": total_cost,
        "sorties": plan_payload["sorties"],
        "launches": plan_payload["launches"],
        "mc_validation": {
            "n_trials": mc_stats.n_trials,
            "plan_cost": mc_stats.plan_cost,
            "p_all_met": mc_stats.p_all_met,
            "confidence_level": mc_stats.confidence_level,
            "per_target": mc_per_target,
        },
    }


def _generate_markdown_report(result: dict, config_path: Path, output_dir: Path) -> None:
    """生成中文 Markdown 作战方案报告。"""
    import json as _json

    raw = _json.loads(config_path.read_text(encoding="utf-8"))
    target_names: dict[str, str] = {}
    type_names: dict[str, str] = {}
    if "targets" in raw:
        for t in raw["targets"]:
            target_names[str(t["id"])] = t.get("name", str(t["id"]))
    if "feature_data" in raw and "target_types" in raw["feature_data"]:
        for tid, tv in raw["feature_data"]["target_types"].items():
            type_names[tid] = tv.get("name", tid)

    lines: list[str] = []
    def w(s: str = "") -> None:
        lines.append(s)

    w("# 武器-目标分配作战方案")
    w()
    w(f"**场景**: {config_path.stem}　|　**总成本**: {result['total_cost']:.0f}　|　**联合达标率**: {result['mc_validation']['p_all_met']:.2%}")
    w()

    # ── 一、兵力部署 ──
    w("## 一、兵力部署（架次计划）")
    w()
    sorties_by_wave: dict[int, list[dict]] = {}
    for s in result["sorties"]:
        sorties_by_wave.setdefault(s["wave"], []).append(s)
    for wave in sorted(sorties_by_wave):
        w(f"### 第 {wave} 波次")
        w()
        w("| 基地 | 平台 | 目标 | 架次数 | 平台成本 |")
        w("|------|------|------|--------|----------|")
        wave_platform_cost = 0
        for s in sorties_by_wave[wave]:
            t_names = ", ".join(target_names.get(str(t), str(t)) for t in s["targets"])
            cost = s["count"] * s["platform_cost_per_sortie"]
            wave_platform_cost += cost
            w(f"| {s['base_id']} | {s['platform']} | {t_names} | {s['count']} | {cost:.0f} |")
        w(f"| **小计** | | | | **{wave_platform_cost:.0f}** |")
        w()

    # ── 二、弹药发射 ──
    w("## 二、弹药发射计划")
    w()
    launches_by_wave: dict[int, list[dict]] = {}
    for ln in result["launches"]:
        launches_by_wave.setdefault(ln["wave"], []).append(ln)
    for wave in sorted(launches_by_wave):
        w(f"### 第 {wave} 波次")
        w()
        w("| 基地 | 平台 | 武器 | 目标 | 发射数 | 武器成本 |")
        w("|------|------|------|------|--------|----------|")
        wave_weapon_cost = 0
        for ln in launches_by_wave[wave]:
            t_name = target_names.get(str(ln["target_id"]), str(ln["target_id"]))
            cost = ln["count"] * ln["weapon_cost_per_round"]
            wave_weapon_cost += cost
            w(f"| {ln['base_id']} | {ln['platform']} | {ln['weapon']} | {t_name} | {ln['count']} | {cost:.0f} |")
        w(f"| **小计** | | | | | **{wave_weapon_cost:.0f}** |")
        w()

    # ── 三、目标毁伤详情 ──
    w("## 三、目标毁伤详情")
    w()
    mc = result["mc_validation"]
    per_target = {t["target_id"]: t for t in mc["per_target"]}

    w("| 目标 | 类型 | 毁伤要求 | 发射数 | 达标率 | 均值 | P50 | P95 | 摧毁率 |")
    w("|------|------|----------|--------|--------|------|-----|-----|--------|")
    for t in mc["per_target"]:
        tid = t["target_id"]
        tname = target_names.get(tid, tid)
        ttype = type_names.get(t["target_type"], t["target_type"])
        req = f"[{t['damage_min']:.1f}, {t['damage_max']:.0f}]"
        flag = " v" if t["p_requirement_met"] >= mc["confidence_level"] else " x"
        w(f"| {tname} | {ttype} | {req} | {t['planned_launches']} | {t['p_requirement_met']:.2%}{flag} | {t['mean_damage']:.2f} | {t['p50_damage']:.2f} | {t['p95_damage']:.2f} | {t['p_destroyed']:.2%} |")
    w()
    w(f"> v = 达标率 >= 置信度 {mc['confidence_level']:.0%}　x = 未达标")
    w()

    # ── 四、资源利用率 ──
    w("## 四、资源利用率")
    w()
    used_platforms: dict[tuple[str, str], int] = {}
    for s in result["sorties"]:
        key = (s["base_id"], s["platform"])
        used_platforms[key] = used_platforms.get(key, 0) + s["count"]
    used_weapons: dict[tuple[str, str], int] = {}
    for ln in result["launches"]:
        key = (ln["base_id"], ln["weapon"])
        used_weapons[key] = used_weapons.get(key, 0) + ln["count"]

    w("### 平台利用率")
    w()
    w("| 基地 | 平台 | 可用 | 已用 | 利用率 |")
    w("|------|------|------|------|--------|")
    for bid, bdata in raw.get("bases_data", {}).items():
        for pname, pcount in bdata.get("platforms", {}).items():
            used = used_platforms.get((bid, pname), 0)
            pct = f"{used / pcount:.0%}" if pcount > 0 else "-"
            w(f"| {bid} | {pname} | {pcount} | {used} | {pct} |")

    w()
    w("### 武器利用率")
    w()
    w("| 基地 | 武器 | 库存 | 已用 | 利用率 |")
    w("|------|------|------|------|--------|")
    for bid, bdata in raw.get("bases_data", {}).items():
        for wname, wcount in bdata.get("weapons", {}).items():
            used = used_weapons.get((bid, wname), 0)
            pct = f"{used / wcount:.0%}" if wcount > 0 else "-"
            w(f"| {bid} | {wname} | {wcount} | {used} | {pct} |")

    w()
    w("## 五、仿真参数")
    w()
    w(f"- 联合置信度要求: {mc['confidence_level']:.0%}")
    w(f"- 仿真次数: {mc['n_trials']:,}")
    w(f"- 联合达标率: **{mc['p_all_met']:.2%}**")

    report_path = output_dir / "wta_plan.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    log(f"作战方案报告已生成: {report_path}")


def main() -> int:
    """程序入口 — 单次 MILP + MC 验证。"""
    parser = argparse.ArgumentParser(
        description="MILP allocator for base-platform-weapon-target assignment."
    )
    parser.add_argument(
        "--config", default="wta/input/scenario.yaml", help="场景配置路径，支持 YAML/JSON"
    )
    parser.add_argument(
        "--output", default=None, help="输出目录 (默认: output/{场景名}_result/)"
    )
    parser.add_argument("--mc-trials", type=int, default=5000)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="[%(name)s] %(message)s",
    )

    config_path = Path(args.config).resolve()

    if args.output:
        output_dir = Path(args.output)
    else:
        config_name = config_path.stem
        output_dir = (
            Path(__file__).resolve().parent.parent
            / "output"
            / f"{config_name}_result"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "plan.json"

    # 加载默认配置
    import yaml as _yaml
    defaults_path = Path(__file__).resolve().parent / "input" / "_defaults.yaml"
    defaults = _yaml.safe_load(defaults_path.read_text(encoding="utf-8")) if defaults_path.exists() else {}

    result = run_allocation(
        config_path=config_path,
        output_path=output_path,
        mc_trials=args.mc_trials,
        defaults=defaults,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"结果已导出: {output_path}")

    _generate_markdown_report(result, config_path, output_dir)

    print("\n===== 结果摘要 =====")
    print(f"total_cost={result['total_cost']:.4f}")
    print(f"sorties={len(result['sorties'])}")
    print(f"launches={len(result['launches'])}")
    print(f"p_all_met={result['mc_validation']['p_all_met']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
