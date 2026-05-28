from __future__ import annotations

import pytest

from app.ai import pydantic_agent as pa_mod
from app.ai.models import MCPCallTrace
from app.ai.pydantic_agent import (
    AgentDeps,
    _exec,
    _external_mcp_call,
    _external_mcp_list_tools,
    run_agent,
)


class RecordingRegistry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def execute(self, skill: str, params: dict) -> dict:
        self.calls.append((skill, params))
        return {"ok": True}


class RecordingApprovalQueue:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def create_single_step_proposal(
        self,
        *,
        command: str,
        skill: str,
        parameters: dict,
        source: str,
    ):
        self.calls.append((skill, parameters))
        return type(
            "Proposal",
            (),
            {
                "id": "proposal-1",
                "status": "pending",
                "adjudication": type(
                    "Adjudication",
                    (),
                    {"model_dump": lambda _self, mode=None: {"status": "needs_review"}},
                )(),
            },
        )()


def test_exec_allows_tools_in_command_mode():
    registry = RecordingRegistry()
    deps = AgentDeps(registry=registry, chat_mode="command")

    result = _exec(deps, "simulation_start", {})

    assert result == {"ok": True}
    assert registry.calls == [("simulation_start", {})]
    assert len(deps.call_log) == 1
    assert deps.call_log[0].status == "ok"


def test_exec_creates_approval_proposal_when_queue_is_present():
    registry = RecordingRegistry()
    queue = RecordingApprovalQueue()
    deps = AgentDeps(
        registry=registry,
        chat_mode="command",
        approval_queue=queue,
        source_command="start simulation",
    )

    result = _exec(deps, "simulation_start", {})

    assert result["proposalId"] == "proposal-1"
    assert result["requiresApproval"] is True
    assert registry.calls == []
    assert queue.calls == [("simulation_start", {})]
    assert deps.call_log[0].output["proposalStatus"] == "pending"


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
    assert "external_mcp_list_tools" in agent.tools
    assert "external_mcp_call" in agent.tools


class FakeMCPClient:
    def list_server_summaries(self) -> list[dict]:
        return [{"name": "planner", "enabled": True}]

    def configuration_errors(self) -> list[str]:
        return []

    async def list_tools(self, server: str | None = None):
        return (
            [
                MCPCallTrace(
                    action="list_tools",
                    target=server or "planner",
                    status="ok",
                    message="1 tools available",
                )
            ],
            [
                {
                    "server": server or "planner",
                    "name": "plan_route",
                    "description": "Plan route",
                    "inputSchema": {},
                }
            ],
        )

    async def call_tool(self, server: str, tool_name: str, arguments: dict):
        return (
            MCPCallTrace(
                action=f"call:{tool_name}",
                target=server,
                status="ok",
                message="MCP tool call succeeded",
            ),
            {"content": [{"type": "text", "text": "planned"}]},
        )


@pytest.mark.asyncio
async def test_external_mcp_list_tools_records_trace():
    deps = AgentDeps(registry=RecordingRegistry(), mcp_client=FakeMCPClient())

    result = await _external_mcp_list_tools(deps, "planner")

    assert result["tools"][0]["name"] == "plan_route"
    assert deps.mcp_traces[0].action == "list_tools"
    assert deps.call_log[0].skill == "external_mcp_list_tools"
    assert deps.call_log[0].status == "ok"


@pytest.mark.asyncio
async def test_external_mcp_call_records_result_and_trace():
    deps = AgentDeps(registry=RecordingRegistry(), mcp_client=FakeMCPClient())

    result = await _external_mcp_call(
        deps,
        "planner",
        "plan_route",
        {"unitId": "u-1"},
    )

    assert result["ok"] is True
    assert result["result"]["content"][0]["text"] == "planned"
    assert deps.mcp_traces[0].action == "call:plan_route"
    assert deps.call_log[0].skill == "external_mcp_call"
    assert deps.call_log[0].status == "ok"


class ExternalMCPAgent:
    async def run(self, command: str, *, deps: AgentDeps) -> None:
        await _external_mcp_call(deps, "planner", "plan_route", {"command": command})


@pytest.mark.asyncio
async def test_run_agent_includes_external_mcp_traces():
    summary = await run_agent(
        ExternalMCPAgent(),
        "plan route",
        RecordingRegistry(),
        mcp_client=FakeMCPClient(),
    )

    assert summary.status == "ok"
    assert summary.mcp_traces[0].action == "call:plan_route"
