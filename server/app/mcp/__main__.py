"""Stdio entrypoint: ``python -m app.mcp``.

为什么单独一个 __main__：
- stdio 模式下 stdout 是 MCP 协议通道，绝不能让日志/print 串扰进去，否
  则 Claude Desktop 会因为收到非 JSON 行而断连；
- 鉴权失败时要给出明确退出码 + stderr 提示，方便用户调试。

启动前置：
    set AICC_MCP_TOKEN=<jwt>   # 推荐
    或
    set AICC_MCP_USER_ID=<uuid>  # 开发模式

环境变量 ``AICC_DATABASE_URL`` 与 fastapi 后端共享同一份 SQLite 文件，
所以 server 不必先起，但要保证 ``server/data/aicc.db`` 存在。
"""

from __future__ import annotations

import logging
import sys


def _configure_logging() -> None:
    """Send all log output to stderr; keep stdout pristine for the MCP wire."""
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def main() -> None:
    _configure_logging()
    # Late import so logging config wins before mcp's own loggers attach.
    from app.mcp.server import mcp

    # FastMCP defaults transport='stdio' when called without args, but pin it
    # explicitly so future SDK default changes don't surprise us.
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
