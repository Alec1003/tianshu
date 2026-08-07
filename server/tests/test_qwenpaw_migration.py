from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.agent_runtime.agents.base import QwenPawTextAgent
from app.agent_runtime.agents.builder import AgentBuilder
from app.agent_runtime.agents.model_factory import AgentModelConfig
from app.agent_runtime.events import AgentEvent
from app.agent_runtime.executor import AgentExecutor
from app.agent_runtime.runtime import AgentRuntimeRequest
from app.agent_runtime.runtime.envelope import Envelope, EnvelopeEvent
from app.agent_runtime.tools.base import ToolContext
from app.agent_runtime.tools.registry import ToolRegistry
from app.agent_runtime.tools.runtime_tools import RuntimeSkillTool
from app.ai.models import AgentExecutionSummary, CommandProposal, SkillExecutionResult


# ---------------------------------------------------------------------------
# Phase 1: QwenPawTextAgent tool-calling tests
# ---------------------------------------------------------------------------


class FakeToolRegistry:
    def __init__(self, tools=None):
        self._tools = tools or []

    def schemas(self):
        return [{"name": t, "description": t, "inputSchema": {"type": "object", "properties": {}}} for t in self._tools]

    def has_tool(self, name):
        return name in self._tools

    async def execute(self, name, arguments, context):
        if name == "whoami":
            return {"status": "ok", "identity": "tianshu-agent"}
        raise ValueError(f"Tool not found: {name}")


def make_agent(model_config=None, tool_registry=None, capability_registry=None):
    model_config = model_config or AgentModelConfig(
        provider="ollama", model="llama3", api_key="", base_url="http://localhost:11434/v1"
    )
    tool_registry = tool_registry or FakeToolRegistry(["whoami"])
    return QwenPawTextAgent(
        model_config=model_config,
        system_prompt="You are a test agent.",
        workspace_context={"user_id": "u1", "scenario_id": "s1", "tool_names": []},
        tool_registry=tool_registry,
        capability_registry=capability_registry,
        tool_context=ToolContext(
            workspace=SimpleNamespace(exported_scenario=lambda: {"name": "test"}),
            skill_registry=None,
            user_id="u1",
            scenario_id="s1",
        ),
    )


def test_qwenpaw_agent_stores_fields():
    agent = make_agent()
    assert agent.model_config.provider == "ollama"
    assert agent.system_prompt == "You are a test agent."
    assert agent.tool_registry.has_tool("whoami")
    assert agent.lifecycle is not None


def test_qwenpaw_agent_get_openai_tools():
    agent = make_agent()
    tools = agent._get_openai_tools()
    assert len(tools) == 1
    assert tools[0]["type"] == "function"
    assert tools[0]["function"]["name"] == "whoami"


def test_qwenpaw_agent_get_openai_tools_is_cached():
    agent = make_agent()
    t1 = agent._get_openai_tools()
    t2 = agent._get_openai_tools()
    assert t1 is t2


def test_qwenpaw_agent_empty_tools_when_no_registry():
    agent = make_agent(tool_registry=FakeToolRegistry([]))
    tools = agent._get_openai_tools()
    assert tools == []


def test_qwenpaw_agent_build_client(monkeypatch):
    import openai
    mock_client = MagicMock()
    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kw: mock_client)
    agent = make_agent()
    client = agent._build_client()
    assert client is mock_client


@pytest.mark.asyncio
async def test_qwenpaw_agent_provider_messages():
    agent = make_agent()
    msgs = agent._provider_messages([
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello there"},
    ])
    assert len(msgs) >= 3
    assert msgs[0]["role"] == "system"
    assert msgs[-2]["role"] == "user"
    assert msgs[-1]["role"] == "assistant"


# ---------------------------------------------------------------------------
# Phase 2: Bridge QwenPaw backend routing tests
# ---------------------------------------------------------------------------


