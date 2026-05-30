from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.ai.agent import PlannedSkillCall
from app.ai.bridge import AICCOpenClawBridge
from app.ai.models import (
    AgentExecutionSummary,
    CommandAdjudicationResult,
    CommandProposal,
    StructuredCommandStep,
)


class RecordingRegexAgent:
    def __init__(self) -> None:
        self.calls = 0

    def plan_command(self, command: str):
        self.calls += 1
        return [
            PlannedSkillCall(
                name="deploy_aircraft",
                parameters={
                    "class_name": "F-16",
                    "latitude": 22.1,
                    "longitude": 121.5,
                    "side": "BLUE",
                },
                source_text=command,
            )
        ]

    def _decompose(self, command: str) -> list[str]:
        return [command]

    def _build_no_skill_message(self, command: str) -> str:
        return f"No skill matched: {command}"


class FakeApprovalQueue:
    def __init__(self) -> None:
        self.created: CommandProposal | None = None

    def create_proposal(
        self,
        *,
        command: str,
        steps: list[StructuredCommandStep],
        source: str,
    ) -> CommandProposal:
        now = datetime.now(UTC).isoformat()
        self.created = CommandProposal(
            id="proposal-1",
            command=command,
            source=source,
            created_at=now,
            updated_at=now,
            steps=steps,
            adjudication=CommandAdjudicationResult(
                status="needs_review",
                summary="pending approval",
            ),
        )
        return self.created

    def get(self, _proposal_id: str) -> CommandProposal | None:
        return None


@pytest.mark.asyncio
async def test_propose_command_does_not_fallback_when_llm_skips_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_agent(*_args, **_kwargs) -> AgentExecutionSummary:
        return AgentExecutionSummary(
            command="Deploy one BLUE F-16 at 22.1 121.5",
            decomposition=["Deploy one BLUE F-16 at 22.1 121.5"],
        )

    monkeypatch.setattr("app.ai.pydantic_agent.run_agent", fake_run_agent)
    bridge = object.__new__(AICCOpenClawBridge)
    regex_agent = RecordingRegexAgent()
    queue = FakeApprovalQueue()
    bridge.agent = regex_agent
    bridge.command_approvals = queue
    bridge.skill_registry = object()
    bridge.mcp_client = None
    bridge._resolve_agent_for_request = lambda _context: object()

    summary, proposals = await bridge.propose_command_async(
        "Deploy one BLUE F-16 at 22.1 121.5"
    )

    assert summary.status == "ok"
    assert proposals == []
    assert regex_agent.calls == 0
    assert queue.created is None
