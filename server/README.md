# 天枢平台 Embedded Backend

## Design Summary
- Single FastAPI process.
- No extra OpenClaw gateway process and no extra OpenClaw-only port.
- 天枢平台 native simulation functions are wrapped as Skills and called in-process.
- External MCP support is client-only for operator-configured third-party servers;
  the bundled tactical planning tools below run in-process on the same TianShu MCP.

## Directory
- `app/main.py`: FastAPI app entry.
- `app/api/ai.py`: `/api/ai/command` API.
- `app/ai/agent.py`: 天枢平台 Commander agent (NL parsing + skill dispatch).
- `app/ai/openclaw_sdk_adapter.py`: Embedded OpenClaw SDK adapter seam (in-process).
- `app/ai/skill_registry.py`: Skill definitions and registration.
- `app/ai/mcp_client.py`: external MCP client for stdio / Streamable HTTP servers.
- `app/ai/bridge.py`: Unified OpenClaw bridge module.
- `app/mcp/small_models_demo/`: copied small-model planning algorithms and MCP source.
- `app/tianshu_runtime/runtime.py`: Native engine runtime adapter (calls `gym/blade` in-process).

## Install
```bash
cd server
pip install -r requirements.txt
```

## Run
```bash
cd server
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Core API
### POST `/api/ai/command`
Request:
```json
{
  "command": "启动仿真并单步推演3步",
  "context": {}
}
```

Response fields:
- `status`: `ok|partial|error`
- `execution.skill_calls`: each skill execution result
- `scenario`: exported scenario object for frontend map refresh

## Extension Areas
- Skill validation/audit hook:
  - `app/ai/skill_registry.py` in `execute()`
- OpenClaw SDK planning hook:
  - `app/ai/openclaw_sdk_adapter.py`
  - `app/ai/agent.py` in `_plan_with_sdk()`
- MCP external services:
  - `app/ai/mcp_client.py`
  - `TIANSHU_EXTERNAL_MCP_SERVERS` JSON config

Example external MCP config:

```powershell
$env:TIANSHU_EXTERNAL_MCP_SERVERS='[
  {
    "name": "planner",
    "transport": "stdio",
    "command": "python",
    "args": ["-m", "my_planner_mcp"],
    "allowedTools": ["plan_route"]
  },
  {
    "name": "remote-planner",
    "transport": "streamable_http",
    "url": "http://127.0.0.1:9000/mcp",
    "headers": {"Authorization": "Bearer <token>"}
  }
]'
```


## 天枢平台 MCP Server (Sprint 1 / P0)

把天枢平台的想定（scenarios）+ 单位 + 威胁 + AAR 通过标准 [Model Context
Protocol](https://modelcontextprotocol.io) 暴露给任意 MCP 客户端
（Claude Desktop、Cursor、自家 agent runtime、hermes-agent 等）。

### Capabilities

Native scenario/runtime tools plus **13 bundled planning tools** + 2 resources + 1 resource template，分为三组：

#### Bundled small-model planning tools（13 tools）
- `wta` / `wta_allcost` / `wta_mincost`
- `cep_match` / `monte_carlo`
- `route_attack` / `route_mode1` / `route_mode2` / `route_mode3` / `route_mode4`
- `route_return` / `route_refuel` / `route_coverage`

The algorithms are copied under `app/mcp/small_models_demo/` and are registered on the
same stdio and Streamable HTTP MCP server. Their generated result JSON files default to
`TIANSHU_USER_DATA_DIR/small_models_demo`; override with
`TIANSHU_SMALL_MODELS_OUTPUT_DIR` when needed.

#### A. DB scenarios组（静态快照、面向持久化，12 tools）

- **读**：`list_scenarios` / `get_scenario` / `get_scenario_statistics`
  / `list_units` / `get_unit_detail` / `query_threats`
- **写**：`create_scenario` / `update_scenario_meta` /
  `update_scenario_data` / `delete_scenario`
- **AAR**：`list_aar_records` / `post_aar_record`
- **资源**：`tianshu://scenarios`（清单）、`tianshu://scenario/{id}`（详情）

#### B. Runtime组（活想定、面向 AI 推演控制，15 tools）

- **生命周期**：`runtime_status` / `runtime_start` / `runtime_pause` /
  `runtime_reset` / `runtime_step(steps)`
- **DB ↔ Runtime 桥接**：`runtime_load_scenario_from_db` /
  `runtime_export_scenario` / `runtime_save_to_db`
