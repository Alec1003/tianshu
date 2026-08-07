"""返航 MILP 分配模块 — 将飞机分配到基地，满足机型容量约束，最小化总代价。"""

from typing import Dict, List, Tuple

import pulp


def assign_platforms_to_bases(
    cost_matrix: Dict[Tuple[str, str], float],
    platform_types: Dict[str, str],
    base_capacities: Dict[str, Dict[str, int]],
) -> Tuple[Dict[str, str], float]:
    """
    用 MILP 求解最优飞机→基地分配。

    Args:
        cost_matrix: {(platform_id, base_id): cost}, cost=inf 表示不可行
        platform_types: {platform_id: aircraft_type}
        base_capacities: {base_id: {aircraft_type: max_count}}

    Returns:
        assignment: {platform_id: base_id}
        total_cost: 总代价

    Raises:
        ValueError: 如果无可行分配
    """
    INF = 1e9

    platforms = list(platform_types.keys())
    bases = list(base_capacities.keys())

    feasible_pairs = []
    for pid in platforms:
        for bid in bases:
            c = cost_matrix.get((pid, bid), INF)
            if c < INF / 2:
                feasible_pairs.append((pid, bid))

    if not feasible_pairs:
        raise ValueError("没有可行的 (platform, base) 组合")

    prob = pulp.LpProblem("ReturnAssignment", pulp.LpMinimize)

    x = {}
    for pid, bid in feasible_pairs:
        x[(pid, bid)] = pulp.LpVariable(f"x_{pid}_{bid}", cat=pulp.LpBinary)

    prob += pulp.lpSum(
        x[(pid, bid)] * cost_matrix[(pid, bid)] for pid, bid in feasible_pairs
    )

    for pid in platforms:
        prob += (
            pulp.lpSum(x[(pid, bid)] for bid in bases if (pid, bid) in feasible_pairs)
            == 1
        )

    for bid in bases:
        cap = base_capacities.get(bid, {})
        for atype in cap:
            prob += (
                pulp.lpSum(
                    x[(pid, bid)]
                    for pid in platforms
                    if (pid, bid) in feasible_pairs and platform_types.get(pid) == atype
                )
                <= cap[atype]
            )

    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    if pulp.LpStatus[prob.status] != "Optimal":
        raise ValueError(f"MILP 未找到最优解, status={pulp.LpStatus[prob.status]}")

    assignment = {}
    for pid, bid in feasible_pairs:
        if pulp.value(x[(pid, bid)]) > 0.5:
            assignment[pid] = bid

    return assignment, pulp.value(prob.objective)
