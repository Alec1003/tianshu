"""Pydantic AI agent runtime for AICC tactical skill execution.

Each registered skill becomes a typed pydantic-ai tool so the LLM receives
proper JSON-schema descriptions and can call them with validated arguments.
Tool calls are logged in AgentDeps.call_log so the caller can build an
AgentExecutionSummary without parsing raw message history.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIModel, OpenAIResponsesModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider

from app.ai.models import AgentExecutionSummary, MCPCallTrace, SkillExecutionResult
from app.ai.skill_registry import AICCSkillRegistry
from app.security.url_guard import normalize_and_validate_base_url


SYSTEM_PROMPT = """
You are the AICC Commander Agent — an AI operator for a tactical simulation platform.
Your job: parse natural-language tactical commands and execute them via the available tools.

Rules:
- Only call the registered tools; never invent tool names.
- For compound commands (separated by "then", ";", "然后"), call tools in sequence.
- When a required parameter is ambiguous, make the most tactically sensible assumption.
- After all tools have been called, respond with a concise single-sentence summary of what was done.
- If a tool fails, note the failure in your summary but continue with remaining operations.
""".strip()

SYSTEM_PROMPT = """
You are the AICC Commander Agent, an AI operator for a tactical simulation and training platform.
Your job is to parse natural-language tactical intent into structured simulation actions.

Rules:
- Only call the registered tools; never invent tool names.
- For compound commands separated by "then", ";", or "然后", call tools in sequence.
- When a required parameter is ambiguous, make the most tactically sensible simulation assumption.
- External MCP tools are advisory integrations. Use them to obtain plans,
  allocations, or analysis from operator-configured external servers; they are
  not the authoritative AICC simulation engine.
- Tool calls create command proposals for human approval; they do not directly mutate the simulation.
- After all tools have been called, respond with a concise single-sentence summary of what was proposed.
- If a tool fails, note the failure in your summary but continue with remaining operations.
""".strip()


@dataclass
class AgentDeps:
    registry: AICCSkillRegistry
    chat_mode: Literal["ask", "command"] = "command"
    call_log: list[SkillExecutionResult] = field(default_factory=list)
    mcp_traces: list[MCPCallTrace] = field(default_factory=list)
    approval_queue: Any | None = None
    proposal_recorder: Callable[[Any], None] | None = None
    source_command: str = ""
    mcp_client: Any | None = None


def _exec(deps: AgentDeps, skill: str, params: dict[str, Any]) -> dict[str, Any]:
    """Execute directly or create an approval proposal, then log the result."""
    if deps.chat_mode == "ask":
        error = "Tool execution is disabled in Ask mode."
        deps.call_log.append(
            SkillExecutionResult(
                skill=skill,
                status="error",
                parameters=params,
                error=error,
            )
        )
        raise PermissionError(error)
    if deps.approval_queue is not None:
        proposal = deps.approval_queue.create_single_step_proposal(
            command=deps.source_command or skill,
            skill=skill,
            parameters=params,
            source="llm_tool",
        )
        if deps.proposal_recorder is not None:
            deps.proposal_recorder(proposal)
        output = {
            "proposalId": proposal.id,
            "proposalStatus": proposal.status,
            "requiresApproval": True,
            "adjudication": proposal.adjudication.model_dump(mode="json"),
        }
        deps.call_log.append(
            SkillExecutionResult(
                skill=skill,
                status="ok",
                parameters=params,
                output=output,
            )
        )
        return output
    try:
        result = deps.registry.execute(skill, params)
        deps.call_log.append(
            SkillExecutionResult(skill=skill, status="ok", parameters=params, output=result)
        )
        return result
    except Exception as exc:
        deps.call_log.append(
            SkillExecutionResult(skill=skill, status="error", parameters=params, error=str(exc))
        )
        raise


async def _external_mcp_list_tools(
    deps: AgentDeps,
    server: str = "",
) -> dict[str, Any]:
    """List operator-configured external MCP tools for the LLM."""
    params = {"server": server}
    if deps.mcp_client is None:
        error = "No external MCP client configured."
        deps.call_log.append(
            SkillExecutionResult(
                skill="external_mcp_list_tools",
                status="error",
                parameters=params,
                error=error,
            )
        )
        return {"ok": False, "error": error, "tools": []}

    traces, tools = await deps.mcp_client.list_tools(server or None)
    deps.mcp_traces.extend(traces)
    config_errors = deps.mcp_client.configuration_errors()
    has_error = any(trace.status == "error" for trace in traces)
    should_mark_error = (has_error or bool(config_errors)) and not tools
    output = {
        "ok": not has_error and not config_errors,
        "servers": deps.mcp_client.list_server_summaries(),
        "tools": tools,
        "configurationErrors": config_errors,
        "traces": [trace.model_dump(mode="json") for trace in traces],
    }
    deps.call_log.append(
        SkillExecutionResult(
            skill="external_mcp_list_tools",
            status="error" if should_mark_error else "ok",
            parameters=params,
            output=output,
            error="Failed to list external MCP tools" if should_mark_error else None,
        )
    )
    return output


async def _external_mcp_call(
    deps: AgentDeps,
    server: str,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call an external MCP tool and log the trace."""
    params = {
        "server": server,
        "tool_name": tool_name,
        "arguments": arguments or {},
    }
    if deps.mcp_client is None:
        error = "No external MCP client configured."
        deps.call_log.append(
            SkillExecutionResult(
                skill="external_mcp_call",
                status="error",
                parameters=params,
                error=error,
            )
        )
        return {"ok": False, "error": error}

    trace, result = await deps.mcp_client.call_tool(server, tool_name, arguments or {})
    deps.mcp_traces.append(trace)
    output = {
        "ok": trace.status == "ok",
        "trace": trace.model_dump(mode="json"),
        "result": result,
    }
    deps.call_log.append(
        SkillExecutionResult(
            skill="external_mcp_call",
            status="ok" if trace.status == "ok" else "error",
            parameters=params,
            output=output,
            error=None if trace.status == "ok" else trace.message,
        )
    )
    return output


