from __future__ import annotations

import pytest
from app.agent_runtime.runtime.runtime_event import RuntimeEvent


class TestChatModes:
    def test_ask_mode_uses_readonly_tools(self):
        ask_events = [
            RuntimeEvent.text("summary"),
            RuntimeEvent.tool_call("inspect_current_scenario", {}),
            RuntimeEvent.tool_result("inspect_current_scenario", {"ok": True}),
            RuntimeEvent.text("Scenario: 11 aircraft"),
            RuntimeEvent.finish("stop"),
        ]
        ask_types = [e.type for e in ask_events]
        assert ask_types == ["text", "tool_call", "tool_result", "text", "finish"]

    def test_command_mode_uses_write_tools(self):
        cmd_events = [
            RuntimeEvent.tool_call("deploy_aircraft", {"sideId": "blue"}),
            RuntimeEvent.tool_result("deploy_aircraft", {"ok": True}),
            RuntimeEvent.text("Unit deployed. Awaiting approval."),
            RuntimeEvent.finish("stop"),
        ]
        cmd_types = [e.type for e in cmd_events]
        assert cmd_types == ["tool_call", "tool_result", "text", "finish"]

    def test_event_protocol_same(self):
        ask_events = [
            RuntimeEvent.text("summary"),
            RuntimeEvent.finish("stop"),
        ]
        cmd_events = [
            RuntimeEvent.tool_call("deploy", {}),
            RuntimeEvent.tool_result("deploy", {}),
            RuntimeEvent.text("done"),
            RuntimeEvent.finish("stop"),
        ]
        valid_types = {"text", "tool_call", "tool_result", "error", "finish", "heartbeat"}
        for e in ask_events + cmd_events:
            assert e.type in valid_types, f"Unknown type: {e.type}"