class FakeWorkspaceForBridge:
    def __init__(self):
        self.runtime = SimpleNamespace(get_exported_scenario=lambda: {"name": "test"})
        self.skill_registry = SimpleNamespace()
        self.command_approvals = SimpleNamespace()
        self.mcp_client = None
        self.sdk_adapter = None
        self.memory_manager = SimpleNamespace()
        self.context_manager = SimpleNamespace()
        self.agent_runtime = SimpleNamespace()
        self.agent_registry = SimpleNamespace()
        self.capability_registry = SimpleNamespace()
        self.workflow_orchestrator = SimpleNamespace()
        self.driver_registry = SimpleNamespace()
        self.tool_registry = SimpleNamespace()
        self.agent = SimpleNamespace()
        self.stream_query_calls = []

    async def stream_query(self, request):
        self.stream_query_calls.append(request)
        yield EnvelopeEvent("start")
        yield EnvelopeEvent("tool_call_start", metadata={"tool": "deploy_aircraft", "arguments": {"lat": 22}})
        yield EnvelopeEvent("tool_call_end", metadata={"tool": "deploy_aircraft", "result": {"ok": True}})
        yield EnvelopeEvent("finish")


@pytest.mark.asyncio
async def test_bridge_backend_is_unified_qwenpaw(monkeypatch):
    """Bridge no longer has backend selection; always uses AgentRuntime."""
    monkeypatch.delenv("TIANSHU_AGENT_BACKEND", raising=False)
    from app.config import get_settings
    get_settings.cache_clear()
    from app.ai.bridge import TianShuOpenClawBridge
    bridge = object.__new__(TianShuOpenClawBridge)
    # _read_agent_backend removed; process_command_async always delegates to runtime
    assert hasattr(bridge, '_process_with_agent_runtime')
    assert not hasattr(bridge, '_read_agent_backend')
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_bridge_config_default_is_qwenpaw(monkeypatch):
    """Config default agent_backend is now qwenpaw."""
    monkeypatch.delenv("TIANSHU_AGENT_BACKEND", raising=False)
    from app.config import get_settings
    get_settings.cache_clear()
    assert get_settings().agent_backend == "qwenpaw"
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_bridge_process_with_agent_runtime(monkeypatch):
    from app.ai.bridge import TianShuOpenClawBridge
    bridge = object.__new__(TianShuOpenClawBridge)
    workspace = FakeWorkspaceForBridge()
    bridge.workspace = workspace
    bridge.tool_registry = SimpleNamespace()
    bridge.command_approvals = SimpleNamespace()
    bridge.agent = SimpleNamespace()
    summary = await bridge._process_with_agent_runtime("deploy aircraft")
    assert isinstance(summary, AgentExecutionSummary)
    assert summary.status == "ok"
    assert len(summary.skill_calls) == 1
    assert summary.skill_calls[0].skill == "deploy_aircraft"
    assert summary.skill_calls[0].status == "ok"
    assert len(workspace.stream_query_calls) == 1


@pytest.mark.asyncio
async def test_bridge_process_with_agent_runtime_fallback_when_no_tools(monkeypatch):
    from app.ai.bridge import TianShuOpenClawBridge
    class EmptyWorkspace:
        def __init__(self):
            self.stream_query_calls = []
        async def stream_query(self, request):
            self.stream_query_calls.append(request)
            yield EnvelopeEvent("start")
            yield EnvelopeEvent("finish")
    bridge = object.__new__(TianShuOpenClawBridge)
    workspace = EmptyWorkspace()
    bridge.workspace = workspace
    bridge.tool_registry = SimpleNamespace()
    bridge.command_approvals = SimpleNamespace()
    recording_agent = SimpleNamespace(process_command_calls=[])
    def process_cmd(command, context=None):
        recording_agent.process_command_calls.append((command, context))
        return AgentExecutionSummary(command=command, status="ok")
    recording_agent.process_command = process_cmd
    bridge.agent = recording_agent
    summary = await bridge._process_with_agent_runtime("start simulation")
    assert summary.status == "ok"
    assert len(recording_agent.process_command_calls) == 1


