"""Pydantic AI agent runtime for 天枢平台 tactical skill execution.

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
from uuid import uuid4

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIModel, OpenAIResponsesModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider

from app.ai.model_endpoint_policy import normalize_model_base_url
from app.ai.internal_skills import build_internal_skill_steps
from app.ai.models import (
    AgentExecutionSummary,
    InternalSkillDraft,
    InternalSkillMissionDraft,
    MCPCallTrace,
    SkillExecutionResult,
    StructuredCommandStep,
    TacticalPlanOptionDraft,
)
from app.ai.skill_registry import TianShuSkillRegistry


SYSTEM_PROMPT = """
You are the 天枢平台 Commander Agent — an AI operator for a tactical simulation platform.
Your job: parse natural-language tactical commands and execute them via the available tools.

Rules:
- Only call the registered tools; never invent tool names.
- For compound commands (separated by "then", ";", "然后"), call tools in sequence.
- When a required parameter is ambiguous, make the most tactically sensible assumption.
- After all tools have been called, respond with a concise single-sentence summary of what was done.
- If a tool fails, note the failure in your summary but continue with remaining operations.
""".strip()

SYSTEM_PROMPT = """
You are the 天枢平台 Commander Agent, an AI operator for a tactical simulation and training platform.
Your job is to parse natural-language tactical intent into structured simulation actions.

Rules:
- Only call the registered tools; never invent tool names.
- For compound commands separated by "then", ";", or "然后", call tools in sequence.
- When a required parameter is ambiguous, make the most tactically sensible simulation assumption.
- External MCP tools are advisory integrations. Use them to obtain plans,
  allocations, or analysis from operator-configured external servers; they are
  not the authoritative 天枢平台 simulation engine.
- Tool calls create command proposals for human approval; they do not directly mutate the simulation.
- For generated operational plans, prefer propose_tactical_plan_skill so unit
  task assignments become a reviewed proposal instead of arbitrary code.
- When asked to generate multiple operational plans or courses of action,
  first inspect the current scenario, optionally call advisory MCP tools, then
  call propose_tactical_plan_options once. Put all executable runtime actions
  for one plan inside that plan option. Do not scatter one plan across multiple
  individual write-tool calls.
