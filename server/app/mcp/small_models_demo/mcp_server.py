"""MCP 服务端：将全部算法封装为 MCP tools，供 LLM Agent 调用.

启动:
    python mcp_server.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

SOURCE_ROOT = Path(__file__).resolve().parent
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

try:
    from .schemas import (
        AttackScenario,
        CEPScenario,
        CoverageScenario,
        FeatureData,
        MCPlan,
        RefuelScenario,
        ReturnScenario,
        RouteAttackInput,
        RouteRefuelInput,
        RouteReturnInput,
        Trajectory,
        WTAConfig,
    )
except ImportError:
    from schemas import (
        AttackScenario,
        CEPScenario,
        CoverageScenario,
        FeatureData,
        MCPlan,
        RefuelScenario,
        ReturnScenario,
        RouteAttackInput,
        RouteRefuelInput,
        RouteReturnInput,
        Trajectory,
        WTAConfig,
    )

mcp = FastMCP(
    "Small Models Solver",
    instructions="统一求解服务 — WTA 武器分配、CEP 弹目匹配、Monte Carlo 仿真、路径规划",
)

OUTPUT_BASE = Path(__file__).resolve().parent / "output"


def _output_path(tool_name: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUTPUT_BASE / f"{tool_name}_{ts}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


# ═══════════════════════════════════════════════════════════════════
# WTA 系列
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
def wta(config: WTAConfig, mc_trials: int = 5000) -> dict[str, Any]:
    """WTA 武器-目标分配（MILP + Monte Carlo 验证）。

    根据场景配置求解武器-目标的最优分配方案。
    先 MILP 求解分配方案，再 Monte Carlo 仿真验证毁伤达标概率。
    用户未填的字段会使用算法内置默认值（waves=1, confidence_level=0.95 等），用户填写的值优先。

    选型建议:
    - wta: 需要自定义波次数和置信度时使用
    - wta_allcost: 必须一击摧毁全部目标、不计代价时使用（如高价值斩首目标）
    - wta_mincost: 大规模打击、追求效费比时使用

    输入:
    - config (WTAConfig): 场景配置（未填字段自动使用默认值，用户值优先覆盖）
      - solver: 求解器参数
        - hit_probability (float): 命中概率回退值，默认 1.0。当 target_types 中未定义某武器对某目标的 hit_rate 时使用此值
        - confidence_level (float): 联合置信度 0~1，默认 0.95。求解器要求所有目标同时达到毁伤要求的概率不低于此值
        - risk_confidence (float): CEP 风险置信度 0~1，默认 0.7。用于计算波及半径时的置信系数
        - waves (int): 攻击波次数，默认 2。波次间命中率会根据上一波毁伤结果动态更新
        - loss_air_defense_damage (float): 防空目标失能后损伤系数，默认 0.8。仅对 type 标记为防空类的目标生效：该目标被摧毁后，其对后续波次的 hit_rate 惩罚降为原来的 (1 - loss_air_defense_damage) 倍。例如 loss_air_defense_damage=0.8 意味着防空压制 80% 的效果
      - targets: 目标列表 [{id, type, damage, risk_distance}]
        - id (int|str): 目标唯一标识
        - type (str): 目标类型，必须与 target_types 中的 key 精确匹配
        - damage ([float, float]): [毁伤率要求(0~1), 完全摧毁阈值]。
          第一项是必须达到的最低毁伤比例（如 0.9 表示至少造成 90% 毁伤），第二项是该目标被认定"完全摧毁"的毁伤值
        - risk_distance (float): 风险距离（米）。来自 CEP 精度约束：波及半径超过此值的武器不可用于该目标。越小越危险
      - feature_data: 武器/平台能力配置
        - platforms: {平台名: {loadout: 最大载弹量(整数)}} — 单个平台的挂载上限
        - weapons: {武器名: {hardpoint: 挂点占用数, cep: 圆概率误差(米), lethal_radius: 杀伤半径(米)}}
        - compatibility: {平台名: [可用武器名列表]} — 某平台能挂载哪些武器
        - target_types: {类型名: {name: 显示名称, damage: {武器名: 单发毁伤率(0~1)}, hit_rate: {武器名: 单发命中率(0~1)}, default_hit_rate_impact?}}
          damage 是命中后造成毁伤的条件概率 P(毁伤|命中)，hit_rate 是单发命中概率。
          实际单发毁伤期望 = hit_rate × damage
          default_hit_rate_impact 可选，当该类型目标作为命中率影响源时使用的默认值（可为单值或分武器字典）
      - bases_data: 基地资源 {基地名: {...}}
        - base_id (str): 基地 ID
        - platforms: {平台名: 该基地可出动架数}
        - weapons: {武器名: 该基地弹药库存}
        - costs: {platform: {平台名: 单架出勤成本}, weapon: {武器名: 单枚消耗成本}} — 成本为抽象数值，仅用于方案间比较
    - mc_trials (int): MC 仿真次数，默认 5000，范围 [100, 100000]。仅影响内置 MC 验证的精度，不影响 MILP 分配结果

    返回:
    - total_cost (float): 总代价（平台出勤成本 + 武器消耗成本之和）
    - sorties: [{base_id, platform, group_id, wave, targets: [目标id], count: 出勤架数, platform_cost_per_sortie: 单架成本}]
    - launches: [{base_id, platform, group_id, wave, weapon, target_id, count: 发射数, weapon_cost_per_round: 单枚成本}]
    - mc_validation: 内置 MC 验证结果（非独立 MC，精度低于 monte_carlo 工具）
      - n_trials (int): 实际仿真次数
      - p_all_met (float): 联合达标率 P(所有目标均满足毁伤要求)
      - per_target: [{target_id, target_type, damage_min, damage_max,
        p_requirement_met: 毁伤达标概率 P(毁伤 ≥ damage_min),
        p_destroyed: 完全摧毁概率 P(毁伤 ≥ damage_max),
        planned_launches: 计划发射数,
        mean_damage, std_damage, p5_damage(5%分位数), p50_damage(中位数), p95_damage(95%分位数), min_damage, max_damage}]

    示例:
      config = {
        "solver": {"waves": 2, "confidence_level": 0.95},
        "targets": [{"id": "0", "type": "bunker", "damage": [0.9, 100], "risk_distance": 50}],
        "feature_data": {
          "platforms": {"F16I": {"loadout": 8}},
          "weapons": {"SPICE 2000": {"hardpoint": 1, "cep": 5, "lethal_radius": 50}},
          "compatibility": {"F16I": ["SPICE 2000"]},
          "target_types": {"bunker": {"name": "掩体", "damage": {"SPICE 2000": 0.8}, "hit_rate": {"SPICE 2000": 0.9}}}
        },
        "bases_data": {"Hatzerim": {"base_id": "Hatzerim", "platforms": {"F16I": 10}, "weapons": {"SPICE 2000": 100}, "costs": {"platform": {"F16I": 6}, "weapon": {"SPICE 2000": 6}}}}
      }
    """
    from src.algorithms.wta import run
    return run(config.model_dump(exclude_none=True), mc_trials, str(_output_path("wta")))


@mcp.tool()
def wta_allcost(config: WTAConfig, mc_trials: int = 5000) -> dict[str, Any]:
    """WTA 不惜代价分配 — 强制单波次 + 最高置信度 (waves=1, confidence=0.99)。

    以不惜代价模式求解武器-目标分配，以最大火力确保摧毁所有目标。
    内部覆盖 solver.waves=1 和 solver.confidence_level=0.99，其余参数保留用户输入。
    适用于必须一击必杀的高价值目标场景。

    输入:
    - config (WTAConfig): 场景配置（solver.waves 和 solver.confidence_level 会被覆盖为 1 和 0.99）
      - solver: 求解器参数（以下字段会被保留）
        - hit_probability (float): 命中概率回退值，默认 1.0
        - risk_confidence (float): CEP 风险置信度 0~1，默认 0.7
        - loss_air_defense_damage (float): 防空目标失能后损伤系数，默认 0.8
      - targets: 目标列表 [{id, type, damage: [毁伤率要求, 最大毁伤值], risk_distance}]
      - feature_data: {platforms, weapons, compatibility, target_types} — 结构同 wta
      - bases_data: {基地名: {base_id, platforms, weapons, costs}} — 结构同 wta
    - mc_trials (int): MC 仿真次数，默认 5000，范围 [100, 100000]

    返回: 结构同 wta — {total_cost, sorties, launches, mc_validation}
    """
    from src.algorithms.wta_allcost import run
    return run(config.model_dump(exclude_none=True), mc_trials, str(_output_path("wta_allcost")))


@mcp.tool()
def wta_mincost(config: WTAConfig, mc_trials: int = 5000) -> dict[str, Any]:
    """WTA 最小花费分配 — 强制两波次 + 标准置信度 (waves=2, confidence=0.95)。

    以最小代价分波次摧毁目标，追求效费比最大化。
    内部覆盖 solver.waves=2 和 solver.confidence_level=0.95，其余参数保留用户输入。
    适用于大规模打击场景。

    输入:
    - config (WTAConfig): 场景配置（solver.waves 和 solver.confidence_level 会被覆盖为 2 和 0.95）
      - solver: 求解器参数（以下字段会被保留）
        - hit_probability (float): 命中概率回退值，默认 1.0
        - risk_confidence (float): CEP 风险置信度 0~1，默认 0.7
        - loss_air_defense_damage (float): 防空目标失能后损伤系数，默认 0.8
      - targets: 目标列表 [{id, type, damage: [毁伤率要求, 最大毁伤值], risk_distance}]
      - feature_data: {platforms, weapons, compatibility, target_types} — 结构同 wta
      - bases_data: {基地名: {base_id, platforms, weapons, costs}} — 结构同 wta
    - mc_trials (int): MC 仿真次数，默认 5000，范围 [100, 100000]

    返回: 结构同 wta — {total_cost, sorties, launches, mc_validation}
    """
    from src.algorithms.wta_mincost import run
    return run(config.model_dump(exclude_none=True), mc_trials, str(_output_path("wta_mincost")))


# ═══════════════════════════════════════════════════════════════════
# CEP 精度-弹目匹配
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
def cep_match(
    feature: FeatureData,
    scenario: CEPScenario,
    confidence: float | None = None,
) -> dict[str, Any]:
    """CEP 精度-弹目匹配 — 计算每个武器对每个目标是否安全可用。

    根据武器 CEP（圆概率误差）、杀伤半径和目标的 risk_distance（风险距离），
    计算在给定置信度下每个武器对每个目标的安全性。
    核心公式: 波及半径 = CEP × k(confidence) + lethal_radius
    其中 k = sqrt(ln(1/(1-confidence)) / ln(2))。
    若波及半径 ≤ risk_distance，该武器对该目标安全可用；否则不可用。
    risk_distance 越小表示目标越危险、对精度要求越高。
    注意: 此工具只用到 weapons 的 cep 和 lethal_radius 字段，
    feature 中的 target_types 的 damage/hit_rate 字段对此计算无影响，可填空对象。

    输入:
    - feature (FeatureData): 武器能力配置（只需 cep 和 lethal_radius 参与计算）
      - platforms: {平台名: {loadout: 最大载弹量}}
      - weapons: {武器名: {hardpoint: 挂点占用数, cep: 圆概率误差(米), lethal_radius: 杀伤半径(米)}}
      - compatibility: {平台名: [可用武器名列表]}
      - target_types: {类型名: {name: 显示名称, damage: {}, hit_rate: {}}} — 此工具不使用 damage/hit_rate，可留空
    - scenario (CEPScenario): 风险场景
      - solver: {risk_confidence: 风险置信度 0~1，默认 0.7}
      - targets: [{id: 目标ID(整数或字符串), risk_distance: 风险距离(米)}]
    - confidence (float | None): 可选，覆盖 scenario.solver.risk_confidence。不传则使用 solver 中的值

    返回:
    - targets: {target_id: {usable_weapons: [...], unusable_weapons: [...]}}
      usable_weapons: 波及半径 ≤ risk_distance 的武器名列表
      unusable_weapons: 波及半径 > risk_distance 的武器名列表

    示例:
      feature = {
        "platforms": {"J-16": {"loadout": 8}},
        "weapons": {
          "KD-20": {"hardpoint": 3, "cep": 5, "lethal_radius": 150},
          "PL-15": {"hardpoint": 1, "cep": 10, "lethal_radius": 50},
          "火箭弹": {"hardpoint": 1, "cep": 100, "lethal_radius": 200}
        },
        "compatibility": {"J-16": ["KD-20", "PL-15", "火箭弹"]},
        "target_types": {"air_defense": {"name": "防空阵地"}}
      }
      scenario = {"solver": {"risk_confidence": 0.7}, "targets": [{"id": 1, "risk_distance": 50}, {"id": 2, "risk_distance": 200}]}
      # confidence=0.7 时 k≈1.318
      # KD-20: 5×1.318+150=156.6 → target 1 (50m) 不可用, target 2 (200m) 可用
      # PL-15: 10×1.318+50=63.2 → target 1 (50m) 不可用, target 2 (200m) 可用
      # 火箭弹: 100×1.318+200=331.8 → 两目标均不可用
    """
    from src.algorithms.cep_match import run
    return run(feature.model_dump(exclude_none=True), scenario.model_dump(exclude_none=True), confidence, str(_output_path("cep_match")))


# ═══════════════════════════════════════════════════════════════════
# Monte Carlo 仿真
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
def monte_carlo(
    config: WTAConfig,
    plan: MCPlan,
    mc_trials: int = 5000,
    seed: int = 42,
) -> dict[str, Any]:
    """Monte Carlo 仿真 — 验证 WTA 分配方案在随机命中条件下的毁伤达标概率。

    对已有的 WTA 分配方案运行 Monte Carlo 仿真，评估方案在真实随机环境中的稳健性。
    仿真逻辑: 逐波次执行发射计划，每次命中为 Bernoulli 试验（成功概率 = hit_rate × damage），
    波次间命中率根据 hit_rate_impact 动态更新（若影响源目标在上一波被摧毁，本波移除其命中率折扣）。
    必须在 wta / wta_allcost / wta_mincost 之后调用。

    输入:
    - config (WTAConfig): 场景配置（必须与生成 plan 时的 config 完全一致）
      - solver: {hit_probability, confidence_level, risk_confidence, waves, loss_air_defense_damage}
      - targets: [{id, type, damage: [毁伤率要求, 最大毁伤值], risk_distance}]
      - feature_data: {platforms, weapons, compatibility, target_types}
      - bases_data: {基地名: {base_id, platforms, weapons, costs}}
    - plan (MCPlan): WTA 分配方案。直接将 wta 工具返回的完整结果传入即可（sorties 和 launches 之外的字段如 total_cost、mc_validation 会被自动忽略）
    - mc_trials (int): 仿真次数，默认 5000，范围 [100, 100000]。越大越精确但越慢
    - seed (int): 随机种子，默认 42，相同 seed 产生可复现的结果

    返回:
    - n_trials (int): 仿真次数
    - plan_cost (float): 方案总代价
    - p_all_met (float): 联合达标率 — 所有目标同时满足毁伤要求的概率
    - confidence_level (float): 使用的置信水平
    - per_target: [{target_id, target_type,
        damage_min: 毁伤率要求, damage_max: 完全摧毁阈值,
        planned_launches: 计划发射数,
        p_requirement_met: 毁伤达标概率 P(实际毁伤 ≥ damage_min),
        p_destroyed: 完全摧毁概率 P(实际毁伤 ≥ damage_max),
        mean_damage, std_damage: 毁伤均值和标准差,
        p5_damage: 5%分位数, p50_damage: 中位数, p95_damage: 95%分位数,
        min_damage, max_damage: 最小和最大毁伤值}]
    """
    from src.algorithms.monte_carlo import run
    return run(config.model_dump(exclude_none=True), plan.model_dump(exclude_none=True), mc_trials, seed, str(_output_path("monte_carlo")))


# ═══════════════════════════════════════════════════════════════════
# 路径规划系列
# ═══════════════════════════════════════════════════════════════════

def _dump_route(model: Any) -> dict[str, Any]:
    """序列化 route 模型，处理 class 别名，排除 None 值."""
    return model.model_dump(by_alias=True, exclude_none=True)


@mcp.tool()
def route_attack(scenario: RouteAttackInput) -> dict[str, Any]:
    """攻击路径规划（自由模式）— 每对 platform-target 的 mode 由用户指定 (1~4)。

    与 route_mode1-4 的区别: 不会强制覆盖 mode，尊重 pairs 中每个配对的 mode 字段。
    可以在一次调用中混合使用 mode 1/2/3/4，适用于不同目标需要不同攻击策略的复杂场景。
    内部使用 Theta* 搜索算法在 3D ECEF 网格上规划路径，代价 = 距离权重 + 威胁暴露 + 方向偏差 + 转弯。

    攻击模式:
    - Mode 1 直攻: 每对独立选最低代价路径，从起点直接到目标
    - Mode 2 多角度: 生成进入参考点候选，按目标分组枚举方向组合，优先方向分散再压低威胁和总代价
    - Mode 3 发射区: 以目标为圆心生成攻击点候选，路径以候选攻击点为终点。需设置 attack_point_radius_km (默认 50km) 和 attack_point_up_height_m (默认 3000m)
    - Mode 4 隐身突防: 在 Mode 3 基础上，要求先经过 waypoint_id 指定的集结点。需设置 waypoint_id、attack_point_radius_km、attack_point_up_height_m

    输入:
    - scenario.scenario.name (str): 任务名称
    - scenario.scenario.platforms: [{id, type, class: "aircraft"|"missile", position: [lon, lat, alt_m], speed: m/s, range: km, initial_heading_deg?}]
      range 为平台最大飞行距离（含往返，单位 km），路径总长度超过 range 则不可行
      initial_heading_deg 不填则默认朝向目标方向，0=北，90=东，180=南，270=西
    - scenario.scenario.waypoints: [{id, position: [lon, lat, alt_m]}] — Mode 4 的集结点
    - scenario.scenario.targets: [{id, position: [lon, lat, alt_m]}]
    - scenario.scenario.threats: [{id, type, position?, params, threat_level: 0~1}]
      threat_level 是威胁代价乘数：0=无威胁(等同于不存在)，1=全威胁。路径穿过威胁体时此值乘以威胁体内部代价
    - scenario.scenario.no_fly_zones: [{id, position, params}] — 禁飞区，路径不可穿过
    - scenario.scenario.pairs: [{platform, target, mode: 1~4, waypoint_id?, attack_point_radius_km?, attack_point_up_height_m?}]
      attack_point_radius_km 不填默认 50km，attack_point_up_height_m 不填默认 3000m

    威胁体类型及 params:
    - sphere: {radius: 球半径(米)} — 以 position 为球心
    - ellipsoid: {direction: [dx,dy,dz] 方向向量, semi_a, semi_b, semi_c: 三个半轴长(米)}
    - cone: {max_range: 最大射程(米), angle: 锥角(弧度或度), direction: [dx,dy,dz] 方向向量}
    - cylinder: {radius: 半径(米), height: 高度(米)} — 无限高圆柱设 height 为很大值

    返回:
    - result.results: 各 pair 的路径结果 [{platform, target, mode,
        cost: 总代价(抽象数值，仅用于方案间相对比较，越低越好),
        threat_exposure: 威胁暴露值(抽象数值，越低越好),
        waypoints: [[lon, lat, alt_m], ...] 航路点坐标数组,
        direction: [方位角(度), 俯仰角(度)], direction_label: 方向标签,
        arrival_angle: [入射方位角(度), 入射俯仰角(度)],
        crossed_threats: [{id, type, avg_value, max_value}] 经过的威胁及暴露值,
        waypoint_details: [{index, waypoint, threat_cost, hits}] 各航点威胁详情}]
    - stdout (str): 路径规划模块终端输出
    """
    from src.algorithms.route_attack import run
    return run(_dump_route(scenario), str(_output_path("route_attack")))


@mcp.tool()
def route_mode1(scenario: RouteAttackInput) -> dict[str, Any]:
    """攻击路径规划 Mode 1（直攻）— 从起点向目标终点直接规划路径。

    强制所有 platform-target pair 使用 mode=1。每对独立选最低代价路径，考虑威胁、禁飞区、转弯代价。
    pairs 中的 mode / attack_point_radius_km / attack_point_up_height_m 会被忽略。
    内部使用 Theta* 搜索算法在 3D ECEF 网格上规划，代价 = 距离 + 威胁暴露 + 方向偏差 + 转弯。

    输入:
    - scenario.scenario.name (str): 任务名称
    - scenario.scenario.platforms: [{id, type, class: "aircraft"|"missile", position: [lon, lat, alt_m], speed: m/s, range: km, initial_heading_deg?}]
      initial_heading_deg 不填则默认朝向目标方向
    - scenario.scenario.targets: [{id, position: [lon, lat, alt_m]}]
    - scenario.scenario.threats: [{id, type: "sphere"|"ellipsoid"|"cone"|"cylinder", position?, params, threat_level: 0~1}]
    - scenario.scenario.no_fly_zones: [{id, position, params}]
    - scenario.scenario.pairs: [{platform, target}] — mode 会被强制覆盖为 1，无需填 mode 字段

    威胁体类型及 params: 同 route_attack（sphere/ellipsoid/cone/cylinder）

    返回: 同 route_attack — {result: {results: [{platform, target, cost, threat_exposure, waypoints, crossed_threats, ...}]}, stdout}
    """
    from src.algorithms.route_mode1 import run
    return run(_dump_route(scenario), str(_output_path("route_mode1")))


@mcp.tool()
def route_mode2(scenario: RouteAttackInput) -> dict[str, Any]:
    """攻击路径规划 Mode 2（多角度）— 生成入射角参考点，按目标分组枚举方向组合。

    强制所有 pair 使用 mode=2。在直攻基础上生成进入参考点候选，同一目标的多个平台分组优化：
    枚举所有方向组合，优先方向分散，再压低威胁和总代价。适用于多方向同时突防的饱和攻击场景。

    输入:
    - scenario.scenario.name (str): 任务名称
    - scenario.scenario.platforms: [{id, type, class: "aircraft"|"missile", position: [lon, lat, alt_m], speed: m/s, range: km}]
    - scenario.scenario.targets: [{id, position: [lon, lat, alt_m]}]
    - scenario.scenario.threats: [{id, type, position?, params, threat_level: 0~1}]
    - scenario.scenario.no_fly_zones: [{id, position, params}]
    - scenario.scenario.pairs: [{platform, target}] — mode 会被强制覆盖为 2

    威胁体类型: 同 route_attack。

    返回: 同 route_attack — {result: {results: [...]}, stdout}
    """
    from src.algorithms.route_mode2 import run
    return run(_dump_route(scenario), str(_output_path("route_mode2")))


@mcp.tool()
def route_mode3(scenario: RouteAttackInput) -> dict[str, Any]:
    """攻击路径规划 Mode 3（发射区）— 以目标为圆心生成攻击点候选。

    强制所有 pair 使用 mode=3。以目标为圆心、attack_point_radius_km 为半径生成攻击点候选，
    路径以候选攻击点为终点（非目标本身），攻击点高度由 attack_point_up_height_m 指定。
    适用于需要在目标外围安全距离发射武器的防区外打击场景。

    输入:
    - scenario.scenario.name (str): 任务名称
    - scenario.scenario.platforms: [{id, type, class, position: [lon, lat, alt_m], speed, range}]
    - scenario.scenario.targets: [{id, position: [lon, lat, alt_m]}]
    - scenario.scenario.threats: [{id, type, position?, params, threat_level}]
    - scenario.scenario.no_fly_zones: [{id, position, params}]
    - scenario.scenario.pairs: [{platform, target, attack_point_radius_km?, attack_point_up_height_m?}]
      attack_point_radius_km (float): 攻击点距目标距离 (km)，不填默认 50km
      attack_point_up_height_m (float): 攻击点高于目标的高度 (m)，不填默认 3000m

    威胁体类型: 同 route_attack。

    返回: 同 route_attack — {result: {results: [...]}, stdout}
    """
    from src.algorithms.route_mode3 import run
    return run(_dump_route(scenario), str(_output_path("route_mode3")))


@mcp.tool()
def route_mode4(scenario: RouteAttackInput) -> dict[str, Any]:
    """攻击路径规划 Mode 4（隐身突防）— 先经过 waypoint 集结点再前往攻击点。

    强制所有 pair 使用 mode=4。在 mode 3 生成攻击点候选的基础上，要求先经过 waypoint_id 指定的集结点，
    再前往攻击点。适用于需要编队集结后协同突防的隐身攻击场景。

    输入:
    - scenario.scenario.name (str): 任务名称
    - scenario.scenario.platforms: [{id, type, class, position: [lon, lat, alt_m], speed, range}]
    - scenario.scenario.waypoints: [{id, position: [lon, lat, alt_m]}] — 集结点，供 waypoint_id 引用
    - scenario.scenario.targets: [{id, position: [lon, lat, alt_m]}]
    - scenario.scenario.threats: [{id, type, position?, params, threat_level}]
    - scenario.scenario.no_fly_zones: [{id, position, params}]
    - scenario.scenario.pairs: [{platform, target, waypoint_id?, attack_point_radius_km?, attack_point_up_height_m?}]
      waypoint_id (str): 必须经过的集结点 ID，需在 waypoints 中已定义
      attack_point_radius_km (float): 攻击点距目标距离 (km)
      attack_point_up_height_m (float): 攻击点高于目标的高度 (m)

    威胁体类型: 同 route_attack。

    返回: 同 route_attack — {result: {results: [...]}, stdout}
    """
    from src.algorithms.route_mode4 import run
    return run(_dump_route(scenario), str(_output_path("route_mode4")))


@mcp.tool()
def route_return(scenario: RouteReturnInput) -> dict[str, Any]:
    """返航路径规划 — 为多平台规划返航到着陆基地的路径。

    支持多个基地，每个基地有限定容量（每种机型最多接收多少架）。
    内部使用 Theta* 搜索为每个平台规划到达指定基地的最优路径，并自动分配平台到基地。
    targets 在此接口中表示着陆基地，而非攻击目标。

    输入:
    - scenario.scenario.name (str): 任务名称
    - scenario.scenario.platforms: [{id, type, class: "aircraft"|"missile", position: [lon, lat, alt_m], speed: m/s, range: km}]
      position 应为平台当前位置（攻击完成后的位置），range 为剩余可用航程
    - scenario.scenario.targets: 着陆基地列表 [{id: 基地名称, position: [lon, lat, alt_m], capacity: {机型: 最大接收架次}}]
      若某机型的所有基地容量之和不足以接收所有该机型平台，多余的平台会出现在 unassigned 中
    - scenario.scenario.threats: [{id, type, position?, params, threat_level: 0~1}]
    - scenario.scenario.no_fly_zones: [{id, position, params}]

    威胁体类型及 params:
    - sphere: {radius: 球半径(米)}
    - cone: {max_range: 最大射程(米), angle: 锥角, direction: [dx,dy,dz] 方向向量}
    - cylinder: {radius: 半径(米), height: 高度(米)}
    - elliptic_cylinder: {semi_a: 长半轴(米), semi_b: 短半轴(米), height: 高度(米)}

    返回:
    - result: 返航分配结果 {name, total_cost, assignment: {平台ID: 基地名}, unassigned: [未分配平台], return_results: [{platform_id, aircraft_type, assigned_base}]}
    - paths_result.results: 各平台路径 [{platform, target: 基地名, cost, threat_exposure, waypoints: [[lon,lat,alt],...], crossed_threats, waypoint_details}]
    - stdout (str): 模块终端输出
    """
    from src.algorithms.route_return import run
    return run(_dump_route(scenario), str(_output_path("route_return")))


@mcp.tool()
def route_refuel(
    scenario: RouteRefuelInput,
    trajectory: Trajectory,
) -> dict[str, Any]:
    """加油点规划 — 根据路径轨迹计算每个平台飞行途中需要加油的位置。

    当 range_remaining（当前剩余航程）< range/3 时在路径上插入加油点。
    加油点安全距离固定为 5km（自动避开威胁）。
    通常在 route_attack / route_mode1-4 / route_return 之后调用。

    输入:
    - scenario.scenario.name (str): 任务名称，默认 "refuel"
    - scenario.scenario.platforms: [{id, type, class, position, speed, range: 最大航程(满油时, km), range_remaining?: 当前剩余航程(km)}]
      range 是满油状态下的最大飞行距离，range_remaining 是当前实际剩余航程。range_remaining 不填则默认等于 range（满油）。
      触发加油条件: range_remaining < range/3（即剩余油量不足满油的 1/3 时）
    - scenario.scenario.targets: [{id, position: [lon, lat, alt_m]}]
    - scenario.scenario.threats: [{id, type, position?, params, threat_level}]
    - scenario.scenario.no_fly_zones: [{id, position, params}]
    - trajectory: 路径轨迹 — 使用 route_attack / route_return 的输出
      trajectory.results: [{platform: 平台ID, target: 目标/基地ID, waypoints: [[lon, lat, alt_m], ...]}]

    返回:
    - result.results: 各平台加油结果 [{platform, target, waypoints: 完整路径,
        refuel_points: [{position: [lon, lat, alt], distance_from_start_km: 距起点距离,
          range_remaining_before_km: 加油前剩余航程, adjusted: 是否调整过位置, threat_distance_km: 距最近威胁距离}]}]
      若某平台无需加油，其 refuel_points 为空数组 []
    - stdout (str): 模块终端输出，含加油点位置信息或 "无需加油点"
    """
    from src.algorithms.route_refuel import run
    return run(
        _dump_route(scenario),
        trajectory.model_dump(exclude_none=True),
        str(_output_path("route_refuel")),
    )


# ═══════════════════════════════════════════════════════════════════
# 区域覆盖路径规划
# ═══════════════════════════════════════════════════════════════════


@mcp.tool()
def route_coverage(scenario: CoverageScenario) -> dict[str, Any]:
    """区域覆盖路径规划 — 多平台对多边形区域进行 zigzag 扫描侦查，A* 规划 cell 间转移路径。

    适用场景：
    - 无人机对指定地理区域进行全覆盖侦查扫描
    - 多个区域由不同平台分别负责，每个平台完成一个区域的 zigzag 覆盖
    - 区域内存在禁飞区时自动绕开，cell 间使用 A* 网格路径避开障碍物

    算法流程：
    1. 目标区域垂直分解为多个 cell（梯形分解，禁飞区用外接六边形近似）
    2. 每个 cell 生成 4 个入口角的 zigzag 弓形扫描线，间距 = 2 × detection_radius_km
    3. 贪心遍历：从平台出发，每次用直线距离选最近 cell 的 zigzag 端点作为入口
    4. 选中入口后，A* 计算到该入口的无障碍路径（approach / inter-cell）
    5. 沿 zigzag 完成该 cell 的覆盖，从出口继续选下一个未访问 cell
    6. 重复直到所有 cell 覆盖完毕

    输入：
    - scenario.scenario.name (str): 任务名称，默认 "coverage_mission"
    - scenario.scenario.platforms: [{id, type, class: "aircraft"|"missile", position: [lon, lat, alt_m],
        speed: m/s, range: km, detection_radius_km: 探测半径(km)}]
      detection_radius_km 控制 zigzag 扫描线间距（间距 = 2 × 半径）
    - scenario.scenario.targets: [{id, boundary: [[lon, lat], [lon, lat], ...]}]
      boundary 为多边形顶点列表（逆时针），至少 3 个顶点
    - scenario.scenario.no_fly_zones: [{id, type: "cylinder", position: [lon, lat, alt_m],
        params: {radius: 半径(km), height: 高度(m)}}]
      禁飞区为圆柱体，俯视图为圆形。cell 分解时用外接六边形近似，A* 避障用原始圆形。高度在覆盖规划中忽略
    - scenario.scenario.pairs: [{platform: 平台ID, target: 区域ID}]
      每个 pair 表示该平台负责侦查该区域。mode/waypoint_id 等字段在此场景中无作用

    返回：
    - result.results: 各 pair 的覆盖路径结果 [{platform, target,
        total_length_km: 总路径长度(km, 含 approach + zigzag + inter-cell),
        cells: cell 数量, cell_order: 遍历顺序(1-based),
        waypoints: [[lon, lat, alt_m], ...] 完整航路点坐标,
        segments: [{type: "approach"|"cell_cover"|"inter_cell",
            cell_index: cell索引(null for approach/inter_cell), length_km: 段长度(km)}]}]
    - stdout (str): 规划过程终端输出
    - 可视化 PNG (5 张/pair + overview): 保存于 output/<name>_<timestamp>/
      cell_decomp_*.png: cell 分解 + 遍历顺序
      cell_zigzag_*.png: 各 cell 的 zigzag 平行扫描线 + 线数标注
      traversal_flow_*.png: cell 间转移流程 + 实际入口/出口箭头
      full_path_*.png: 完整路径 (approach=青色实线, cell_cover=彩色实线, inter-cell=粉色虚线)
      overview.png: 所有 pair 总览
    """
    from src.algorithms.coverage_route import run
    return run(_dump_route(scenario), str(_output_path("route_coverage")))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Small Models MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse"],
        default="stdio",
        help="传输模式: stdio (本地) | http (远程)",
    )
    parser.add_argument("--host", default="0.0.0.0", help="HTTP 监听地址 (默认 0.0.0.0)")
    parser.add_argument("--port", type=int, default=11123, help="HTTP 监听端口 (默认 11123)")
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port)