@pytest.mark.asyncio
async def test_bridge_process_with_agent_runtime_error_handling(monkeypatch):
    """When qwenpaw runtime produces errors with no tool results,
    it falls back to regex. When errors occur alongside tool results,
    partial status is returned."""
    from app.ai.bridge import TianShuOpenClawBridge
    class PartialWorkspace:
        def __init__(self):
            self.stream_query_calls = []
        async def stream_query(self, request):
            self.stream_query_calls.append(request)
            yield EnvelopeEvent("start")
            yield EnvelopeEvent("tool_call_start", metadata={"tool": "bad_tool", "arguments": {}})
            yield EnvelopeEvent("tool_error", "something broke", {"tool": "bad_tool", "error_type": "ValueError"})
            yield EnvelopeEvent("finish")
    bridge = object.__new__(TianShuOpenClawBridge)
    workspace = PartialWorkspace()
    bridge.workspace = workspace
    bridge.tool_registry = SimpleNamespace()
    bridge.command_approvals = SimpleNamespace()
    # With error + no results, now falls back to regex. Provide a working agent.
    recording_agent = SimpleNamespace()
    def cmd_handler(command, context=None):
        return AgentExecutionSummary(command=command, status="ok")
    recording_agent.process_command = cmd_handler
    bridge.agent = recording_agent
    summary = await bridge._process_with_agent_runtime("bad command")
    # Phase 3: no tool results triggers regex fallback
    assert summary.status == "ok"
    assert summary.command == "bad command"


@pytest.mark.asyncio
async def test_bridge_process_command_async_qwenpaw_path(monkeypatch):
    monkeypatch.setenv("TIANSHU_AGENT_BACKEND", "qwenpaw")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.ai.bridge import TianShuOpenClawBridge
    bridge = object.__new__(TianShuOpenClawBridge)
    workspace = FakeWorkspaceForBridge()
    bridge.workspace = workspace
    bridge.tool_registry = SimpleNamespace()
    bridge.command_approvals = SimpleNamespace()
    bridge.agent = SimpleNamespace()
    summary = await bridge.process_command_async("deploy aircraft")
    assert isinstance(summary, AgentExecutionSummary)
    assert summary.status == "ok"
    assert len(workspace.stream_query_calls) == 1
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_bridge_process_command_async_falls_back_to_regex(monkeypatch):
    """process_command_async uses AgentRuntime with regex fallback."""
    monkeypatch.delenv("TIANSHU_AGENT_BACKEND", raising=False)
    monkeypatch.setenv("TIANSHU_LLM_MODEL", "")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.ai.bridge import TianShuOpenClawBridge
    from app.agent_runtime.runtime.envelope import EnvelopeEvent

    class StubWorkspace:
        async def stream_query(self, request):
            yield EnvelopeEvent("start")
            yield EnvelopeEvent("finish")

    bridge = object.__new__(TianShuOpenClawBridge)
    bridge.workspace = StubWorkspace()
    bridge.tool_registry = SimpleNamespace()
    bridge.command_approvals = SimpleNamespace()
    recording_agent = SimpleNamespace()
    def cmd_handler(command, context=None):
        return AgentExecutionSummary(command=command, status="ok")
    recording_agent.process_command = cmd_handler
    bridge.agent = recording_agent

    summary = await bridge.process_command_async("start simulation")
    assert summary.status == "ok"
    assert summary.command == "start simulation"
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_bridge_propose_command_async_qwenpaw_path(monkeypatch):
    monkeypatch.setenv("TIANSHU_AGENT_BACKEND", "qwenpaw")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.ai.bridge import TianShuOpenClawBridge
    class ProposalQueue:
        def __init__(self):
            self._proposals = {}
        def get(self, pid):
            return self._proposals.get(pid)
        def create_single_step_proposal(self, *args, **kwargs):
            return SimpleNamespace(id="p-1")
    class ProposalWorkspace:
        def __init__(self):
            self.stream_query_calls = []
        async def stream_query(self, request):
            self.stream_query_calls.append(request)
            yield EnvelopeEvent("start")
            yield EnvelopeEvent(
                "tool_call_end",
                metadata={"tool": "simulation_start", "result": {"proposalId": "proposal-abc", "requiresApproval": True}},
            )
            yield EnvelopeEvent("finish")
    bridge = object.__new__(TianShuOpenClawBridge)
    workspace = ProposalWorkspace()
    bridge.workspace = workspace
    bridge.tool_registry = SimpleNamespace()
    queue = ProposalQueue()
    bridge.command_approvals = queue
    bridge.agent = SimpleNamespace()
    summary, proposals = await bridge.propose_command_async("start simulation")
    assert summary.status == "ok"
    assert len(workspace.stream_query_calls) == 1
    get_settings.cache_clear()




