"""Pydantic schemas for all algorithm inputs — 使 MCP 能自动生成完整的 inputSchema."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════════════════
# 共享基础类型
# ═══════════════════════════════════════════════════════════════════

Position = list[float]  # [lon, lat, alt_m]


# ═══════════════════════════════════════════════════════════════════
# WTA 系列 (wta / wta_allcost / wta_mincost 共用)
# ═══════════════════════════════════════════════════════════════════

class SolverConfig(BaseModel):
    """求解器参数."""

    hit_probability: float = Field(default=1.0, description="命中概率回退值")
    confidence_level: float = Field(default=0.95, description="联合置信度 0~1")
    risk_confidence: float = Field(default=0.7, description="CEP 风险置信度 0~1")
    waves: int = Field(default=2, description="攻击波次数")
    loss_air_defense_damage: float = Field(default=0.8, description="防空目标失能后损伤系数")


class WTATarget(BaseModel):
    """目标定义."""

    id: int | str = Field(description="目标唯一标识")
    type: str = Field(description="目标类型（需与 target_types 匹配）")
    damage: list[float] = Field(description="[毁伤率要求, 最大毁伤值]，如 [0.9, 100]")
    risk_distance: float = Field(description="风险距离（米），越小表示越危险、对精度要求越高")


class WeaponSpec(BaseModel):
    """武器规格."""

    hardpoint: int = Field(description="挂点占用数")
    cep: float = Field(description="圆概率误差（米）")
    lethal_radius: float = Field(description="杀伤半径（米）")


class PlatformSpec(BaseModel):
    """平台规格."""

    loadout: int = Field(description="最大载弹量")


class TargetTypeSpec(BaseModel):
    """目标类型规格."""

    name: str = Field(description="类型显示名称")
    damage: dict[str, float] = Field(default_factory=dict, description="各武器对该类型的毁伤率 {武器名: 毁伤率}")
    hit_rate: dict[str, float] = Field(default_factory=dict, description="各武器对该类型的命中率 {武器名: 命中率}")
    default_hit_rate_impact: dict[str, float] | float | None = Field(
        default=None, description="可选，默认命中率影响（可为 dict 或 float）"
    )


class FeatureData(BaseModel):
    """武器/平台能力配置."""

    platforms: dict[str, PlatformSpec] = Field(description="平台名 → 平台规格")
    weapons: dict[str, WeaponSpec] = Field(description="武器名 → 武器规格")
    compatibility: dict[str, list[str]] = Field(description="平台名 → 可用武器名列表")
    target_types: dict[str, TargetTypeSpec] = Field(description="目标类型名 → 类型规格")


class BaseData(BaseModel):
    """单个基地信息 — bases_data 的值."""

    base_id: str = Field(description="基地 ID（字符串）")
    platforms: dict[str, int] = Field(description="平台名 → 可用架数")
    weapons: dict[str, int] = Field(description="武器名 → 可用数量")
    costs: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description="成本: {platform: {平台名: 成本}, weapon: {武器名: 成本}}",
    )


class WTAConfig(BaseModel):
    """WTA 场景配置."""

    solver: SolverConfig = Field(default_factory=SolverConfig, description="求解器参数")
    targets: list[WTATarget] = Field(description="目标列表")
    feature_data: FeatureData = Field(description="武器/平台能力配置")
    bases_data: dict[str, BaseData] = Field(description="基地名 → 基地信息")


# ═══════════════════════════════════════════════════════════════════
# CEP 精度-弹目匹配
# ═══════════════════════════════════════════════════════════════════

class CEPRiskTarget(BaseModel):
    """CEP 匹配风险目标."""

    id: int | str = Field(description="目标唯一标识")
    risk_distance: float = Field(description="目标风险距离（米），越小越危险")


class CEPSolverConfig(BaseModel):
    """CEP 匹配求解器参数."""

    risk_confidence: float = Field(default=0.7, description="风险置信度 0~1")


class CEPScenario(BaseModel):
    """CEP 匹配风险场景."""

    solver: CEPSolverConfig = Field(default_factory=CEPSolverConfig, description="求解器参数")
    targets: list[CEPRiskTarget] = Field(description="目标列表（含风险距离）")


# ═══════════════════════════════════════════════════════════════════
# Monte Carlo 仿真
# ═══════════════════════════════════════════════════════════════════

class PlanSortie(BaseModel):
    """架次信息."""

    base_id: int | str = Field(description="基地 ID")
    platform: str = Field(description="平台名")
    group_id: int | str = Field(description="编组 ID")
    wave: int = Field(description="波次")
    targets: list[int | str] = Field(description="分配的目标 ID 列表")
    count: int = Field(description="架次数")
    platform_cost_per_sortie: float = Field(description="每架次平台成本")


class PlanLaunch(BaseModel):
    """武器发射信息."""

    base_id: int | str = Field(description="基地 ID")
    platform: str = Field(description="平台名")
    group_id: int | str = Field(description="编组 ID")
    wave: int = Field(description="波次")
    weapon: str = Field(description="武器名")
    target_id: int | str = Field(description="目标 ID")
    count: int = Field(description="发射数量")
    weapon_cost_per_round: float = Field(description="每枚武器成本")


class PlanSummary(BaseModel):
    """方案摘要."""

    total_cost: float = Field(default=0, description="总代价")
    total_platform_cost: float = Field(default=0, description="总平台成本")
    total_weapon_cost: float = Field(default=0, description="总武器成本")
    wave_count: int = Field(default=1, description="波次数")


class MCPlan(BaseModel):
    """Monte Carlo 仿真输入方案 — WTA 输出的分配方案."""

    summary: PlanSummary = Field(default_factory=PlanSummary, description="方案摘要")
    sorties: list[PlanSortie] = Field(description="平台架次列表")
    launches: list[PlanLaunch] = Field(description="武器发射列表")


# ═══════════════════════════════════════════════════════════════════
# 路径规划系列 (attack mode1-4 / return / refuel)
# ═══════════════════════════════════════════════════════════════════

class RoutePlatform(BaseModel):
    """路径规划平台."""

    id: str = Field(description="平台唯一标识")
    type: str = Field(description="平台型号")
    class_: str = Field(alias="class", description="平台类别: aircraft | missile")
    position: Position = Field(description="起始位置 [lon, lat, alt_m]")
    speed: float = Field(description="巡航速度 (m/s)")
    range: float = Field(description="最大航程 (km)")
    initial_heading_deg: float | None = Field(default=None, description="初始朝向角 (0=北, 90=东)")
    range_remaining: float | None = Field(default=None, description="当前剩余航程 (km)，默认等于 range（refuel 用）")


class RouteWaypoint(BaseModel):
    """途经点."""

    id: str = Field(description="途经点唯一标识")
    position: Position = Field(description="途经点位置 [lon, lat, alt_m]")


class RouteTarget(BaseModel):
    """攻击目标."""

    id: str = Field(description="目标唯一标识")
    position: Position = Field(description="目标位置 [lon, lat, alt_m]")


class RouteThreat(BaseModel):
    """威胁体."""

    id: str = Field(description="威胁唯一标识")
    type: str = Field(description="威胁类型: sphere | ellipsoid | cone | cylinder | elliptic_cylinder")
    position: Position | None = Field(default=None, description="威胁位置 [lon, lat, alt_m]")
    params: dict[str, Any] = Field(description="威胁参数（依类型不同）")
    threat_level: float = Field(default=0.5, ge=0, le=1, description="威胁系数 0~1")


class RouteNoFlyZone(BaseModel):
    """禁飞区."""

    id: str = Field(description="禁飞区唯一标识")
    type: str = Field(default="cylinder", description="禁飞区类型，通常为 cylinder")
    position: Position = Field(description="禁飞区位置 [lon, lat, alt_m]")
    params: dict[str, Any] = Field(description="禁飞区参数")


class RoutePair(BaseModel):
    """平台-目标配对（攻击模式 1~4 的核心配置）."""

    platform: str = Field(description="平台 ID")
    target: str = Field(description="目标 ID")
    mode: int = Field(default=2, ge=1, le=4, description="攻击模式 1=直攻 2=多角度 3=发射区 4=隐身突防")
    waypoint_id: str | None = Field(default=None, description="mode 4 必须经过的集结点 ID")
    attack_point_radius_km: float | None = Field(default=None, description="mode 3/4 攻击点距目标距离 (km)")
    attack_point_up_height_m: float | None = Field(default=None, description="mode 3/4 攻击点高于目标的高度 (m)")


class AttackScenario(BaseModel):
    """攻击路径规划场景内容."""

    name: str = Field(description="任务名称")
    platforms: list[RoutePlatform] = Field(description="平台列表")
    waypoints: list[RouteWaypoint] = Field(default_factory=list, description="途经点列表")
    targets: list[RouteTarget] = Field(description="目标列表")
    threats: list[RouteThreat] = Field(default_factory=list, description="威胁体列表")
    no_fly_zones: list[RouteNoFlyZone] = Field(default_factory=list, description="禁飞区列表")
    pairs: list[RoutePair] = Field(description="平台-目标配对列表")


class RouteAttackInput(BaseModel):
    """攻击路径规划输入 — 外层 scenario 包装."""

    scenario: AttackScenario = Field(description="攻击场景配置")


class ReturnTarget(BaseModel):
    """返航着陆基地."""

    id: str = Field(description="基地唯一标识")
    position: Position = Field(description="基地位置 [lon, lat, alt_m]")
    capacity: dict[str, int] = Field(description="各机型最大接收架次 {机型: 容量}")


class ReturnScenario(BaseModel):
    """返航路径规划场景内容."""

    name: str = Field(description="任务名称")
    platforms: list[RoutePlatform] = Field(description="平台列表")
    targets: list[ReturnTarget] = Field(description="着陆基地列表")
    threats: list[RouteThreat] = Field(default_factory=list, description="威胁体列表")
    no_fly_zones: list[RouteNoFlyZone] = Field(default_factory=list, description="禁飞区列表")


class RouteReturnInput(BaseModel):
    """返航路径规划输入 — 外层 scenario 包装."""

    scenario: ReturnScenario = Field(description="返航场景配置")


class RefuelScenario(BaseModel):
    """加油点规划场景内容."""

    name: str = Field(default="refuel", description="任务名称")
    platforms: list[RoutePlatform] = Field(description="平台列表（含 range 和 range_remaining）")
    targets: list[RouteTarget] = Field(description="目标列表")
    threats: list[RouteThreat] = Field(default_factory=list, description="威胁体列表")
    no_fly_zones: list[RouteNoFlyZone] = Field(default_factory=list, description="禁飞区列表")


class RouteRefuelInput(BaseModel):
    """加油点规划输入 — 外层 scenario 包装."""

    scenario: RefuelScenario = Field(description="加油场景配置")


class TrajectoryWaypoint(BaseModel):
    """轨迹中的一个航路点."""

    platform: str = Field(description="平台 ID")
    target: str = Field(description="目标 ID")
    waypoints: list[Position] = Field(description="航路点列表 [[lon, lat, alt_m], ...]")


class Trajectory(BaseModel):
    """路径轨迹 — route_plan 输出结果，作为 refuel 的输入."""

    results: list[TrajectoryWaypoint] = Field(description="各平台的路径结果")


# ═══════════════════════════════════════════════════════════════════
# 区域覆盖路径规划
# ═══════════════════════════════════════════════════════════════════


class CoveragePlatform(BaseModel):
    """覆盖侦查平台 — 比 RoutePlatform 多了探测半径."""

    id: str = Field(description="平台唯一标识")
    type: str = Field(default="ReconUAV", description="平台型号")
    class_: str = Field(default="aircraft", alias="class", description="平台类别: aircraft | missile")
    position: Position = Field(description="起始位置 [lon, lat, alt_m]")
    speed: float = Field(default=250.0, description="巡航速度 (m/s)")
    range: float = Field(default=1500.0, description="最大航程 (km)")
    detection_radius_km: float = Field(default=5.0, description="探测半径 (km)，决定 zigzag 扫描线间距")


class CoverageTarget(BaseModel):
    """覆盖侦查目标区域 — 多边形边界顶点列表."""

    id: str = Field(description="目标区域唯一标识")
    boundary: list[list[float]] = Field(description="多边形边界顶点坐标 [[lon, lat], [lon, lat], ...] 逆时针")


class CoverageScenarioContent(BaseModel):
    """覆盖路径规划场景内容."""

    name: str = Field(default="coverage_mission", description="任务名称")
    platforms: list[CoveragePlatform] = Field(description="平台列表")
    targets: list[CoverageTarget] = Field(description="目标区域列表")
    no_fly_zones: list[RouteNoFlyZone] = Field(default_factory=list, description="禁飞区列表（圆柱体，俯视忽略高度）")
    pairs: list[RoutePair] = Field(description="平台-目标区域配对列表。mode/waypoint_id/attack_point 等字段在此场景中无实际作用")


class CoverageScenario(BaseModel):
    """覆盖路径规划输入 — 外层 scenario 包装."""

    scenario: CoverageScenarioContent = Field(description="覆盖路径规划场景配置")
