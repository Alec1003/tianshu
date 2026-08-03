from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from app.ai.agent import TianShuCommanderAgent
from app.ai.command_governance import CommandApprovalQueue
from app.ai.mcp_client import MCPClientSkeleton
from app.ai.openclaw_sdk_adapter import OpenClawSDKAdapter
from app.ai.skill_registry import TianShuSkillRegistry
from app.agent_runtime.context.manager import ContextManager
from app.agent_runtime.capabilities import CapabilityRegistry
from app.agent_runtime.drivers.registry import DriverRegistry
from app.agent_runtime.memory.manager import MemoryManager
from app.agent_runtime.agents.capabilities import AgentCapability
from app.agent_runtime.agents.profile import AgentProfile
from app.agent_runtime.agents.registry import AgentRegistry
from app.agent_runtime.agents.prompt import QWENPAW_TEXT_PROMPT
from app.agent_runtime.runtime import AgentRuntimeRequest, TianShuRuntimeOrchestrator
from app.agent_runtime.runtime.envelope import EnvelopeEvent
from app.agent_runtime.tools.registry import ToolRegistry
from app.agent_runtime.workflow.orchestrator import WorkflowOrchestrator
from app.agent_runtime.workspace.local_workspace import TianShuLocalWorkspace
from app.agent_runtime.workspace.plugins import WorkspacePlugins
from app.agent_runtime.workspace.service_manager import ServiceManager
from app.platform.paths import default_scenario_path
from app.tianshu_runtime.runtime import TianShuRuntime


class TianShuWorkspace:
    """Workspace-scoped owner for TianShu agent runtime services."""

    def __init__(
        self,
        *,
        user_id: str,
        scenario_id: str,
        scenario_path: Path | None = None,
        external_mcp_servers: str | None = None,
    ) -> None:
        self.user_id = user_id
        self.scenario_id = scenario_id
        self.id = self.workspace_id = f"{user_id}:{scenario_id}"
        self.scenario_path = scenario_path or default_scenario_path()
        self.external_mcp_servers = external_mcp_servers
        self.plugins = WorkspacePlugins()
        self.services = ServiceManager()
        self.local_workspace = TianShuLocalWorkspace(self)
        self._initialized = False

        self.runtime: TianShuRuntime
        self.skill_registry: TianShuSkillRegistry
        self.command_approvals: CommandApprovalQueue
        self.mcp_client: MCPClientSkeleton
        self.sdk_adapter: OpenClawSDKAdapter
        self.memory_manager: MemoryManager
        self.context_manager: ContextManager
        self.agent_runtime: TianShuRuntimeOrchestrator
        self.agent_registry: AgentRegistry
        self.capability_registry: CapabilityRegistry
        self.workflow_orchestrator: WorkflowOrchestrator
        self.driver_registry: DriverRegistry
        self.tool_registry: ToolRegistry
        self.agent: TianShuCommanderAgent

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        scenario_id: str,
        scenario_path: Path | None = None,
        external_mcp_servers: str | None = None,
    ) -> "TianShuWorkspace":
        workspace = cls(
            user_id=user_id,
            scenario_id=scenario_id,
            scenario_path=scenario_path,
            external_mcp_servers=external_mcp_servers,
        )
        workspace.initialize()
        return workspace

    def initialize(self) -> None:
        if self._initialized:
            return

        self.runtime = TianShuRuntime(scenario_path=self.scenario_path)
        self.skill_registry = TianShuSkillRegistry(runtime=self.runtime)
        self.command_approvals = CommandApprovalQueue(
            runtime=self.runtime,
            registry=self.skill_registry,
        )
        self.mcp_client = MCPClientSkeleton.from_env(self.external_mcp_servers)
        self.sdk_adapter = OpenClawSDKAdapter()
        self.memory_manager = MemoryManager()
        self.context_manager = ContextManager(memory_manager=self.memory_manager)
        self.agent_runtime = TianShuRuntimeOrchestrator(
            context_manager=self.context_manager,
        )
        self.agent_registry = AgentRegistry()
        self.agent_registry.register(
            AgentProfile(
                name="default",
                description="Default TianShu tactical assistant.",
                system_prompt=QWENPAW_TEXT_PROMPT,
                memory_scope="workspace",
                role="default_assistant",
                capabilities=[
                    AgentCapability(
                        name="text_chat",
                        description="Single-agent text conversation and tool-mediated tactical assistance.",
                    )
                ],
                metadata={"multi_agent_enabled": False},
            )
        )
        self.workflow_orchestrator = WorkflowOrchestrator()
        self.driver_registry = DriverRegistry.from_workspace(self)
        self.capability_registry = CapabilityRegistry.from_workspace(self)
        self.tool_registry = ToolRegistry.from_workspace(self)
        self.plugins.tool_registry = self.tool_registry
        self.plugins.driver_registry = self.driver_registry
        self.agent = TianShuCommanderAgent(
            skill_registry=self.skill_registry,
            mcp_client=self.mcp_client,
            sdk_adapter=self.sdk_adapter,
        )
        self._initialized = True

    def close(self) -> None:
        self._initialized = False

    def get_tools(self) -> list[Any]:
        return self.local_workspace.get_tools()

    def get_memory(self) -> MemoryManager:
        return self.memory_manager

    def get_context(self) -> ContextManager:
        return self.context_manager

    async def stream_query(
        self,
        request: AgentRuntimeRequest,
    ) -> AsyncGenerator[EnvelopeEvent, None]:
        if request.workspace is None:
            request.workspace = self
        if request.capability_registry is None:
            request.capability_registry = self.capability_registry
        if request.tool_registry is None:
            request.tool_registry = self.tool_registry
        if request.approval_queue is None and request.chat_mode == "command":
            request.approval_queue = self.command_approvals
        async for event in self.agent_runtime.run(request):
            yield event

    def exported_scenario(self) -> dict[str, Any]:
        return self.runtime.get_exported_scenario()


__all__ = ["TianShuWorkspace"]
