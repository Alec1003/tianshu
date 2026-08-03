from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.ai.agent import PlannedSkillCall
from app.ai.bridge import TianShuOpenClawBridge
from app.ai.models import (
    AgentExecutionSummary,
    CommandAdjudicationResult,
    CommandProposal,
    StructuredCommandStep,
)


class RecordingRegexAgent:
    def __init__(self) -> None:
        self.calls = 0

    def process_command(self, command, context=None):
        self.calls += 1
        from app.ai.models import AgentExecutionSummary
        return AgentExecutionSummary(command=command, status="ok")

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
async def test_propose_command_uses_regex_when_no_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """propose_command_async falls back to regex planner when no LLM."""
    from app.ai.bridge import TianShuOpenClawBridge
    bridge = object.__new__(TianShuOpenClawBridge)
    regex_agent = RecordingRegexAgent()
    queue = FakeApprovalQueue()
    bridge.agent = regex_agent
    bridge.command_approvals = queue
    bridge.skill_registry = object()
    bridge.mcp_client = None
    # Simple workspace stub for stream_query
    from types import SimpleNamespace
    class StubWS:
        async def stream_query(self, request):
            from app.agent_runtime.runtime.envelope import EnvelopeEvent
            yield EnvelopeEvent('start')
            yield EnvelopeEvent('finish')
    bridge.workspace = StubWS()
    bridge.tool_registry = SimpleNamespace()

    summary, proposals = await bridge.propose_command_async(
        "Deploy one BLUE F-16 at 22.1 121.5"
    )

    assert summary.status == "ok"
    assert proposals == []
    assert regex_agent.calls == 1
