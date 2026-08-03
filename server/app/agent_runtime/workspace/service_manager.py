from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ServiceDescriptor:
    name: str
    factory: Callable[[], Any]
    close_method: str = "close"


class ServiceManager:
    """Small workspace-scoped service owner.

    It mirrors QwenPaw's ownership pattern without introducing its service
    framework or changing existing TianShu service implementations.
    """

    def __init__(self) -> None:
        self._descriptors: dict[str, ServiceDescriptor] = {}
        self.services: dict[str, Any] = {}
        self.initialized = False

    def register(self, descriptor: ServiceDescriptor) -> None:
        self._descriptors[descriptor.name] = descriptor

    def initialize(self) -> None:
        if self.initialized:
            return
        for name, descriptor in self._descriptors.items():
            self.services[name] = descriptor.factory()
        self.initialized = True

    def close(self) -> None:
        for name in reversed(list(self.services)):
            service = self.services[name]
            close = getattr(service, self._descriptors[name].close_method, None)
            if callable(close):
                close()
        self.services.clear()
        self.initialized = False


__all__ = ["ServiceDescriptor", "ServiceManager"]
