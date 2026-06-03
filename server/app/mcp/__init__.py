"""TianShu MCP server package.

暴露仿真控制能力为标准 Model Context Protocol，让 Claude Desktop /
Cursor / 自家 agent runtime / hermes-agent 等任何 MCP 客户端都能通过同
一套契约读懂态势 + 操作想定。

入口：
    python -m app.mcp           # stdio 模式（推荐 Claude Desktop 接入）

挂载到现有 FastAPI 的 Streamable HTTP 模式留给下一切片实现。
"""