@pytest.mark.asyncio
async def test_bridge_qwenpaw_no_model_falls_back_to_regex(monkeypatch):
    """When qwenpaw backend is selected but no LLM is configured,
    the bridge falls back to the regex planner."""
    monkeypatch.setenv("TIANSHU_AGENT_BACKEND", "qwenpaw")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.ai.bridge import TianShuOpenClawBridge

    class ErrorWorkspace:
        def __init__(self):
            self.stream_query_calls = []
        async def stream_query(self, request):
            self.stream_query_calls.append(request)
            yield EnvelopeEvent("error", "No LLM configured", {"error_type": "NoAgentModelConfiguredError"})
            yield EnvelopeEvent("finish")

    bridge = object.__new__(TianShuOpenClawBridge)
    workspace = ErrorWorkspace()
    bridge.workspace = workspace
    bridge.tool_registry = SimpleNamespace()
    bridge.command_approvals = SimpleNamespace()

    recording_agent = SimpleNamespace(process_command_calls=[])
    def process_cmd(command, context=None):
        recording_agent.process_command_calls.append((command, context))
        return AgentExecutionSummary(command=command, status="ok")
    recording_agent.process_command = process_cmd
    bridge.agent = recording_agent

    summary = await bridge.process_command_async("start simulation")

    assert summary.status == "ok"
    assert len(recording_agent.process_command_calls) == 1
    get_settings.cache_clear()
# ---------------------------------------------------------------------------
# AgentBuilder + AgentExecutor integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_builder_creates_agent_with_tool_registry(monkeypatch):
    monkeypatch.setenv("TIANSHU_LLM_MODEL", "")
    from app.config import get_settings
    get_settings.cache_clear()
    workspace = SimpleNamespace(
        skill_registry=SimpleNamespace(capabilities=lambda: []),
        exported_scenario=lambda: {"name": "Demo"},
    )
    request = AgentRuntimeRequest(
        messages=[{"role": "user", "content": "hi"}],
        user_id="user-1",
        workspace=workspace,
        model={"provider": "ollama", "model": "llama3"},
    )
    agent = await AgentBuilder().build(request)
    assert isinstance(agent, QwenPawTextAgent)
    assert agent.model_config.provider == "ollama"
    assert agent.tool_registry.has_tool("inspect_current_scenario")
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_agent_executor_runs_qwenpaw_agent():
    class TextAgent:
        async def reply_stream(self, messages):
            yield AgentEvent("start")
            yield AgentEvent("text_delta", "hello")
            yield AgentEvent("complete")
    events = [
        event
        async for event in AgentExecutor().run(
            TextAgent(),
            [{"role": "user", "content": "hi"}],
        )
    ]
    # executor yields start -> agent events -> complete
    # agent yields start -> text_delta -> complete
    # total: 5 events
    assert len(events) == 5
    assert events[0].type == "start"
    assert events[2].type == "text_delta"
    assert events[2].content == "hello"
    assert events[4].type == "complete"


def test_message_text_string():
    from app.agent_runtime.agents.base import message_text
    assert message_text({"content": "hello"}) == "hello"


def test_message_text_list():
    from app.agent_runtime.agents.base import message_text
    assert message_text({"content": [{"text": "a"}, {"text": "b"}]}) == "a\nb"


def test_last_user_text():
    from app.agent_runtime.agents.base import last_user_text
    assert last_user_text([{"role": "user", "content": "hi"}]) == "hi"
    assert last_user_text([]) == ""
