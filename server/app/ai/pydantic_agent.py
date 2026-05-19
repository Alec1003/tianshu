"""Pydantic AI agent runtime for Panopticon tactical skill execution.

Each registered skill becomes a typed pydantic-ai tool so the LLM receives
proper JSON-schema descriptions and can call them with validated arguments.
Tool calls are logged in AgentDeps.call_log so the caller can build an
AgentExecutionSummary without parsing raw message history.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIModel

from app.ai.models import AgentExecutionSummary, SkillExecutionResult
from app.ai.skill_registry import PanopticonSkillRegistry


SYSTEM_PROMPT = """
You are the Panopticon Commander Agent — an AI operator for a tactical simulation platform.
Your job: parse natural-language tactical commands and execute them via the available tools.

Rules:
- Only call the registered tools; never invent tool names.
- For compound commands (separated by "then", ";", "然后"), call tools in sequence.
- When a required parameter is ambiguous, make the most tactically sensible assumption.
- After all tools have been called, respond with a concise single-sentence summary of what was done.
- If a tool fails, note the failure in your summary but continue with remaining operations.
""".strip()


@dataclass
class AgentDeps:
    registry: PanopticonSkillRegistry
    call_log: list[SkillExecutionResult] = field(default_factory=list)


def _exec(deps: AgentDeps, skill: str, params: dict[str, Any]) -> dict[str, Any]:
    """Execute a skill, log the result, and re-raise on error so pydantic-ai sees it."""
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


def resolve_model(model_id: str, api_key: str, base_url: str) -> Any:
    """Resolve a model_id string to a pydantic-ai model object.

    model_id format: "<provider>:<name>", e.g. "openai:gpt-4o" or
    "anthropic:claude-3-5-sonnet-20241022". If api_key / base_url are empty,
    pydantic-ai falls back to its own env-var lookup (OPENAI_API_KEY, etc.).
    """
    if not model_id:
        return None

    provider, _, name = model_id.partition(":")

    if provider == "openai":
        if api_key or base_url:
            from openai import AsyncOpenAI  # noqa: PLC0415

            kwargs: dict[str, Any] = {}
            if api_key:
                kwargs["api_key"] = api_key
            if base_url:
                kwargs["base_url"] = base_url
            return OpenAIModel(name or "gpt-4o", openai_client=AsyncOpenAI(**kwargs))
        return OpenAIModel(name or "gpt-4o")

    if provider == "anthropic":
        if api_key:
            from anthropic import AsyncAnthropic  # noqa: PLC0415

            return AnthropicModel(
                name or "claude-3-5-sonnet-20241022",
                anthropic_client=AsyncAnthropic(api_key=api_key),
            )
        return AnthropicModel(name or "claude-3-5-sonnet-20241022")

    # Unknown provider prefix — pass string through and let pydantic-ai handle it.
    return model_id


def build_agent(model_id: str, api_key: str = "", base_url: str = "") -> Agent[AgentDeps, str]:
    """Build a pydantic-ai Agent with all Panopticon skills registered as tools."""
    model = resolve_model(model_id, api_key, base_url)
    agent: Agent[AgentDeps, str] = Agent(
        model=model,
        deps_type=AgentDeps,
        result_type=str,
        system_prompt=SYSTEM_PROMPT,
    )

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
    def load_scenario_file(
        ctx: RunContext[AgentDeps],
        scenario_path: str,
    ) -> dict[str, Any]:
        """Load a scenario from an absolute or repo-relative file path on the server."""
        return _exec(ctx.deps, "load_scenario_file", {"scenario_path": scenario_path})

    return agent


async def run_agent(
    agent: Agent[AgentDeps, str],
    command: str,
    registry: PanopticonSkillRegistry,
) -> AgentExecutionSummary:
    """Run the pydantic-ai agent and wrap the result in AgentExecutionSummary."""
    deps = AgentDeps(registry=registry)
    summary = AgentExecutionSummary(command=command, decomposition=[command])

    try:
        await agent.run(command, deps=deps)
    except Exception as exc:
        summary.status = "error"
        summary.error = str(exc)
        summary.skill_calls = deps.call_log
        return summary

    summary.skill_calls = deps.call_log
    has_error = any(c.status == "error" for c in deps.call_log)
    if has_error and deps.call_log:
        summary.status = "partial"
    elif has_error:
        summary.status = "error"
    else:
        summary.status = "ok"
    return summary
