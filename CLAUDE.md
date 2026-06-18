# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

TianShu is a tactical scenario / wargame platform: a React + Cesium frontend on port 3002 talks to a FastAPI backend on port 8000 that wraps a Python `gym/blade` simulation engine. Natural-language commands flow through an OpenClaw-style "TianShu" bridge into a skill registry that mutates the live scenario. The same backend also exposes an MCP server (stdio + Streamable HTTP at `/api/mcp/`) so external LLMs (Claude Desktop, Cursor) drive the *same* runtime instance the browser is rendering.

## Common commands

Run from `client/` unless noted.

| Command | Purpose |
| --- | --- |
| `docker compose up --build` (repo root) | Build + run frontend (`:3002`) and backend (`:8000`). |
| `.\server\start-ai-server.ps1` / `.\server\stop-ai-server.ps1` | Launch / kill backend via in-repo `.python312\python.exe`. PID + logs land under `server\.ai_server.*`. |
| `npm run dev` | Vite dev server on port 3002. Copy `.env.example` to `.env.local` first. |
| `npm run build` | TS check (`tsc -b`) + production Vite build. |
| `npm run lint` | ESLint. |
| `npm run test` | Vitest (single run); `npm run test:watch` for watch mode. |
| `npm run test src/path/to/file.test.ts` | Run a single Vitest file. Also: `npm run test:game`, `test:units`, `test:utils`. |
| `npm run preview` | Preview the production build. |
| `& "...\.python312\python.exe" -m pytest tests/ -v` (from `server/`) | Backend pytest. `asyncio_mode = auto`. |
| `& "...\.python312\python.exe" -m pytest tests/test_mcp_runtime.py::test_x -v` | Single backend test. |
| `& "...\.python312\python.exe" -m app.mcp` (from `server/`) | Run MCP server in stdio mode. Requires `TIANSHU_MCP_TOKEN` (JWT) or `TIANSHU_MCP_USER_ID` (dev). |

The Python interpreter lives at `.python312\python.exe` in the repo root — `start-ai-server.ps1` and the MCP scripts assume this exact path.

## Architecture

### Backend (`server/app/`)

- `main.py` builds the FastAPI app. The `lifespan` is load-bearing: it (1) creates DB + seeds system templates, (2) constructs `TianShuOpenClawBridge` which owns the singleton `TianShuRuntime`, (3) calls `set_shared_runtime(bridge.runtime)` *before* opening the MCP session manager, then (4) wraps `yield` inside `async with mcp.session_manager.run()`. The MCP HTTP transport is mounted at `/api/mcp` behind `BearerAuthASGI`.
- `ai/bridge.py` — `TianShuOpenClawBridge` is the composition root: runtime + skill registry + agent + MCP client skeleton + SDK adapter. `from_env()` is the only constructor callers use.
- `ai/agent.py` — `TianShuCommanderAgent` parses natural-language commands (regex-driven; see `UUID_RE`, `NUMBER_RE`, etc.) and dispatches to skills. Hooks `_plan_with_sdk()` for future OpenClaw SDK integration.
- `ai/skill_registry.py` — Concrete skill implementations bound to the runtime.
- `tianshu/runtime.py` — `TianShuRuntime` wraps `gym/blade`'s `Game`/`Scenario`. It mutates `sys.path` at import time to put `<repo>/gym` on the path, then imports `blade.*` modules. Holds an `RLock` and a script-step cursor for staged playback. `ROOT_DIR` is `repo` root computed via `parents[3]`.
- `api/ai.py` — three endpoints:
  - `POST /api/ai/command` — main NL command surface; returns execution summary + freshly exported scenario JSON.
  - `GET /api/ai/runtime/scenario` — read-only snapshot of the live runtime (the front-end polls this to see MCP-side mutations).
  - `POST /api/ai/model/check` — connectivity check for an LLM provider.
- `auth/` — fastapi-users 14 + SQLAlchemy async. JWT-based, secret from `TIANSHU_JWT_SECRET`. First registered user auto-becomes superuser (configurable in `config.py`).
- `scenarios/` — CRUD for persistent scenarios + AAR records. Permission model: own + system templates readable; only owners can mutate; system templates are read-only.
- `mcp/` — FastMCP server. `server.py` registers all tools (27 tools + 2 resources + 1 template). Two transports:
  - **stdio**: `python -m app.mcp`. Auth via `TIANSHU_MCP_TOKEN` (JWT) or `TIANSHU_MCP_USER_ID` (dev shortcut).
  - **Streamable HTTP**: mounted at `/api/mcp/` with per-request `Authorization: Bearer <jwt>`. `TIANSHU_MCP_HTTP_DEV_USER_ID` skips auth for local dev (warns in logs).
  - Tools split into two groups: **DB scenarios** (12 tools — static persistence on the `Scenario` table) and **runtime** (15 tools — live in-memory `TianShuRuntime`). The two groups do **not** auto-sync; use `runtime_load_scenario_from_db` and `runtime_save_to_db` to bridge.
