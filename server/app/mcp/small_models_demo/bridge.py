"""Register the bundled small-model planning tools on TianShu's MCP server.

The source package in this directory is kept close to the upstream demo so it
can be updated independently.  This module is the only TianShu-specific
integration layer: it converts the demo's standalone FastMCP functions into
tools on the existing TianShu FastMCP instance.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .schemas import (
    CEPScenario,
    CoverageScenario,
    FeatureData,
    MCPlan,
    RefuelScenario,
    RouteAttackInput,
    RouteRefuelInput,
    RouteReturnInput,
    Trajectory,
    WTAConfig,
)


_SOURCE_ROOT = Path(__file__).resolve().parent
_DEFAULT_OUTPUT_ROOT = Path(
    os.environ.get("TIANSHU_USER_DATA_DIR", str(_SOURCE_ROOT / "output"))
) / "small_models_demo"


def _ensure_source_importable() -> None:
    source_root = str(_SOURCE_ROOT)
    if source_root not in sys.path:
        sys.path.insert(0, source_root)
    # The copied demo launches a few algorithm modules in subprocesses using
    # ``python -m wta...`` / ``python -m route_plan...``.  Both the source root
    # and its ``src`` directory must therefore be visible to child processes.
    child_paths = [source_root, str(_SOURCE_ROOT / "src")]
    existing = os.environ.get("PYTHONPATH", "")
    if existing:
        child_paths.append(existing)
    os.environ["PYTHONPATH"] = os.pathsep.join(child_paths)
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def _output_path(tool_name: str) -> str:
    output_root = Path(
        os.environ.get("TIANSHU_SMALL_MODELS_OUTPUT_DIR", str(_DEFAULT_OUTPUT_ROOT))
    )
    output_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return str(output_root / f"{tool_name}_{timestamp}.json")


def _dump_route(model: Any) -> dict[str, Any]:
    return model.model_dump(by_alias=True, exclude_none=True)


def _register_tool(mcp: FastMCP, name: str, description: str):
    """Keep registration calls uniform while retaining source tool names."""

    return mcp.tool(name=name, description=description)


def register_small_models_tools(mcp: FastMCP) -> None:
    """Register all 13 planning tools from the small-model demo."""

    @_register_tool(mcp, "wta", "WTA weapon-to-target allocation with Monte Carlo validation.")
    def wta(config: WTAConfig, mc_trials: int = 5000) -> dict[str, Any]:
        _ensure_source_importable()
        from src.algorithms.wta import run

        return run(config.model_dump(exclude_none=True), mc_trials, _output_path("wta"))

    @_register_tool(mcp, "wta_allcost", "WTA allocation prioritizing maximum firepower and confidence.")
    def wta_allcost(config: WTAConfig, mc_trials: int = 5000) -> dict[str, Any]:
        _ensure_source_importable()
        from src.algorithms.wta_allcost import run

        return run(
            config.model_dump(exclude_none=True), mc_trials, _output_path("wta_allcost")
        )

    @_register_tool(mcp, "wta_mincost", "WTA allocation optimizing for minimum cost.")
    def wta_mincost(config: WTAConfig, mc_trials: int = 5000) -> dict[str, Any]:
        _ensure_source_importable()
        from src.algorithms.wta_mincost import run

        return run(
            config.model_dump(exclude_none=True), mc_trials, _output_path("wta_mincost")
        )

    @_register_tool(mcp, "cep_match", "Match weapons to targets under CEP risk-distance constraints.")
    def cep_match(
        feature: FeatureData,
        scenario: CEPScenario,
        confidence: float | None = None,
    ) -> dict[str, Any]:
        _ensure_source_importable()
        from src.algorithms.cep_match import run

        return run(
            feature.model_dump(exclude_none=True),
            scenario.model_dump(exclude_none=True),
            confidence,
            _output_path("cep_match"),
        )

    @_register_tool(mcp, "monte_carlo", "Run Monte Carlo validation for a WTA allocation plan.")
    def monte_carlo(
        config: WTAConfig,
        plan: MCPlan,
        mc_trials: int = 5000,
        seed: int = 42,
    ) -> dict[str, Any]:
        _ensure_source_importable()
        from src.algorithms.monte_carlo import run

        return run(
            config.model_dump(exclude_none=True),
            plan.model_dump(exclude_none=True),
            mc_trials,
            seed,
            _output_path("monte_carlo"),
        )

    @_register_tool(mcp, "route_attack", "Plan attack routes using the mode in each platform-target pair.")
    def route_attack(scenario: RouteAttackInput) -> dict[str, Any]:
        _ensure_source_importable()
        from src.algorithms.route_attack import run

        return run(_dump_route(scenario), _output_path("route_attack"))

    @_register_tool(mcp, "route_mode1", "Plan direct attack routes.")
    def route_mode1(scenario: RouteAttackInput) -> dict[str, Any]:
        _ensure_source_importable()
        from src.algorithms.route_mode1 import run

        return run(_dump_route(scenario), _output_path("route_mode1"))

    @_register_tool(mcp, "route_mode2", "Plan multi-angle attack routes.")
    def route_mode2(scenario: RouteAttackInput) -> dict[str, Any]:
        _ensure_source_importable()
        from src.algorithms.route_mode2 import run

        return run(_dump_route(scenario), _output_path("route_mode2"))

    @_register_tool(mcp, "route_mode3", "Plan launch-area attack routes.")
    def route_mode3(scenario: RouteAttackInput) -> dict[str, Any]:
        _ensure_source_importable()
        from src.algorithms.route_mode3 import run

        return run(_dump_route(scenario), _output_path("route_mode3"))

    @_register_tool(mcp, "route_mode4", "Plan stealth penetration attack routes through waypoints.")
    def route_mode4(scenario: RouteAttackInput) -> dict[str, Any]:
        _ensure_source_importable()
        from src.algorithms.route_mode4 import run

        return run(_dump_route(scenario), _output_path("route_mode4"))

    @_register_tool(mcp, "route_return", "Plan return routes for platforms to landing bases.")
    def route_return(scenario: RouteReturnInput) -> dict[str, Any]:
        _ensure_source_importable()
        from src.algorithms.route_return import run

        return run(_dump_route(scenario), _output_path("route_return"))

    @_register_tool(mcp, "route_refuel", "Plan in-flight refueling points along trajectories.")
    def route_refuel(
        scenario: RouteRefuelInput,
        trajectory: Trajectory,
    ) -> dict[str, Any]:
        _ensure_source_importable()
        from src.algorithms.route_refuel import run

        return run(
            _dump_route(scenario),
            _dump_route(trajectory),
            _output_path("route_refuel"),
        )

    @_register_tool(mcp, "route_coverage", "Plan zigzag multi-platform coverage routes over polygon regions.")
    def route_coverage(scenario: CoverageScenario) -> dict[str, Any]:
        _ensure_source_importable()
        from src.algorithms.coverage_route import run

        return run(_dump_route(scenario), _output_path("route_coverage"))

    # Keep local references alive for introspection/debuggers. FastMCP owns the
    # registered tool objects; this tuple also documents the complete surface.
    _ = (
        wta,
        wta_allcost,
        wta_mincost,
        cep_match,
        monte_carlo,
        route_attack,
        route_mode1,
        route_mode2,
        route_mode3,
        route_mode4,
        route_return,
        route_refuel,
        route_coverage,
    )