# Default base URLs for OpenAI-compatible providers. Front-end can still
# override via the `baseUrl` field; this just spares the user typing the
# obvious endpoint when they pick a known provider.
_OPENAI_COMPAT_DEFAULT_BASE_URL: dict[str, str] = {
    "deepseek": "https://api.deepseek.com/v1",
    "glm": "https://open.bigmodel.cn/api/paas/v4",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "minimax": "https://api.minimax.chat/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": "http://localhost:11434/v1",
    # google supports an OpenAI-compatible endpoint:
    # https://generativelanguage.googleapis.com/v1beta/openai/
    "google": "https://generativelanguage.googleapis.com/v1beta/openai",
}

_NO_API_KEY_PROVIDERS = {"ollama", "custom"}


def _safe_user_base_url(provider: str, base_url: str) -> str:
    """Validate user-supplied model endpoints before SDK clients can call them."""
    if not base_url.strip():
        return ""
    return normalize_and_validate_base_url(
        base_url,
        allow_private_network=provider.strip().lower() == "ollama",
    )


def can_build_model_override(
    provider: str,
    model_name: str,
    api_key: str = "",
    base_url: str = "",
) -> bool:
    """Return whether a user-supplied model config is complete enough to try."""
    provider_name = provider.strip().lower()
    if not provider_name or not model_name.strip():
        return False
    if api_key.strip():
        return True
    if provider_name == "ollama":
        return True
    if provider_name == "custom" and base_url.strip():
        return True
    return False


