from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.ai import bridge_registry as registry_mod
from app.ai.bridge_registry import AICCBridgeRegistry


class _FakeBridge:
    def __init__(
        self,
        *,
        scenario_path: Path,
        llm_model: str = "",
        llm_api_key: str = "",
        llm_base_url: str = "",
    ) -> None:
        self.scenario_path = scenario_path
        self.llm_model = llm_model
        self.llm_api_key = llm_api_key
        self.llm_base_url = llm_base_url
        self.runtime = SimpleNamespace(id=f"runtime:{id(self)}")


def test_bridge_registry_reuses_bridge_per_user_and_isolates_users(
    monkeypatch,
) -> None:
    monkeypatch.setattr(registry_mod, "AICCOpenClawBridge", _FakeBridge)
    scenario_path = Path("scenario.json")
    registry = AICCBridgeRegistry(
        scenario_path=scenario_path,
        llm_model="openai:test",
        llm_api_key="sk-test",
        llm_base_url="https://llm.example.test",
    )

    user_a = SimpleNamespace(id="user-a")
    user_b = SimpleNamespace(id="user-b")

    bridge_a1 = registry.get_bridge_for_user(user_a)
    bridge_a2 = registry.get_bridge_for_user(user_a)
    bridge_b = registry.get_bridge_for_user(user_b)

    assert bridge_a1 is bridge_a2
    assert bridge_a1 is not bridge_b
    assert registry.get_runtime_for_user(user_a) is bridge_a1.runtime
    assert bridge_a1.scenario_path == scenario_path
    assert bridge_a1.llm_model == "openai:test"