- **部署**：`runtime_deploy_aircraft` / `runtime_deploy_ship` /
  `runtime_deploy_facility` / `runtime_deploy_airbase`
- **单位控制**：`runtime_move_unit` / `runtime_delete_unit`
- **事件**：`runtime_set_relationship` / `runtime_set_current_side`
- **胜负**：`runtime_get_outcome`
- **资源**：`tianshu://runtime`（活想定实时快照）

> **两组不同源，不会自动同步**：
> - DB 组读写 ``Scenario`` 表（静态快照）
> - Runtime 组读写进程内 ``TianShuRuntime``（内存活想定）
> - 要把 DB 中的一个想定接管进推演，调 ``runtime_load_scenario_from_db``。
> - 要把当前推演中的活想定持久化，调 ``runtime_save_to_db``。

权限模型完全复用 HTTP API：同一个 fastapi-users 用户 + 同一个 JWT。

### Run (stdio mode, for Claude Desktop)

stdio 模式启动前要给两条凭证之一：

| 变量 | 说明 |
| --- | --- |
| `TIANSHU_MCP_TOKEN` | （推荐）fastapi-users 签发的 JWT，复用 `/api/auth/jwt/login` 的返回值 |
| `TIANSHU_MCP_USER_ID` | （开发模式）直接用 user UUID，跳过 JWT；上线后不建议使用 |

`TIANSHU_DATABASE_URL` / `TIANSHU_JWT_SECRET` 必须与 FastAPI 后端使用同一份值，
否则 token 解码失败。

启动命令：

```powershell
# 用 token
$env:TIANSHU_MCP_TOKEN = "<jwt-from-login>"
& "..\.python312\python.exe" -m app.mcp
```

```bash
# Linux/macOS 同理
TIANSHU_MCP_TOKEN=<jwt> python -m app.mcp
```

stdout 是协议通道（不要 print），日志走 stderr。

### Claude Desktop 接入

`~/Library/Application Support/Claude/claude_desktop_config.json`
（macOS）或 `%APPDATA%\Claude\claude_desktop_config.json`（Windows）：

```json
{
  "mcpServers": {
    "tianshu": {
      "command": "<repo>\\.python312\\python.exe",
      "args": ["-m", "app.mcp"],
      "cwd": "<repo>\\server",
      "env": {
        "TIANSHU_MCP_TOKEN": "<jwt>",
        "TIANSHU_DATABASE_URL": "sqlite+aiosqlite:///./data/tianshu.db",
        "TIANSHU_JWT_SECRET": "<same-as-fastapi>"
      }
    }
  }
}
```

重启 Claude Desktop 后会在工具栏看到 `tianshu`，可以让模型：

- 列出我所有想定
- 读 `tpl-blank_scenario` 的 sides 列表
- 给我 RED 视角下的威胁排序
- 在我已有的 `<scenario-id>` 上创建一条 AAR 记录

### AI 推演控制（双方作战清单 → 全自动推演）

拿到一份资深双方作战清单后，LLM（Claude Desktop / Cursor / 自家
agent）可以走这条决策环完成一场推演，不需人介入：

```
1. list_scenarios                            # 看可选起点
2. runtime_load_scenario_from_db(scenario_id)# DB → 内存引擎
3. runtime_set_current_side(side="BLUE")
4. for o in blue_orders:                     # AI BLUE 按清单部署
     runtime_deploy_aircraft / runtime_move_unit / ...
5. runtime_set_current_side(side="RED")
6. for o in red_orders:                      # AI RED 同上
     ...
7. runtime_set_relationship(side="BLUE", hostiles=["RED"])
8. runtime_start
9. while True:                               # 主循环
     runtime_step(steps=30)
     situation = query_threats(side_id=...) # 或 read tianshu://runtime
     # AI 看新态势 → 决策 → runtime_move_unit / runtime_deploy_*
     outcome = runtime_get_outcome
     if outcome.time_up or outcome.inferred_winner_side_id: break
10. runtime_save_to_db(name="推演结果-2026-05-19")
11. post_aar_record(scenario_id=..., outcome_reason=..., winner_side_id=...)
```

关键语义：

- `runtime_step(steps=N)` = 推进 N 仿真秒，含交战 / 探测 / 单位运动。
  单次上限 7200 步（= 2 小时仿真），超过请拆多次调用。
