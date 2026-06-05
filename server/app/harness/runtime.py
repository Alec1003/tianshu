from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Callable, Literal, Mapping, Sequence


DEFAULT_PROFILE_NAME = "tianshu-runtime"
DEFAULT_PROFILE_DESCRIPTION = "Authoritative TianShu backend runtime harness."
DEFAULT_PROFILE_VERSION = "1.0.0"

HarnessAccess = Literal["read", "write", "control"]
HarnessInvocationSource = Literal[
    "api",
    "mcp",
    "agent",
    "internal_skill",
    "test",
    "unknown",
]
HarnessHandler = Callable[..., Any]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class HarnessProfile:
    """Runtime-shaping metadata for an TianShu harness instance.

    This mirrors the Deep Agents profile idea without importing deepagents:
    profiles tune visibility and prompt/tool metadata around a stable backend
    executor instead of changing the domain runtime itself.
    """

    name: str = DEFAULT_PROFILE_NAME
    description: str = DEFAULT_PROFILE_DESCRIPTION
    version: str = DEFAULT_PROFILE_VERSION
    system_prompt_suffix: str = ""
    tool_description_overrides: Mapping[str, str] = field(default_factory=dict)
    excluded_capabilities: frozenset[str] = field(default_factory=frozenset)
    required_capabilities: frozenset[str] = field(default_factory=frozenset)

    def merged(self, override: "HarnessProfile") -> "HarnessProfile":
        """Layer another profile on top using Deep Agents-style additive merge."""
        return HarnessProfile(
            name=(
                override.name
                if override.name != DEFAULT_PROFILE_NAME
                else self.name
            ),
            description=(
                override.description
                if override.description != DEFAULT_PROFILE_DESCRIPTION
                else self.description
            ),
            version=(
                override.version
                if override.version != DEFAULT_PROFILE_VERSION
                else self.version
            ),
            system_prompt_suffix=(
                override.system_prompt_suffix or self.system_prompt_suffix
            ),
            tool_description_overrides={
                **dict(self.tool_description_overrides),
                **dict(override.tool_description_overrides),
            },
            excluded_capabilities=(
                self.excluded_capabilities | override.excluded_capabilities
            ),
            required_capabilities=(
                self.required_capabilities | override.required_capabilities
            ),
        )


