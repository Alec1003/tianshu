from __future__ import annotations

import pytest

from app.ai import pydantic_agent as pa_mod
from app.ai.pydantic_agent import AgentDeps, _exec


class RecordingRegistry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def execute(self, skill: str, params: dict) -> dict:
        self.calls.append((skill, params))
        return {"ok": True}


def test_exec_allows_tools_in_command_mode():
    registry = RecordingRegistry()
    deps = AgentDeps(registry=registry, chat_mode="command")

    result = _exec(deps, "simulation_start", {})

    assert result == {"ok": True}
    assert registry.calls == [("simulation_start", {})]
    assert len(deps.call_log) == 1
    assert deps.call_log[0].status == "ok"


def test_exec_blocks_tools_in_ask_mode():
    registry = RecordingRegistry()
    deps = AgentDeps(registry=registry, chat_mode="ask")

    with pytest.raises(PermissionError, match="disabled in Ask mode"):
        _exec(deps, "simulation_start", {})

    assert registry.calls == []
    assert len(deps.call_log) == 1
    assert deps.call_log[0].status == "error"
    assert deps.call_log[0].skill == "simulation_start"


class RecordingAgent:
    def __init__(self, **_kwargs) -> None:
        self.tools: list[str] = []

    def tool(self, func):
        self.tools.append(func.__name__)
        return func


def test_build_agent_can_disable_tool_registration(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(pa_mod, "resolve_model", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(pa_mod, "Agent", RecordingAgent)

    agent = pa_mod.build_agent("openai:gpt-4o-mini", enable_tools=False)

    assert agent.tools == []


def test_build_agent_registers_tools_by_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(pa_mod, "resolve_model", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(pa_mod, "Agent", RecordingAgent)

    agent = pa_mod.build_agent("openai:gpt-4o-mini")

    assert "simulation_start" in agent.tools
    assert "deploy_aircraft" in agent.tools