- After all tools have been called, respond with a concise single-sentence summary of what was proposed.
- If a tool fails, note the failure in your summary but continue with remaining operations.
""".strip()


@dataclass
class AgentDeps:
    registry: TianShuSkillRegistry
    chat_mode: Literal["ask", "command"] = "command"
    call_log: list[SkillExecutionResult] = field(default_factory=list)
    mcp_traces: list[MCPCallTrace] = field(default_factory=list)
    approval_queue: Any | None = None
    proposal_recorder: Callable[[Any], None] | None = None
    source_command: str = ""
    mcp_client: Any | None = None
    session: Any | None = None
    user: Any | None = None
    scenario_id: str | None = None
    bridge_provider: Callable[[Any, str | None], Any] | None = None


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


def _propose_internal_skill(
    deps: AgentDeps,
    draft: InternalSkillDraft,
) -> dict[str, Any]:
    parameters = draft.model_dump(mode="json")
    if deps.chat_mode == "ask":
        return _log_tool_error(
            deps,
            skill="propose_tactical_plan_skill",
            parameters=parameters,
            error="Internal skill proposals are disabled in Ask mode.",
        )
    if deps.approval_queue is None:
        return _log_tool_error(
            deps,
            skill="propose_tactical_plan_skill",
            parameters=parameters,
            error="Approval queue is unavailable.",
        )
    try:
        steps = build_internal_skill_steps(deps.registry.runtime, draft)
        proposal = deps.approval_queue.create_proposal(
            command=deps.source_command or draft.name,
            steps=steps,
            source="internal_skill",
        )
        if deps.proposal_recorder is not None:
            deps.proposal_recorder(proposal)
        output = {
            "ok": True,
            "kind": "internal_skill_proposal",
            "proposalId": proposal.id,
            "proposalStatus": proposal.status,
            "requiresApproval": True,
            "draft": parameters,
            "adjudication": proposal.adjudication.model_dump(mode="json"),
        }
        return _log_tool_success(
            deps,
            skill="propose_tactical_plan_skill",
            parameters=parameters,
            output=output,
        )
    except Exception as exc:
        return _log_tool_error(
            deps,
            skill="propose_tactical_plan_skill",
            parameters=parameters,
            error=str(exc),
        )


def _propose_tactical_plan_options(
    deps: AgentDeps,
    options: list[TacticalPlanOptionDraft],
    command: str = "",
) -> dict[str, Any]:
    parameters = {
        "command": command,
        "options": [option.model_dump(mode="json") for option in options],
    }
    if deps.chat_mode == "ask":
        return _log_tool_error(
            deps,
            skill="propose_tactical_plan_options",
            parameters=parameters,
            error="Tactical plan proposals are disabled in Ask mode.",
        )
    if deps.approval_queue is None:
        return _log_tool_error(
            deps,
            skill="propose_tactical_plan_options",
            parameters=parameters,
            error="Approval queue is unavailable.",
        )
    if not options:
        return _log_tool_error(
            deps,
            skill="propose_tactical_plan_options",
            parameters=parameters,
            error="At least one tactical plan option is required.",
        )

    proposals = []
    try:
        for option_index, option in enumerate(options):
            steps = [
                StructuredCommandStep(
                    id=f"plan-{option_index + 1}-step-{step_index + 1}-{uuid4()}",
                    skill=step.skill,
                    parameters=step.parameters,
                    source_text=step.rationale or option.description or step.summary,
                    summary=step.summary or step.skill.replace("_", " "),
                    risk=step.risk,
                    writes_runtime=True,
                )
                for step_index, step in enumerate(option.steps)
            ]
            metadata = {
                "kind": "tactical_plan_option",
                "title": option.title,
                "label": option.label,
                "description": option.description,
                "advantages": option.advantages,
                "risks": option.risks,
                "optionIndex": option_index + 1,
                "toolCount": len(steps),
            }
            proposal = deps.approval_queue.create_proposal(
                command=command or option.title,
                steps=steps,
                source="llm_plan",
                plan_metadata=metadata,
            )
            if deps.proposal_recorder is not None:
                deps.proposal_recorder(proposal)
            proposals.append(
                {
                    "proposalId": proposal.id,
                    "proposalStatus": proposal.status,
                    "title": option.title,
                    "label": option.label,
                    "stepCount": len(steps),
                    "adjudication": proposal.adjudication.model_dump(mode="json"),
                }
            )
    except Exception as exc:
        return _log_tool_error(
            deps,
            skill="propose_tactical_plan_options",
            parameters=parameters,
            error=str(exc),
        )

    return _log_tool_success(
        deps,
        skill="propose_tactical_plan_options",
        parameters=parameters,
        output={
            "ok": True,
            "kind": "tactical_plan_options",
            "requiresApproval": True,
            "proposalCount": len(proposals),
            "proposals": proposals,
        },
    )


def _log_tool_success(
    deps: AgentDeps,
    *,
    skill: str,
    parameters: dict[str, Any],
    output: dict[str, Any],
) -> dict[str, Any]:
    deps.call_log.append(
        SkillExecutionResult(
            skill=skill,
            status="ok",
            parameters=parameters,
            output=output,
        )
    )
    return output


def _log_tool_error(
    deps: AgentDeps,
    *,
    skill: str,
    parameters: dict[str, Any],
    error: str,
) -> dict[str, Any]:
    deps.call_log.append(
        SkillExecutionResult(
            skill=skill,
            status="error",
            parameters=parameters,
            error=error,
        )
    )
    return {"ok": False, "error": error}


def _require_plan_workspace(
    deps: AgentDeps,
    *,
    skill: str,
    parameters: dict[str, Any],
) -> bool:
    if deps.session is not None and deps.user is not None and deps.scenario_id:
        return True
    _log_tool_error(
        deps,
        skill=skill,
        parameters=parameters,
        error="This tool requires an active scenario workspace.",
    )
    return False


async def _inspect_current_scenario(deps: AgentDeps) -> dict[str, Any]:
    parameters: dict[str, Any] = {}
    if deps.bridge_provider is None or deps.user is None:
        return _log_tool_error(
            deps,
            skill="inspect_current_scenario",
            parameters=parameters,
            error="Scenario inspector is unavailable.",
        )
    bridge = deps.bridge_provider(deps.user, deps.scenario_id)
    scenario = bridge.exported_scenario()
    current = (
        scenario.get("currentScenario")
        if isinstance(scenario, dict) and isinstance(scenario.get("currentScenario"), dict)
        else scenario
    )
    sides = current.get("sides") if isinstance(current, dict) else []
    output = {
        "ok": True,
        "kind": "scenario_brief",
        "scenarioId": deps.scenario_id or "",
        "scenarioName": str(current.get("name") or "") if isinstance(current, dict) else "",
        "counts": {
            "aircraft": len(current.get("aircraft") or []) if isinstance(current, dict) else 0,
            "ships": len(current.get("ships") or []) if isinstance(current, dict) else 0,
            "facilities": len(current.get("facilities") or []) if isinstance(current, dict) else 0,
            "airbases": len(current.get("airbases") or []) if isinstance(current, dict) else 0,
            "missions": len(current.get("missions") or []) if isinstance(current, dict) else 0,
            "obstacles": len(current.get("obstacles") or []) if isinstance(current, dict) else 0,
        },
        "sides": [
            {
                "id": str(side.get("id") or ""),
                "name": str(side.get("name") or ""),
                "color": side.get("color"),
            }
            for side in sides
            if isinstance(side, dict)
        ],
    }
    return _log_tool_success(
        deps,
        skill="inspect_current_scenario",
        parameters=parameters,
        output=output,
    )


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
    return normalize_model_base_url(provider, base_url)


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
    """Build a pydantic-ai Agent with all 天枢平台 skills registered as tools."""
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
        """Deploy an existing aircraft class only; never invent missing aircraft."""
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
    def create_patrol_mission(
        ctx: RunContext[AgentDeps],
        name: str,
        assigned_unit_ids: list[str],
        reference_point_ids: list[str],
    ) -> dict[str, Any]:
        """Create a patrol mission from assigned units and reference points."""
        return _exec(ctx.deps, "create_patrol_mission", {
            "name": name,
            "assigned_unit_ids": assigned_unit_ids,
            "reference_point_ids": reference_point_ids,
        })

    @agent.tool
    def create_strike_mission(
        ctx: RunContext[AgentDeps],
        name: str,
        assigned_unit_ids: list[str],
        assigned_target_ids: list[str],
    ) -> dict[str, Any]:
        """Create a strike mission from assigned attacker units and targets."""
        return _exec(ctx.deps, "create_strike_mission", {
            "name": name,
            "assigned_unit_ids": assigned_unit_ids,
            "assigned_target_ids": assigned_target_ids,
        })

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
    def propose_tactical_plan_skill(
        ctx: RunContext[AgentDeps],
        name: str,
        missions: list[InternalSkillMissionDraft],
        description: str = "",
        side_id: str = "",
        trigger_phrases: list[str] | None = None,
        constraints: list[str] | None = None,
        allowed_runtime_skills: list[str] | None = None,
        expires_at: str | None = None,
        allow_duplicate_assignments: bool = False,
    ) -> dict[str, Any]:
        """Create a temporary in-app tactical skill as a human-approved mission proposal."""
        draft = InternalSkillDraft(
            name=name,
            description=description,
            side_id=side_id,
            trigger_phrases=trigger_phrases or [],
            constraints=constraints or [],
            allowed_runtime_skills=allowed_runtime_skills or [],
            missions=missions,
            expires_at=expires_at,
            allow_duplicate_assignments=allow_duplicate_assignments,
        )
        return _propose_internal_skill(ctx.deps, draft)

    @agent.tool
    def propose_tactical_plan_options(
        ctx: RunContext[AgentDeps],
        options: list[TacticalPlanOptionDraft],
        command: str = "",
    ) -> dict[str, Any]:
        """Create approval cards for multiple tactical plan options.

        Use this when the operator asks for several courses of action. Each
        option becomes one card and may contain multiple backend runtime steps,
        such as move_unit, create_patrol_mission, create_strike_mission,
        attack_unit, update_weapon_quantity, simulation_step, or
        simulation_start. The steps execute only after human approval.
        """
        return _propose_tactical_plan_options(ctx.deps, options, command)

    @agent.tool
    def attack_unit(
        ctx: RunContext[AgentDeps],
        attacker_type: str,
        attacker_id: str,
        target_id: str,
        weapon_id: str = "",
        weapon_quantity: int = 1,
        auto: bool = False,
    ) -> dict[str, Any]:
        """Create an approval proposal for an aircraft or ship attack."""
        return _exec(
            ctx.deps,
            "attack_unit",
            {
                "attacker_type": attacker_type,
                "attacker_id": attacker_id,
                "target_id": target_id,
                "weapon_id": weapon_id,
                "weapon_quantity": weapon_quantity,
                "auto": auto,
            },
        )

    @agent.tool
    def update_weapon_quantity(
        ctx: RunContext[AgentDeps],
        unit_type: str,
        unit_id: str,
        weapon_id: str,
        increment: int,
    ) -> dict[str, Any]:
        """Create an approval proposal to adjust a unit weapon load quantity."""
        return _exec(
            ctx.deps,
            "update_weapon_quantity",
            {
                "unit_type": unit_type,
                "unit_id": unit_id,
                "weapon_id": weapon_id,
                "increment": increment,
            },
        )

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

    @agent.tool
    async def inspect_current_scenario(
        ctx: RunContext[AgentDeps],
    ) -> dict[str, Any]:
        """Read the current scenario summary."""
        return await _inspect_current_scenario(ctx.deps)

    return agent


async def run_agent(
    agent: Agent[AgentDeps, str],
    command: str,
    registry: TianShuSkillRegistry,
    approval_queue: Any | None = None,
    chat_mode: Literal["ask", "command"] = "command",
    mcp_client: Any | None = None,
    session: Any | None = None,
    user: Any | None = None,
    scenario_id: str | None = None,
    bridge_provider: Callable[[Any, str | None], Any] | None = None,
) -> AgentExecutionSummary:
    """Run the pydantic-ai agent and wrap the result in AgentExecutionSummary."""
    deps = AgentDeps(
        registry=registry,
        chat_mode=chat_mode,
        approval_queue=approval_queue,
        source_command=command,
        mcp_client=mcp_client,
        session=session,
        user=user,
        scenario_id=scenario_id,
        bridge_provider=bridge_provider,
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
