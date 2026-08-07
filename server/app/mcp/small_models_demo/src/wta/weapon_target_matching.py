"""CEP 精度-弹目匹配。

根据武器 CEP、杀伤半径和目标的保护距离，计算在给定置信度下
每个武器对每个目标是否安全可用。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class WeaponPhysics:
    """武器物理参数。"""
    name: str
    cep: float          # 圆概率误差 (米)
    lethal_radius: float = 0.0  # 杀伤半径 (米)


@dataclass
class TargetRisk:
    """目标风险参数。"""
    target_id: str
    risk_distance: float  # 目标边缘到禁区边缘的距离 (米), inf=无限制


@dataclass
class MatchingResult:
    """弹目匹配结果。"""
    confidence: float
    k_factor: float                     # CEP 系数
    safe_pairs: list[tuple[str, str]]   # [(weapon_name, target_id)]
    excluded_pairs: list[tuple[str, str, float, float]]  # [(weapon, target, impact_radius, risk_distance)]
    summary: dict[str, list[str]]       # target_id → [safe_weapon_names]


def compute_impact_radius(cep: float, lethal_radius: float, confidence: float) -> float:
    """计算给定置信度下的波及半径。

    impact_radius = CEP × k(confidence) + lethal_radius
    其中 k = sqrt(ln(1/(1-C)) / ln(2))
    """
    if confidence <= 0 or confidence >= 1:
        raise ValueError(f"confidence 必须在 (0, 1) 之间, 当前={confidence}")
    k = math.sqrt(math.log(1.0 / (1.0 - confidence)) / math.log(2))
    return cep * k + lethal_radius


def match_weapons_to_targets(
    weapons: list[WeaponPhysics],
    targets: list[TargetRisk],
    confidence: float = 0.80,
) -> MatchingResult:
    """根据 CEP 精度约束，匹配武器到目标。

    对每对 (weapon, target), 若波及半径 > risk_distance, 则排除该武器。
    波及半径 = CEP × k(confidence) + lethal_radius

    Args:
        weapons: 武器列表 (含 CEP 和杀伤半径)
        targets: 目标列表 (含 risk_distance)
        confidence: 弹着点不超安全距离的置信度

    Returns:
        MatchingResult: 包含安全对、排除对和按目标汇总的安全武器列表
    """
    k = math.sqrt(math.log(1.0 / (1.0 - confidence)) / math.log(2))

    safe_pairs: list[tuple[str, str]] = []
    excluded_pairs: list[tuple[str, str, float, float]] = []
    summary: dict[str, list[str]] = {t.target_id: [] for t in targets}

    for target in targets:
        rd = target.risk_distance
        for weapon in weapons:
            impact_radius = compute_impact_radius(weapon.cep, weapon.lethal_radius, confidence)
            if impact_radius <= rd:
                safe_pairs.append((weapon.name, target.target_id))
                summary[target.target_id].append(weapon.name)
            else:
                excluded_pairs.append((weapon.name, target.target_id, impact_radius, rd))

    return MatchingResult(
        confidence=confidence,
        k_factor=k,
        safe_pairs=safe_pairs,
        excluded_pairs=excluded_pairs,
        summary=summary,
    )


def print_matching_report(result: MatchingResult, weapons: list[WeaponPhysics], targets: list[TargetRisk]) -> None:
    """打印弹目匹配报告。"""
    tw = max(len(w.name) for w in weapons) + 2
    tt = max(len(t.target_id) for t in targets) + 2

    print(f"\n=== 精度-弹目匹配 (置信度={result.confidence:.2f}, k={result.k_factor:.2f}) ===")

    # 表头
    header = f"  {'武器':<{tw}}"
    for t in targets:
        header += f" {'T' + t.target_id:>{tt}}"
    print(header)

    # 每武器一行
    for w in weapons:
        row = f"  {w.name:<{tw}}"
        for t in targets:
            key = (w.name, t.target_id)
            if key in result.safe_pairs:
                ir = compute_impact_radius(w.cep, w.lethal_radius, result.confidence)
                row += f" {f'✓{ir:.0f}m':>{tt}}"
            else:
                for wpn, tid, ir, rd in result.excluded_pairs:
                    if wpn == w.name and tid == t.target_id:
                        row += f" {f'✗{ir:.0f}>{rd:.0f}':>{tt}}"
                        break
                else:
                    row += f" {'-':>{tt}}"
        print(row)

    # 详细排除列表
    if result.excluded_pairs:
        print(f"\n  排除详情 ({len(result.excluded_pairs)} 条):")
        for wpn, tid, ir, rd in sorted(result.excluded_pairs):
            print(f"    {wpn} → T{tid}: 波及半径={ir:.1f}m > risk_distance={rd:.0f}m")

    # 每目标可用武器
    print(f"\n  可用武器 (按目标):")
    for t in targets:
        safe = result.summary[t.target_id]
        if safe:
            print(f"    T{t.target_id} (risk={t.risk_distance:.0f}m): {', '.join(safe)}")
        else:
            print(f"    T{t.target_id} (risk={t.risk_distance:.0f}m): 无可用武器!")


# ---------------------------------------------------------------------------
# 独立测试入口
# ---------------------------------------------------------------------------


def main() -> int:
    """从当前项目数据加载武器和目标，测试精度-弹目匹配。"""
    import argparse
    from pathlib import Path
    from .models import load_feature_yaml, load_scenario_yaml

    parser = argparse.ArgumentParser(description="CEP 精度-弹目匹配测试")
    parser.add_argument(
        "--feature", default="wta/input/feature.yaml", help="特征配置路径，支持 YAML/JSON"
    )
    parser.add_argument(
        "--scenario", default="wta/input/scenario_weapon_match.yaml", help="场景配置路径，支持 YAML/JSON"
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=None,
        help="覆盖场景中的 solver.risk_confidence；未传时默认读取场景配置",
    )
    parser.add_argument(
        "--output", default="output/cep_matching.json", help="结果 JSON 输出路径"
    )
    args = parser.parse_args()

    fd = load_feature_yaml(Path(args.feature))
    weapons = [
        WeaponPhysics(
            w,
            cep=fd.weapon_cep.get(w, 0),
            lethal_radius=fd.weapon_lethal_radius.get(w, 0),
        )
        for w in fd.weapons
    ]

    sc = load_scenario_yaml(Path(args.scenario))
    confidence = float(
        args.confidence
        if args.confidence is not None
        else sc.get("solver", {}).get("risk_confidence", 0.95)
    )
    targets = [
        TargetRisk(str(t["id"]), float(t.get("risk_distance", 1e9)))
        for t in sc["targets"]
    ]

    result = match_weapons_to_targets(weapons, targets, confidence=confidence)
    print_matching_report(result, weapons, targets)

    import json
    excluded_by_target: dict[str, list[str]] = {t.target_id: [] for t in targets}
    for weapon_name, target_id, _impact_radius, _risk_distance in result.excluded_pairs:
        excluded_by_target[target_id].append(weapon_name)
    target_weapons = {}
    for t in targets:
        target_weapons[t.target_id] = {
            "usable_weapons": result.summary.get(t.target_id, []),
            "unusable_weapons": excluded_by_target.get(t.target_id, []),
        }
    output = {"targets": target_weapons}
    json_path = Path(args.output).resolve()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON 结果已导出: {json_path}")

    # 检查是否有目标无可用武器
    no_weapon = [tid for tid, safe in result.summary.items() if not safe]
    if no_weapon:
        print(f"\n⚠ 目标 {no_weapon} 在置信度 {confidence:.2f} 下无可用武器!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
