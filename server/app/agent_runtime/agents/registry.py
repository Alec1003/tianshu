from __future__ import annotations

from typing import Any

from app.agent_runtime.agents.profile import AgentProfile


class AgentRegistry:
    """Workspace-scoped registry for declarative agent profiles."""

    def __init__(self) -> None:
        self._profiles: dict[str, AgentProfile] = {}

    def register(self, profile: AgentProfile) -> None:
        self.register_profile(profile)

    def register_profile(self, profile: AgentProfile) -> None:
        if not profile.name:
            raise ValueError("Agent profile name is required.")
        self._profiles[profile.name] = profile

    def get(self, name: str = "default") -> AgentProfile:
        return self.get_profile(name)

    def get_profile(self, name: str = "default") -> AgentProfile:
        try:
            return self._profiles[name]
        except KeyError as exc:
            raise ValueError(f"Agent profile not registered: {name}") from exc

    def list_agents(self) -> list[AgentProfile]:
        return list(self._profiles.values())

    async def create_default_agent(self, *, request: Any, builder: Any) -> Any:
        return await self.create_agent(request=request, builder=builder, name="default")

    async def create_agent(
        self,
        *,
        request: Any,
        builder: Any,
        name: str = "default",
    ) -> Any:
        profile = self.get(name)
        build_with_profile = getattr(builder, "build_with_profile", None)
        if callable(build_with_profile):
            return await build_with_profile(request, profile)
        return await builder.build(request)


__all__ = ["AgentRegistry"]
