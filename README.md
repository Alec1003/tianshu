# AICC 大模型指挥控制平台

AICC 是一个面向作战想定推演、态势显示和大模型辅助指挥的 Web 平台。当前主入口是 `http://localhost:3000/`，前端以 Cesium 地图为核心承载想定场景，后端提供嵌入式 AICC 风格的 AI 指令执行能力。

本 README 以当前仓库代码为准，已移除旧平台官网、Discord 和过期本地路径说明。

## 当前能力

| 能力 | 说明 |
| --- | --- |
| 想定地图 | 使用 Cesium 渲染二维/三维态势地图，默认加载 `client/src/scenarios/SCS.json`。 |
| 作战实体 | 支持飞机、舰船、机场、设施、参考点等实体的显示、部署、移动、删除和状态更新。 |
| 图层切换 | 内置高德中文矢量、高德卫星、CartoDB 暗色底图和 Sentinel-2 开放影像。 |
| AI 指挥面板 | 前端通过 `VITE_AI_SERVER_URL` 连接 FastAPI 后端，提交自然语言指令并接收执行结果。 |
| Skill 桥接 | 后端将 AI 指令映射到仿真控制、实体部署、路径规划、战术事件、脚本推演等技能。 |
| 仿真引擎 | 前端 TypeScript 游戏模型与 `gym/blade` Python/Gym 环境共同支撑想定推演。 |

## 技术栈

| 层级 | 主要技术 |
| --- | --- |
| 前端 | React 18、Vite 6、TypeScript、Cesium、MUI、i18next、Vitest |
| 后端 | Python 3.12、FastAPI、Uvicorn、Pydantic、Gymnasium |
| AI/指挥 | AICC command bridge、AICC runtime skill registry |
| 部署 | Docker Compose、前端端口 `3000`、后端端口 `8000` |

## 快速启动

### Docker 一键启动

确保已安装 Docker Desktop，然后在仓库根目录执行：

```powershell
docker compose up --build
```

启动后访问：

| 服务 | 地址 |
| --- | --- |
| 前端平台 | `http://localhost:3000/` |
| AI 后端健康检查 | `http://localhost:8000/health` |

停止服务：

```powershell
docker compose down
```

### 本地开发启动

1. 启动 AI 后端：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\server\start-ai-server.ps1
```

默认端口为 `8000`。如需停止：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\server\stop-ai-server.ps1
```

2. 启动前端：

```powershell
cd client
npm ci
Copy-Item .env.example .env.local
npm run dev
```

前端默认运行在 `http://localhost:3000/`。如果 AI 后端端口调整，请同步修改 `client/.env.local` 中的 `VITE_AI_SERVER_URL`。

## 环境变量

前端环境变量参考 `client/.env.example`：

| 变量 | 默认/示例 | 说明 |
| --- | --- | --- |
| `VITE_ENV` | `standalone` | 前端运行模式。 |
| `VITE_AI_SERVER_URL` | `http://127.0.0.1:8000` | AI/FastAPI 后端地址，AI 面板会调用这个地址。 |
| `VITE_API_SERVER_URL` | `http://localhost:8080` | 原平台 API 地址保留项，当前 AI 后端不使用该端口。 |
| `VITE_CESIUM_ION_TOKEN` | 空 | Cesium Ion token，可选；当前内置底图无需 token。 |
| `VITE_AUTH0_*` | `secret` 示例 | Auth0 配置，仅在需要登录集成时填写真实值。 |

Docker Compose 会为前端设置：

```yaml
VITE_ENV: standalone
VITE_AI_SERVER_URL: http://localhost:8000
```

## 后端 API

FastAPI 后端默认监听 `8000`：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 健康检查，正常返回 `{"status":"ok"}`。 |
| `GET` | `/api/ai/skills` | 返回后端已注册的 AI/仿真技能列表。 |
| `POST` | `/api/ai/command` | 接收自然语言指令和上下文，执行技能并返回场景结果。 |
| `POST` | `/api/ai/model/check` | 检查模型服务连通性和模型配置。 |

## 常用命令

| 位置 | 命令 | 用途 |
| --- | --- | --- |
| 根目录 | `docker compose up --build` | 构建并启动前后端。 |
| 根目录 | `docker compose down` | 停止 Docker 服务。 |
| 根目录 | `.\server\start-ai-server.ps1` | 使用仓库内 Python 运行 AI 后端。 |
| 根目录 | `.\server\stop-ai-server.ps1` | 停止脚本启动的 AI 后端。 |
| `client` | `npm run dev` | 启动前端开发服务，端口 `3000`。 |
| `client` | `npm run build` | TypeScript 检查并构建生产包。 |
| `client` | `npm run lint` | 运行 ESLint。 |
| `client` | `npm run test` | 运行 Vitest 测试。 |
| `client` | `npm run preview` | 预览构建产物。 |

## 目录结构

```text
.
├─ client/                  # React + Vite 前端
│  ├─ src/game/             # TypeScript 想定/仿真模型
│  ├─ src/gui/              # 地图、工具栏、AI 面板等界面
│  ├─ src/i18n/             # 中文化与实体名称本地化
│  ├─ src/scenarios/        # 默认想定 JSON
│  └─ src/styles/           # 样式文件
├─ server/                  # FastAPI AI 后端
│  ├─ app/ai/               # AI bridge、skill registry、模型检查
│  ├─ app/api/              # HTTP API 路由
│  └─ app/aicc_runtime/       # AICC runtime 适配层（内部兼容路径）
├─ gym/                     # Python/Gym 仿真环境
├─ docs/                    # 项目文档
├─ docker-compose.yml       # 本地容器编排
└─ README.md
```

## 开发注意事项

- 平台主入口是 `http://localhost:3000/`，不需要额外的 `?map=ol` 参数。
- 当前主地图由 `CesiumScenarioMap` 承载，底图默认使用中文矢量图层。
- Cesium 在 React 严格模式下可能触发 WebGL 双初始化问题，当前前端入口保留了非 StrictMode 集成方式。
- Windows + Docker bind mount 下文件监听可能不稳定，Vite 配置已开启 polling 以保证 HMR。
- README 只记录当前仓库已存在的能力；新增认证、项目管理、数据库迁移等能力前，请以代码和接口为准再补文档。

## 许可证

本项目沿用仓库根目录 `LICENSE`，许可证为 Apache License 2.0。