def resolve_model(model_id: str, api_key: str, base_url: str) -> Any:
    """Resolve a model_id string to a pydantic-ai model object.

    model_id format: "<provider>:<name>", e.g. "openai:gpt-4o" or
    "anthropic:claude-3-5-sonnet-20241022". If api_key / base_url are empty,
    pydantic-ai falls back to its own env-var lookup (OPENAI_API_KEY, etc.).

    Supported providers:
      - ``openai``:    OpenAI Chat Completions-compatible SDK + optional base_url override.
      - ``openai-responses``: OpenAI Responses API.
      - ``anthropic``: native Anthropic SDK.
      - ``deepseek`` / ``glm`` / ``qwen`` / ``minimax`` / ``openrouter`` /
        ``ollama`` / ``google`` / ``custom``:
        treated as OpenAI-compatible; uses OpenAIModel + OpenAIProvider with
        an override base_url. Each known alias has a sensible default
        endpoint (see ``_OPENAI_COMPAT_DEFAULT_BASE_URL``); ``custom``
        requires an explicit base_url.
    """
    if not model_id:
        return None

    provider, _, name = model_id.partition(":")

    if provider == "openai":
        kwargs: dict[str, Any] = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = _safe_user_base_url(provider, base_url)
        return OpenAIModel(name or "gpt-4o", provider=OpenAIProvider(**kwargs))

    if provider == "openai-responses":
        kwargs = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = _safe_user_base_url(provider, base_url)
        return OpenAIResponsesModel(
            name or "gpt-5-mini",
            provider=OpenAIProvider(**kwargs),
        )

    if provider == "anthropic":
        kwargs = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = _safe_user_base_url(provider, base_url)
        return AnthropicModel(
            name or "claude-3-5-sonnet-20241022",
            provider=AnthropicProvider(**kwargs),
        )

    if provider in _OPENAI_COMPAT_DEFAULT_BASE_URL or provider == "custom":
        effective_base = (
            _safe_user_base_url(provider, base_url)
            if base_url
            else _OPENAI_COMPAT_DEFAULT_BASE_URL.get(provider, "")
        )
        if not effective_base:
            # ``custom`` without an explicit base_url is unusable — bail out so
            # the bridge can fall back to the global agent / regex planner.
            return model_id
        kwargs = {"base_url": effective_base}
        if api_key:
            kwargs["api_key"] = api_key
        return OpenAIModel(name or "gpt-4o-mini", provider=OpenAIProvider(**kwargs))

    # Unknown provider prefix — pass string through and let pydantic-ai handle it.
    return model_id