@dataclass(frozen=True)
class HarnessCapability:
    """A runtime capability exposed through API, MCP, agent, or UI adapters."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: HarnessHandler
    access: HarnessAccess = "write"
    source: str = "backend"
    version: str = "1.0.0"
    enabled: bool = True
    tags: tuple[str, ...] = field(default_factory=tuple)
    created_by: str = "TianShu Runtime"
    updated_at: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)

    @property
    def readonly(self) -> bool:
        return self.access == "read"


@dataclass(frozen=True)
class HarnessInvocation:
    capability: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    source: HarnessInvocationSource = "unknown"
    actor_id: str = ""
    scenario_id: str = ""
    request_id: str = ""


@dataclass(frozen=True)
class HarnessExecution:
    invocation: HarnessInvocation
    capability: HarnessCapability
    status: Literal["ok", "error"] = "ok"
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    started_at: str = ""
    completed_at: str = ""
    latency_ms: float = 0.0


@dataclass(frozen=True)
class HarnessCapabilityStats:
    usage_count: int = 0
    failure_count: int = 0
    last_used_at: str = ""
    last_latency_ms: float = 0.0
    last_source: HarnessInvocationSource = "unknown"
    last_actor_id: str = ""
    last_scenario_id: str = ""
    last_request_id: str = ""


class RuntimeHarness:
    """Canonical executor for runtime capabilities.

    The harness deliberately stays framework-neutral: HTTP, MCP, and agent
    adapters pass invocations in; domain capabilities remain plain callables.
    """

    def __init__(
        self,
        *,
        runtime: Any,
        name: str | None = None,
        version: str | None = None,
        profile: HarnessProfile | None = None,
        execution_log_limit: int = 200,
    ) -> None:
        self.runtime = runtime
        self.profile = profile or HarnessProfile()
        if name is not None:
            self.profile = replace(self.profile, name=name)
        if version is not None:
            self.profile = replace(self.profile, version=version)
        self.name = self.profile.name
        self.version = self.profile.version
        self.execution_log_limit = max(0, execution_log_limit)
        self._capabilities: dict[str, HarnessCapability] = {}
        self._stats: dict[str, HarnessCapabilityStats] = {}
        self._executions: list[HarnessExecution] = []

    def register(self, capability: HarnessCapability) -> None:
        if capability.name in self._capabilities:
            raise ValueError(f"Harness capability already registered: {capability.name}")
        description = self.profile.tool_description_overrides.get(
            capability.name,
            capability.description,
        )
        enabled = capability.enabled and capability.name not in self.profile.excluded_capabilities
        normalized = replace(
            capability,
            description=description,
            enabled=enabled,
            updated_at=capability.updated_at or _utc_now(),
            input_schema=capability.input_schema or capability.parameters,
        )
        self._capabilities[normalized.name] = normalized
        self._stats[normalized.name] = HarnessCapabilityStats()

    def has_capability(self, name: str) -> bool:
        return name in self._capabilities

    def get_capability(self, name: str) -> HarnessCapability:
        try:
            return self._capabilities[name]
        except KeyError as exc:
            raise ValueError(f"Harness capability not registered: {name}") from exc

    def capabilities(self) -> list[HarnessCapability]:
        return list(self._capabilities.values())

    def stats(self, name: str) -> HarnessCapabilityStats:
        self.get_capability(name)
        return self._stats[name]

    def execution_log(self, limit: int | None = None) -> list[HarnessExecution]:
        if limit is None:
            return list(self._executions)
        normalized_limit = max(0, limit)
        if normalized_limit == 0:
            return []
        return list(self._executions[-normalized_limit:])

    def execute_invocation(self, invocation: HarnessInvocation) -> HarnessExecution:
        capability = self.get_capability(invocation.capability)
        if not capability.enabled:
            raise ValueError(f"Harness capability disabled: {capability.name}")

        started_at = _utc_now()
        started = perf_counter()
        try:
            output = capability.handler(**dict(invocation.parameters))
            if output is None:
                output = {}
            if not isinstance(output, dict):
                output = {"value": output}
        except Exception as exc:
            completed_at = _utc_now()
            latency_ms = (perf_counter() - started) * 1000
            self._record_execution(
                HarnessExecution(
                    invocation=invocation,
                    capability=capability,
                    status="error",
                    error=str(exc),
                    started_at=started_at,
                    completed_at=completed_at,
                    latency_ms=latency_ms,
                )
            )
            raise

        completed_at = _utc_now()
        latency_ms = (perf_counter() - started) * 1000
        execution = HarnessExecution(
            invocation=invocation,
            capability=capability,
            output=output,
            started_at=started_at,
            completed_at=completed_at,
            latency_ms=latency_ms,
        )
        self._record_execution(execution)
        return execution

    def _record_execution(self, execution: HarnessExecution) -> None:
        previous = self._stats.get(execution.capability.name, HarnessCapabilityStats())
        self._stats[execution.capability.name] = HarnessCapabilityStats(
            usage_count=previous.usage_count + (1 if execution.status == "ok" else 0),
            failure_count=previous.failure_count + (1 if execution.status == "error" else 0),
            last_used_at=execution.completed_at,
            last_latency_ms=execution.latency_ms,
            last_source=execution.invocation.source,
            last_actor_id=execution.invocation.actor_id,
            last_scenario_id=execution.invocation.scenario_id,
            last_request_id=execution.invocation.request_id,
        )
        if self.execution_log_limit == 0:
            return
        self._executions.append(execution)
        overflow = len(self._executions) - self.execution_log_limit
        if overflow > 0:
            del self._executions[:overflow]

    def execute(
        self,
        capability: str,
        parameters: Mapping[str, Any] | None = None,
        *,
        source: HarnessInvocationSource = "unknown",
        actor_id: str = "",
        scenario_id: str = "",
        request_id: str = "",
    ) -> dict[str, Any]:
        invocation = HarnessInvocation(
            capability=capability,
            parameters=parameters or {},
            source=source,
            actor_id=actor_id,
            scenario_id=scenario_id,
            request_id=request_id,
        )
        return self.execute_invocation(invocation).output

    def verify_required_capabilities(self) -> None:
        missing = sorted(
            name for name in self.profile.required_capabilities if name not in self._capabilities
        )
        if missing:
            raise ValueError(
                f"Required harness capabilities are missing: {', '.join(missing)}"
            )

    def capability_names(self) -> Sequence[str]:
        return tuple(self._capabilities)
