from app.agent_runtime.workspace.local_workspace import TianShuLocalWorkspace
from app.agent_runtime.workspace.plugins import WorkspacePlugins
from app.agent_runtime.workspace.registry import WorkspaceRegistry
from app.agent_runtime.workspace.service_manager import ServiceDescriptor, ServiceManager

__all__ = [
    "ServiceDescriptor",
    "ServiceManager",
    "TianShuLocalWorkspace",
    "TianShuWorkspace",
    "WorkspacePlugins",
    "WorkspaceRegistry",
]


def __getattr__(name: str):
    if name == "TianShuWorkspace":
        from app.agent_runtime.workspace.workspace import TianShuWorkspace

        return TianShuWorkspace
    raise AttributeError(name)
