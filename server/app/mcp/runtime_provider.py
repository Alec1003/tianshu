"""MCP runtime provider: 单进程单 PanopticonRuntime + async 适配层。

为什么单独成文件：
- ``PanopticonRuntime`` 内部用 ``threading.RLock`` 做粒度锁，是同步阻塞。
  FastMCP 的 tool 是 async；直接调 sync 会卡住 event loop（pyd 反例 1）。
  这里集中提供 ``run_in_runtime(fn, ...)`` 用 ``asyncio.to_thread`` 把所有
  调用扔进线程池，保证 event loop 不阻塞。
- lifespan 创建 runtime 是 IO + CPU 重操作（加载 scenario JSON、初始化
  blade.Game 引擎），放进 to_thread 让 mcp 启动期不阻塞 stdin/stdout。
- 想定路径可由 ``AICC_MCP_RUNTIME_SCENARIO`` 环境变量覆盖；不指定就用
  ``client/src/scenarios/SCS.json``（与 ``ai/bridge.py`` 同源）。

边界：本切片**单进程单 runtime**。SaaS 多用户/多 scenario 隔离留给下一
切片做 runtime registry（per-scenario sandbox）。
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, TypeVar

from app.panopticon.runtime import ROOT_DIR, PanopticonRuntime

logger = logging.getLogger(__name__)

# 与 ai/bridge.DEFAULT_SCENARIO_PATH 同源；不在这里 import 是为了不依赖
# AI bridge 模块（它会一并拉起 agent / mcp_client 等无关组件）。
DEFAULT_SCENARIO_PATH = ROOT_DIR / "client" / "src" / "scenarios" / "SCS.json"

ENV_RUNTIME_SCENARIO = "AICC_MCP_RUNTIME_SCENARIO"

T = TypeVar("T")


def resolve_default_scenario_path() -> Path:
    """允许用 ``AICC_MCP_RUNTIME_SCENARIO`` 切换 runtime 启动想定。

    传相对路径时基准是项目根，不是 cwd（与 PanopticonRuntime 内部一致）。
    """
    override = os.environ.get(ENV_RUNTIME_SCENARIO, "").strip()
    if override:
        p = Path(override)
        return p if p.is_absolute() else ROOT_DIR / p
    return DEFAULT_SCENARIO_PATH


async def create_runtime_async() -> PanopticonRuntime:
    """lifespan 启动期调用：把同步构造扔线程池避免阻塞 event loop。"""
    path = resolve_default_scenario_path()
    logger.info("mcp.runtime: bootstrapping with scenario %s", path)
    return await asyncio.to_thread(PanopticonRuntime, path)


async def run_in_runtime(
    fn: Callable[..., T], /, *args: Any, **kwargs: Any
) -> T:
    """把同步 runtime 方法包成 await-able。

    所有 ``runtime_*`` MCP tool 必须经此调用，不得直接 ``runtime.xxx()``。
    后续可以在这里加：每次调用前 health-check、调用超时、metrics 上报、
    异常归一化（runtime 抛 ``ValueError`` → MCP ``ToolError``）。
    """
    return await asyncio.to_thread(fn, *args, **kwargs)
