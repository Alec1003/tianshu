"""MCP runtime provider for one process and one TianShuRuntime.

This module keeps the async/sync boundary in one place. TianShuRuntime is a
synchronous object protected by an RLock, while FastMCP tools are async. Runtime
work is therefore dispatched through asyncio.to_thread so tool handlers do not
block the event loop.

The boot scenario is resolved through app.platform.paths, so source, Docker,
and packaged desktop builds can use the same runtime entry point.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable, TypeVar

from app.tianshu_runtime.runtime import TianShuRuntime
from app.platform.paths import default_scenario_path

logger = logging.getLogger(__name__)

DEFAULT_SCENARIO_PATH = default_scenario_path()

T = TypeVar("T")


def resolve_default_scenario_path() -> Path:
    """Return the current default scenario path for runtime boot."""
    return default_scenario_path()


async def create_runtime_async() -> TianShuRuntime:
    """Construct the synchronous runtime without blocking the event loop."""
    path = resolve_default_scenario_path()
    logger.info("mcp.runtime: bootstrapping with scenario %s", path)
    return await asyncio.to_thread(TianShuRuntime, path)


async def run_in_runtime(
    fn: Callable[..., T], /, *args: Any, **kwargs: Any
) -> T:
    """Wrap a synchronous runtime call as an awaitable operation."""
    return await asyncio.to_thread(fn, *args, **kwargs)
