from __future__ import annotations

from app.ai.agent import TianShuCommanderAgent


def test_deploy_f16_without_aircraft_word_is_planned_as_aircraft() -> None:
    agent = TianShuCommanderAgent(skill_registry=None, mcp_client=None)

    calls = agent.plan_command("Deploy one BLUE F-16 at 22.1 121.5")

    assert len(calls) == 1
    assert calls[0].name == "deploy_aircraft"
    assert calls[0].parameters == {
        "class_name": "F-16C",
        "latitude": 22.1,
        "longitude": 121.5,
        "side": "BLUE",
    }


def test_deploy_f22_uses_canonical_aircraft_name() -> None:
    agent = TianShuCommanderAgent(skill_registry=None, mcp_client=None)

    calls = agent.plan_command("Deploy one BLUE F-22 at 22.1 121.5")

    assert len(calls) == 1
    assert calls[0].name == "deploy_aircraft"
    assert calls[0].parameters == {
        "class_name": "F-22 Raptor",
        "latitude": 22.1,
        "longitude": 121.5,
        "side": "BLUE",
    }
