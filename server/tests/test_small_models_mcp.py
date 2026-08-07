from __future__ import annotations

import pytest

from app.mcp.server import list_builtin_mcp_tool_definitions


@pytest.mark.asyncio
async def test_small_models_tools_are_exposed_by_builtin_mcp() -> None:
    definitions = await list_builtin_mcp_tool_definitions()
    names = {item["name"] for item in definitions}

    assert {
        "wta",
        "wta_allcost",
        "wta_mincost",
        "cep_match",
        "monte_carlo",
        "route_attack",
        "route_mode1",
        "route_mode2",
        "route_mode3",
        "route_mode4",
        "route_return",
        "route_refuel",
        "route_coverage",
    } <= names

