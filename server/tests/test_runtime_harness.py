from __future__ import annotations

import pytest

from app.harness import (
    HarnessCapability,
    HarnessInvocation,
    HarnessProfile,
    RuntimeHarness,
)


def test_runtime_harness_registers_and_executes_capability() -> None:
    calls: list[int] = []

    def handler(value: int = 0) -> dict:
        calls.append(value)
        return {"ok": True, "value": value}

    harness = RuntimeHarness(
        runtime=object(),
        profile=HarnessProfile(
            tool_description_overrides={"ping": "Overridden description."},
        ),
    )
    harness.register(
        HarnessCapability(
            name="ping",
            description="Original description.",
            parameters={"value": {"type": "integer"}},
            handler=handler,
            access="read",
            tags=("status",),
        )
    )

    capability = harness.get_capability("ping")
    assert capability.description == "Overridden description."
    assert capability.readonly is True
    assert capability.input_schema == {"value": {"type": "integer"}}

    execution = harness.execute_invocation(
        HarnessInvocation(
            capability="ping",
            parameters={"value": 7},
            source="test",
            actor_id="operator-1",
            scenario_id="scenario-1",
            request_id="request-1",
        )
    )

    assert calls == [7]
    assert execution.status == "ok"
    assert execution.output == {"ok": True, "value": 7}
    assert execution.invocation.source == "test"

    stats = harness.stats("ping")
    assert stats.usage_count == 1
    assert stats.failure_count == 0
    assert stats.last_source == "test"
    assert stats.last_actor_id == "operator-1"
    assert stats.last_scenario_id == "scenario-1"
    assert stats.last_request_id == "request-1"


def test_harness_profile_merge_preserves_base_defaults() -> None:
    base = HarnessProfile(
        name="tianshu-specialized",
        description="Specialized runtime.",
        version="2.0.0",
        tool_description_overrides={"alpha": "Alpha."},
        excluded_capabilities=frozenset({"hidden_alpha"}),
    )

    merged = base.merged(
        HarnessProfile(
            system_prompt_suffix="Keep runtime writes explicit.",
            tool_description_overrides={"beta": "Beta."},
            required_capabilities=frozenset({"simulation_step"}),
        )
    )

    assert merged.name == "tianshu-specialized"
    assert merged.description == "Specialized runtime."
    assert merged.version == "2.0.0"
    assert merged.system_prompt_suffix == "Keep runtime writes explicit."
    assert merged.tool_description_overrides == {
        "alpha": "Alpha.",
        "beta": "Beta.",
    }
    assert merged.excluded_capabilities == frozenset({"hidden_alpha"})
    assert merged.required_capabilities == frozenset({"simulation_step"})


def test_runtime_harness_rejects_duplicate_capability() -> None:
    harness = RuntimeHarness(runtime=object())
    capability = HarnessCapability(
        name="ping",
        description="Ping.",
        parameters={},
        handler=lambda: {"ok": True},
    )

    harness.register(capability)

    with pytest.raises(ValueError, match="already registered"):
        harness.register(capability)


def test_runtime_harness_rejects_disabled_capability() -> None:
    harness = RuntimeHarness(runtime=object())
    harness.register(
        HarnessCapability(
            name="disabled",
            description="Disabled.",
            parameters={},
            handler=lambda: {"ok": True},
            enabled=False,
        )
    )

    with pytest.raises(ValueError, match="disabled"):
        harness.execute("disabled", source="test")


def test_runtime_harness_normalizes_non_dict_outputs() -> None:
    harness = RuntimeHarness(runtime=object())
    harness.register(
        HarnessCapability(
            name="scalar",
            description="Scalar output.",
            parameters={},
            handler=lambda: "done",
        )
    )
    harness.register(
        HarnessCapability(
            name="none",
            description="None output.",
            parameters={},
            handler=lambda: None,
        )
    )

    assert harness.execute("scalar", source="test") == {"value": "done"}
    assert harness.execute("none", source="test") == {}
    assert harness.execution_log(limit=0) == []


def test_runtime_harness_records_handler_failures_without_swallowing() -> None:
    def handler() -> dict:
        raise RuntimeError("boom")

    harness = RuntimeHarness(runtime=object())
    harness.register(
        HarnessCapability(
            name="explode",
            description="Explode.",
            parameters={},
            handler=handler,
        )
    )

    with pytest.raises(RuntimeError, match="boom"):
        harness.execute("explode", source="test")

    stats = harness.stats("explode")
    assert stats.usage_count == 0
    assert stats.failure_count == 1
    assert harness.execution_log(limit=1)[0].status == "error"