- `runtime_get_outcome` 返回 **time_up + 各方存活状况 + 推断赢家**三
  路信号（后端 ``blade.Game.check_game_ended`` 当前是占位）。LLM 应
  结合清单中的胜负条件自行终止，不要依赖单字段 ``ended``。
- 仿真实例 **单进程单 runtime**：stdio 模式下每启一次
  ``python -m app.mcp`` 就是一个独立 runtime；同一进程中的多次 tool
  调用共享同一份活想定。多用户 / 多想定 SaaS 隔离要等 runtime
  registry 切片。
- 启动时默认加载 ``client/src/scenarios/SCS.json``；可用
  ``TIANSHU_MCP_RUNTIME_SCENARIO`` 环境变量指向别的想定 JSON。

### Streamable HTTP（已完成 ✅）

MCP 现在 **同时** 支持两种传输：

| 传输 | 适用场景 | 端点 | 鉴权 |
|---|---|---|---|
| **stdio** | Claude Desktop / Cursor / 本地 agent | `python -m app.mcp` | ENV `TIANSHU_MCP_TOKEN` 或 `TIANSHU_MCP_USER_ID` |
| **HTTP** | 前端 AI Sidebar / 远程 agent / mcp-inspector | `POST /api/mcp/` | `Authorization: Bearer <jwt>` per-request |

HTTP 模式核心特性：

- **共享 runtime**：MCP tool 与 `/api/ai/command` 操作 **同一个**
  `TianShuRuntime` 实例（`app.state.bridge.runtime`）。AI 通过 MCP
  部署 / step → 后端 runtime 立即更新。
  > **注意**：前端浏览器有自己的 client-side `Game`（`client/src/game/Game.ts`），
  > 地图从 `game.currentScenario` 渲染，**不会自动轮询后端**。要让前端看到
  > MCP 的改动，需要前端主动调 `GET /api/ai/runtime/scenario` 拿后端快照
  > → `game.loadScenario(json)` 刷新。AI Sidebar 切片会加自动刷新。
- **per-request JWT**：复用 fastapi-users 签发的 JWT（`/api/auth/jwt/login`
  的返回值）；每个 HTTP 请求独立校验，无 token / 过期 token 返回 401 +
  `WWW-Authenticate`。
- **CORS**：FastAPI `CORSMiddleware` 从 `TIANSHU_CORS_ORIGINS` 读取显式 origin；配置层会拒绝 wildcard origin。
- **session**：MCP 会话 ID 在 `Mcp-Session-Id` 响应头返回；后续请求需回传。
- **dev 捷径**：设 `TIANSHU_MCP_HTTP_DEV_USER_ID=<uuid>` 可跳过 token 校验
  （仅限本地调试，日志会 warning）。

#### Claude Desktop HTTP 接入（新版 ≥1.x）

```json
{
  "mcpServers": {
    "tianshu-http": {
      "url": "http://localhost:8000/api/mcp/",
      "headers": {
        "Authorization": "Bearer <jwt>"
      }
    }
  }
}
```

> 新版 Claude Desktop 支持 `url` 字段直连 Streamable HTTP，不再需要
> `command` / `args`。旧版仍可用 stdio 配置（见上方）。

#### mcp-inspector 快速验证

```bash
npx @anthropic-ai/mcp-inspector --url http://localhost:8000/api/mcp/ \
  -H "Authorization: Bearer <jwt>"
```

### Tests

```powershell
cd server
& "..\.python312\python.exe" -m pytest tests/ -v
```

当前覆盖（38 passed）：
- `tests/test_mcp_utils.py` — scenario.data → sides/units/threats 解析
- `tests/test_scenarios_service.py` — service 层 CRUD + 权限 + AAR
- `tests/test_mcp_runtime.py` — runtime status/outcome 计算逻辑 + ``run_in_runtime``
  严格走线程池（避免阻塞 event loop）

端到端验证已覆盖：
- **stdio lifespan 烟雾**：TianShuRuntime 加载 SCS 想定（3 sides / 14
  aircraft / 5 airbases），`runtime_step` 推进仿真时间。
- **HTTP 8 步烟雾**：①无 token 401 ②假 token 401 ③注册+登录拿 JWT
  ④ JSON-RPC initialize ⑤ tools/list=29 ⑥ runtime_status ⑦
  runtime_deploy_aircraft ⑧ `/api/ai/command` 确认 MCP 部署的飞机可见
  （证明 runtime 共享）。
