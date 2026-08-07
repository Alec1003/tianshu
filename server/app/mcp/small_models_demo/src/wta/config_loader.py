"""统一配置加载管线。

从场景配置（YAML/JSON）加载所有数据，统一处理：
- inline 模式（feature_data / bases_data 内联）和 file-path 模式
- 校验、波次参数、CEP 风险约束
- 返回单一 `Config` 结构体供下游使用
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.config_utils import deep_merge
from .models import (
    BaseData,
    FeatureData,
    Target,
    enforce_cep_risk_constraints,
    load_base_data,
    load_base_yaml,
    load_feature_data,
    load_feature_yaml,
    load_scenario_yaml,
    load_wave_parameters,
    log,
    validate_config,
)
from .milp_core import ensure_feasible_coverage


@dataclass
class Config:
    """完整的问题配置 — 加载 + 校验 + 预处理后的所有输入。"""

    # 全局能力
    feature_data: FeatureData

    # 基地库存
    base_data: dict[str, BaseData]

    # 目标列表（已校验）
    targets: list[Target]

    # 目标组映射: (base_id, platform) -> [target_group, ...]
    groups: dict[tuple[str, str], list[tuple[str, ...]]]

    # 波次
    wave_count: int

    # 影响矩阵: (src_id, dst_id) -> factor
    impact_matrix: dict[tuple[str, str], float]

    # solver 参数
    confidence_level: float
    hit_probability: float
    risk_confidence: float = 0.99

    # 原始 solver 配置（保留给需要其他字段的调用方）
    solver_config: dict[str, Any] = field(default_factory=dict)

    # 原始配置路径
    config_path: Path = field(default_factory=Path)


def load_config(config_path: Path, defaults: dict = None) -> Config:
    """加载场景配置，完成校验和预处理。

    同时支持 file-path 模式和 inline 模式（自动检测）。
    可选 defaults 字典用于深度合并默认配置。
    返回可直接用于 MILP 建模的完整 Config。
    """
    log(f"加载场景配置: {config_path}")
    raw = load_scenario_yaml(config_path)
    if defaults:
        raw = deep_merge(defaults, raw)

    # --- 全局能力 ---
    if "feature_data" in raw:
        feature_data = load_feature_data(raw["feature_data"])
    else:
        feature_path = (config_path.parent / raw["feature"]).resolve()
        feature_data = load_feature_yaml(feature_path)

    # --- 基地数据 ---
    base_data: dict[str, BaseData] = {}
    if "bases_data" in raw:
        for bid, item in raw["bases_data"].items():
            base_data[bid] = load_base_data(item, feature_data)
    else:
        for bid, fname in raw["bases"].items():
            base_data[bid] = load_base_yaml(
                (config_path.parent / fname).resolve(), feature_data
            )
    log(f"基地文件加载完成: bases={list(base_data.keys())}")

    # --- 目标 & 编组 ---
    targets, groups = validate_config(raw, feature_data, base_data)

    # --- 波次 ---
    wave_count, impact_matrix = load_wave_parameters(raw, targets, feature_data)

    # --- 可行性预检 ---
    ensure_feasible_coverage(feature_data, base_data, targets, groups)

    # --- solver 参数 ---
    solver_cfg = raw.get("solver", {})
    confidence_level = float(solver_cfg.get("confidence_level", 0.95))
    hit_probability = float(solver_cfg.get("hit_probability", 1.0))
    risk_confidence = float(solver_cfg.get("risk_confidence", 0.99))

    # --- CEP 风险约束 ---
    enforce_cep_risk_constraints(feature_data, targets, risk_confidence)

    return Config(
        feature_data=feature_data,
        base_data=base_data,
        targets=targets,
        groups=groups,
        wave_count=wave_count,
        impact_matrix=impact_matrix,
        confidence_level=confidence_level,
        hit_probability=hit_probability,
        risk_confidence=risk_confidence,
        solver_config=solver_cfg,
        config_path=config_path,
    )