- `db/session.py` — async SQLAlchemy session. SQLite at `./data/tianshu.db` by default; docker-compose mounts a volume so data survives rebuilds.

### Shared-runtime invariant

The MCP server and `/api/ai/command` operate on the **same** `TianShuRuntime` instance (`app.state.bridge.runtime`). External LLM mutations through MCP are immediately visible at `GET /api/ai/runtime/scenario`. The browser, however, has its own client-side `Game` (`client/src/game/Game.ts`) and does **not** auto-poll — frontend must explicitly call the snapshot endpoint and `game.loadScenario(json)` to pick up MCP-side changes.

### Simulation engine — two copies

`client/src/game/` (TypeScript) and `gym/blade/` (Python) are *parallel implementations* of the same simulation engine: `Game`, `Scenario`, `Side`, `units/*`, `engine/weaponEngagement`. The TypeScript engine runs in the browser for fast UI playback; the Python engine runs in the backend so MCP / `/api/ai/command` can mutate authoritative state. Default scenario for both is `client/src/scenarios/SCS.json`. When changing simulation semantics, both copies usually need the change — they are not auto-synchronized.

### Frontend (`client/src/`)

- React 18 + Vite 6 + TypeScript. Routing in `App.tsx`: `/scenarios` (list), `/play/:scenarioId` (Cesium scenario view), `/login` + `/register` (same `LoginPage` component switching on pathname). Both protected routes are wrapped in `RequireAuth`.
- `main.tsx` provider order: `BrowserRouter` → `AuthProvider` → `AppProvider` → `App`. `BrowserRouter` must be outermost because `AuthProvider` uses `useNavigate` for redirect-after-logout.
- `api/client.ts` — single fetch wrapper. Reads JWT from `localStorage["tianshu.auth.token"]`, attaches as Bearer, picks base URL from `VITE_AI_SERVER_URL` (dev) or relative (prod, where nginx proxies `/api/*`). On 401 it clears the token and dispatches `tianshu:auth:logout` for `AuthProvider` to react.
- `features/auth/`, `features/scenarios/`, `features/tactical/` — top-level pages and panels (login, scenario list, play page, AI sidebar, AAR dialog, simulation inspector).
- `gui/` — Cesium map, toolbars, mission UI, popups. Cesium is plugged in via `vite-plugin-cesium`.
- `game/` — client-side simulation engine (TypeScript twin of `gym/blade`).

### Frontend ↔ backend URL plumbing

- Dev: Vite serves on `:3002`, frontend reads `VITE_AI_SERVER_URL=http://127.0.0.1:8000` from `.env.local`, hits the backend cross-origin (backend has `allow_origins=["*"]`).
- Prod (docker-compose): `VITE_AI_SERVER_URL=""` in the build args; nginx in the client container reverse-proxies `/api/*` to the server.

## Environment variables

Backend (prefix `TIANSHU_`, see `server/app/config.py`):

- `TIANSHU_DATABASE_URL` — async SQLAlchemy DSN. Defaults to SQLite under `./data/`. Compose mounts a named volume here.
- `TIANSHU_JWT_SECRET` — JWT signing secret. **Must be overridden in production.**
- `TIANSHU_MCP_TOKEN` / `TIANSHU_MCP_USER_ID` — stdio MCP auth.
- `TIANSHU_MCP_HTTP_DEV_USER_ID` — local-only HTTP MCP auth bypass.
- `TIANSHU_MCP_RUNTIME_SCENARIO` — override the default `SCS.json` boot scenario.

Frontend (see `client/.env.example`): `VITE_AI_SERVER_URL`, `VITE_API_SERVER_URL`, `VITE_CESIUM_ION_TOKEN`, `VITE_AUTH0_*`, `VITE_ENV`.

## Development notes

- Platform entry point is `http://localhost:3002/` — no `?map=ol` query param needed; default map is `CesiumScenarioMap`.
- Cesium can double-initialize under React `StrictMode` (WebGL); the current entry deliberately omits StrictMode.
- On Windows + Docker bind mounts, file watching can be flaky; Vite is configured with polling for HMR.
- `runtime_step(steps=N)` is capped at 7200 (= 2 simulation hours) per call. Loop for longer runs.
- Single-process / single-runtime: each `python -m app.mcp` invocation owns its own runtime; HTTP MCP shares the FastAPI bridge runtime. There is no multi-tenant runtime registry yet.
- Coding style is enforced by ESLint + Prettier (client) and pytest's `filterwarnings = ignore::DeprecationWarning` (server, to silence fastapi-users 14 + SQLAlchemy 2 noise). Match underscore-prefix conventions for private members and follow the existing camelCase / snake_case split (TS vs Python).
- README ground rule (from `README.md`): only document capabilities that exist in code today — verify against source before adding feature docs.