def build_agent(
    model_id: str,
    api_key: str = "",
    base_url: str = "",
    enable_tools: bool = True,
) -> Agent[AgentDeps, str]:
    """Build a pydantic-ai Agent with all AICC skills registered as tools."""
    model = resolve_model(model_id, api_key, base_url)
    agent: Agent[AgentDeps, str] = Agent(
        model=model,
        deps_type=AgentDeps,
        output_type=str,
        system_prompt=SYSTEM_PROMPT,
    )
    if not enable_tools:
        return agent

    # ── Simulation lifecycle ──────────────────────────────────────────────────

    @agent.tool
    def simulation_start(ctx: RunContext[AgentDeps]) -> dict[str, Any]:
        """Start or resume the tactical simulation."""
        return _exec(ctx.deps, "simulation_start", {})

    @agent.tool
    def simulation_pause(ctx: RunContext[AgentDeps]) -> dict[str, Any]:
        """Pause the running simulation."""
        return _exec(ctx.deps, "simulation_pause", {})

    @agent.tool
    def simulation_stop(ctx: RunContext[AgentDeps]) -> dict[str, Any]:
        """Stop the simulation and reset it to its initial state."""
        return _exec(ctx.deps, "simulation_stop", {})

    @agent.tool
    def simulation_reset(ctx: RunContext[AgentDeps]) -> dict[str, Any]:
        """Hard-reset all simulation state (scenario reloads from initial JSON)."""
        return _exec(ctx.deps, "simulation_reset", {})

    @agent.tool
    def simulation_step(ctx: RunContext[AgentDeps], steps: int = 1) -> dict[str, Any]:
        """Advance the simulation by N time steps. Maximum 7200 steps per call (~2 sim-hours)."""
        return _exec(ctx.deps, "simulation_step", {"steps": steps})

    # ── Unit deployment ───────────────────────────────────────────────────────

    @agent.tool
    def deploy_aircraft(
        ctx: RunContext[AgentDeps],
        class_name: str,
        latitude: float,
        longitude: float,
        side: str = "BLUE",
        name: str = "",
    ) -> dict[str, Any]:
        """Deploy an aircraft unit at the given lat/lon. side: BLUE | RED | ALLY."""
        params: dict[str, Any] = {
            "class_name": class_name,
            "latitude": latitude,
            "longitude": longitude,
            "side": side,
        }
        if name:
            params["name"] = name
        return _exec(ctx.deps, "deploy_aircraft", params)

    @agent.tool
    def deploy_ship(
        ctx: RunContext[AgentDeps],
        class_name: str,
        latitude: float,
        longitude: float,
        side: str = "BLUE",
        name: str = "",
    ) -> dict[str, Any]:
        """Deploy a naval vessel at the given lat/lon. side: BLUE | RED | ALLY."""
        params: dict[str, Any] = {
            "class_name": class_name,
            "latitude": latitude,
            "longitude": longitude,
            "side": side,
        }
        if name:
            params["name"] = name
        return _exec(ctx.deps, "deploy_ship", params)

    @agent.tool
    def deploy_facility(
        ctx: RunContext[AgentDeps],
        class_name: str,
        latitude: float,
        longitude: float,
        side: str = "BLUE",
        name: str = "",
    ) -> dict[str, Any]:
        """Deploy a ground facility (radar, SAM battery, etc.) at the given lat/lon."""
        params: dict[str, Any] = {
            "class_name": class_name,
            "latitude": latitude,
            "longitude": longitude,
            "side": side,
        }
        if name:
            params["name"] = name
        return _exec(ctx.deps, "deploy_facility", params)

    @agent.tool
    def deploy_airbase(
        ctx: RunContext[AgentDeps],
        class_name: str,
        latitude: float,
        longitude: float,
        side: str = "BLUE",
        name: str = "",
    ) -> dict[str, Any]:
        """Deploy an airbase / air station at the given lat/lon."""
        params: dict[str, Any] = {
            "class_name": class_name,
            "latitude": latitude,
            "longitude": longitude,
            "side": side,
        }
        if name:
            params["name"] = name
        return _exec(ctx.deps, "deploy_airbase", params)

    @agent.tool
    def deploy_obstacle(
        ctx: RunContext[AgentDeps],
        class_name: str,
        latitude: float,
        longitude: float,
        side: str = "",
        name: str = "",
        radius_nm: float = 15.0,
        obstacle_type: str = "no_go",
        movement_penalty: float = 1.0,
        detection_penalty: float = 0.0,
        communication_penalty: float = 0.0,
        affected_domains: list[str] | None = None,
    ) -> dict[str, Any]:
        """Deploy an environment obstacle / constraint zone at the given lat/lon."""
        params: dict[str, Any] = {
            "class_name": class_name,
            "latitude": latitude,
            "longitude": longitude,
            "radius_nm": radius_nm,
            "obstacle_type": obstacle_type,
            "movement_penalty": movement_penalty,
            "detection_penalty": detection_penalty,
            "communication_penalty": communication_penalty,
            "affected_domains": affected_domains or ["aircraft", "ship"],
        }
        if side:
            params["side"] = side
        if name:
            params["name"] = name
        return _exec(ctx.deps, "deploy_obstacle", params)

    @agent.tool
    def deploy_reference_point(
        ctx: RunContext[AgentDeps],
        name: str,
        latitude: float,
        longitude: float,
        side: str = "BLUE",
    ) -> dict[str, Any]:
        """Place a named reference / waypoint marker on the map."""
        return _exec(ctx.deps, "deploy_reference_point", {
            "name": name,
            "latitude": latitude,
            "longitude": longitude,
            "side": side,
        })

    # ── Unit manipulation ─────────────────────────────────────────────────────

    @agent.tool
    def delete_unit(
        ctx: RunContext[AgentDeps],
        unit_type: str,
        unit_id: str,
    ) -> dict[str, Any]:
        """Remove a unit from the scenario. unit_type: aircraft | ship | facility | airbase."""
        return _exec(ctx.deps, "delete_unit", {"unit_type": unit_type, "unit_id": unit_id})

    @agent.tool
    def move_unit(
        ctx: RunContext[AgentDeps],
        unit_type: str,
        unit_id: str,
        route: list[list[float]],
    ) -> dict[str, Any]:
        """Order an aircraft or ship to follow a route. route: [[lat, lon], ...]. unit_type: aircraft | ship."""
        return _exec(ctx.deps, "move_unit", {
            "unit_type": unit_type,
            "unit_id": unit_id,
            "route": route,
        })

    @agent.tool
    def update_unit_state(
        ctx: RunContext[AgentDeps],
        unit_type: str,
        unit_id: str,
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        """Patch a unit's state fields (speed, fuel, name, range, etc.)."""
        return _exec(ctx.deps, "update_unit_state", {
            "unit_type": unit_type,
            "unit_id": unit_id,
            "patch": patch,
        })

    # ── Tactical events / scenario loading ───────────────────────────────────

    @agent.tool
    def trigger_tactical_event(
        ctx: RunContext[AgentDeps],
        event_name: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Fire a named tactical event with optional payload data."""
        return _exec(ctx.deps, "trigger_tactical_event", {
            "event_name": event_name,
            "payload": payload or {},
        })

    @agent.tool
    def update_situation_layer(
        ctx: RunContext[AgentDeps],
        layer_name: str,
        operation: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update a situation layer such as reference_points or obstacles."""
        return _exec(ctx.deps, "update_situation_layer", {
            "layer_name": layer_name,
            "operation": operation,
            "payload": payload or {},
        })

    @agent.tool
    def load_script(
        ctx: RunContext[AgentDeps],
        script: list[str],
    ) -> dict[str, Any]:
        """Load a scripted sequence of simulation actions for staged playback."""
        return _exec(ctx.deps, "load_script", {"script": script})

    @agent.tool
    def execute_script_step(ctx: RunContext[AgentDeps]) -> dict[str, Any]:
        """Execute the next scripted simulation step."""
        return _exec(ctx.deps, "execute_script_step", {})

    @agent.tool
    def control_script_flow(
        ctx: RunContext[AgentDeps],
        action: str,
    ) -> dict[str, Any]:
        """Control scripted playback. action: pause | resume | reset."""
        return _exec(ctx.deps, "control_script_flow", {"action": action})

    @agent.tool
    def load_scenario_snapshot(
        ctx: RunContext[AgentDeps],
        scenario_json: str,
        scenario_id: str = "",
        name: str = "",
    ) -> dict[str, Any]:
        """Load an already authorized scenario JSON snapshot."""
        params = {"scenario_json": scenario_json}
        if scenario_id:
            params["scenario_id"] = scenario_id
        if name:
            params["name"] = name
        return _exec(ctx.deps, "load_scenario_snapshot", params)

    @agent.tool
    def load_scenario_file(
        ctx: RunContext[AgentDeps],
        scenario_path: str,
    ) -> dict[str, Any]:
        """Load a scenario from an absolute or repo-relative file path on the server."""
        return _exec(ctx.deps, "load_scenario_file", {"scenario_path": scenario_path})

    # ── External MCP advisory integrations ────────────────────────────────────

    @agent.tool
    async def external_mcp_list_tools(
        ctx: RunContext[AgentDeps],
        server: str = "",
    ) -> dict[str, Any]:
        """List tools exposed by configured external MCP servers."""
        return await _external_mcp_list_tools(ctx.deps, server)

    @agent.tool
    async def external_mcp_call(
        ctx: RunContext[AgentDeps],
        server: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call a configured external MCP tool with JSON arguments."""
        return await _external_mcp_call(ctx.deps, server, tool_name, arguments)

    return agent


async def run_agent(
    agent: Agent[AgentDeps, str],
    command: str,
    registry: AICCSkillRegistry,
    approval_queue: Any | None = None,
    chat_mode: Literal["ask", "command"] = "command",
    mcp_client: Any | None = None,
) -> AgentExecutionSummary:
    """Run the pydantic-ai agent and wrap the result in AgentExecutionSummary."""
    deps = AgentDeps(
        registry=registry,
        chat_mode=chat_mode,
        approval_queue=approval_queue,
        source_command=command,
        mcp_client=mcp_client,
    )
    summary = AgentExecutionSummary(command=command, decomposition=[command])

    try:
        await agent.run(command, deps=deps)
    except Exception as exc:
        summary.status = "error"
        summary.error = str(exc)
        summary.skill_calls = deps.call_log
        summary.mcp_traces = deps.mcp_traces
        return summary

    summary.skill_calls = deps.call_log
    summary.mcp_traces = deps.mcp_traces
    has_error = any(c.status == "error" for c in deps.call_log)
    if has_error and deps.call_log:
        summary.status = "partial"
    elif has_error:
        summary.status = "error"
    else:
        summary.status = "ok"
    return summary
