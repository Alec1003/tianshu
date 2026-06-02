# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project overview

AICC is a tactical scenario / wargame platform: a React + Cesium frontend on port 3000 talks to a FastAPI backend on port 8000 that wraps a Python `gym/blade` simulation engine. Natural-language commands flow through an OpenClaw-style "AICC" bridge into a skill registry that mutates the live scenario. The same backend also exposes an MCP server (stdio + Streamable HTTP at `/api/mcp/`) so external LLMs (Codex Desktop, Cursor) drive the *same* runtime instance the browser is rendering.

## Common commands

Run from `client/` unless noted.

| Command | Purpose |
| --- | --- |
| `docker compose up --build` (repo root) | Build + run frontend (`:3000`) and backend (`:8000`). |
| `docker compose up --build -d client` (repo root) | Rebuild the Nginx-served frontend bundle after client source/UI changes, then restart the client container. |
| `.\server\start-ai-server.ps1` / `.\server\stop-ai-server.ps1` | Launch / kill backend via in-repo `.python312\python.exe`. PID + logs land under `server\.ai_server.*`. |
| `npm run dev` | Vite dev server on port 3000. Copy `.env.example` to `.env.local` first. |
| `npm run build` | TS check (`tsc -b`) + production Vite build. |
| `npm run lint` | ESLint. |
| `npm run test` | Vitest (single run); `npm run test:watch` for watch mode. |
| `npm run test src/path/to/file.test.ts` | Run a single Vitest file. Also: `npm run test:game`, `test:units`, `test:utils`. |
| `npm run preview` | Preview the production build. |
| `npm run electron:dev` (repo root) | Build the client and run the Electron shell against bundled local resources. |
| `npm run electron:pack` (repo root) | Build the unpacked Windows Electron app under `dist-electron/win-unpacked`. |
| `npm run electron:dist` (repo root) | Build the Windows NSIS installer. Requires `.python312` and `client/dist`. |
| `npm run electron:publish` (repo root) | Build + publish installer/update metadata to GitHub Releases via electron-builder. Requires `GH_TOKEN`. |
| `& "...\.python312\python.exe" -m pytest tests/ -v` (from `server/`) | Backend pytest. `asyncio_mode = auto`. |
| `& "...\.python312\python.exe" -m pytest tests/test_mcp_runtime.py::test_x -v` | Single backend test. |
| `& "...\.python312\python.exe" -m app.mcp` (from `server/`) | Run MCP server in stdio mode. Requires `AICC_MCP_TOKEN` (JWT) or `AICC_MCP_USER_ID` (dev). |

The Python interpreter lives at `.python312\python.exe` in the repo root — `start-ai-server.ps1` and the MCP scripts assume this exact path.

## Architecture

### Backend (`server/app/`)

- `main.py` builds the FastAPI app. The `lifespan` is load-bearing: it (1) creates DB + seeds system templates, (2) constructs `AICCOpenClawBridge` which owns the singleton `AICCRuntime`, (3) calls `set_shared_runtime(bridge.runtime)` *before* opening the MCP session manager, then (4) wraps `yield` inside `async with mcp.session_manager.run()`. The MCP HTTP transport is mounted at `/api/mcp` behind `BearerAuthASGI`.
- `ai/bridge.py` — `AICCOpenClawBridge` is the composition root: runtime + skill registry + agent + MCP client skeleton + SDK adapter. `from_env()` is the only constructor callers use.
- `ai/agent.py` — `AICCCommanderAgent` parses natural-language commands (regex-driven; see `UUID_RE`, `NUMBER_RE`, etc.) and dispatches to skills. Hooks `_plan_with_sdk()` for future OpenClaw SDK integration.
- `ai/skill_registry.py` — Concrete skill implementations bound to the runtime.
- `aicc_runtime/runtime.py` — `AICCRuntime` wraps `gym/blade`'s `Game`/`Scenario`. It mutates `sys.path` at import time to put `AICC_GYM_DIR` or `<resource-root>/gym` on the path, then imports `blade.*` modules. Holds an `RLock` and a script-step cursor for staged playback.
- `platform/paths.py` — packaging-aware path resolver. Source/Docker default to the repository-shaped root; Electron/exe launchers should set `AICC_RESOURCE_DIR` to bundled read-only resources and `AICC_USER_DATA_DIR` / `AICC_SKILLS_DIR` to writable app data.
- `api/ai.py` — three endpoints:
  - `POST /api/ai/command` — main NL command surface; returns execution summary + freshly exported scenario JSON.
  - `GET /api/ai/runtime/scenario` — read-only snapshot of the live runtime (the front-end polls this to see MCP-side mutations).
  - `POST /api/ai/model/check` — connectivity check for an LLM provider.
- `auth/` — fastapi-users 14 + SQLAlchemy async. JWT-based, secret from `AICC_JWT_SECRET`. First registered user auto-becomes superuser (configurable in `config.py`).
- `scenarios/` — CRUD for persistent scenarios + AAR records. Permission model: own + system templates readable; only owners can mutate; system templates are read-only.
- `mcp/` — FastMCP server. `server.py` registers all tools (27 tools + 2 resources + 1 template). Two transports:
  - **stdio**: `python -m app.mcp`. Auth via `AICC_MCP_TOKEN` (JWT) or `AICC_MCP_USER_ID` (dev shortcut).
  - **Streamable HTTP**: mounted at `/api/mcp/` with per-request `Authorization: Bearer <jwt>`. `AICC_MCP_HTTP_DEV_USER_ID` skips auth for local dev (warns in logs).
  - Tools split into two groups: **DB scenarios** (12 tools — static persistence on the `Scenario` table) and **runtime** (15 tools — live in-memory `AICCRuntime`). The two groups do **not** auto-sync; use `runtime_load_scenario_from_db` and `runtime_save_to_db` to bridge.
- `db/session.py` — async SQLAlchemy session. SQLite at `./data/aicc.db` by default; docker-compose mounts a volume so data survives rebuilds.

### Shared-runtime invariant

The MCP server and `/api/ai/command` operate on the **same** `AICCRuntime` instance (`app.state.bridge.runtime`). External LLM mutations through MCP are immediately visible at `GET /api/ai/runtime/scenario`. The browser, however, has its own client-side `Game` (`client/src/game/Game.ts`) and does **not** auto-poll — frontend must explicitly call the snapshot endpoint and `game.loadScenario(json)` to pick up MCP-side changes.

### Simulation engine — two copies

`client/src/game/` (TypeScript) and `gym/blade/` (Python) are *parallel implementations* of the same simulation engine: `Game`, `Scenario`, `Side`, `units/*`, `engine/weaponEngagement`. The TypeScript engine runs in the browser for fast UI playback; the Python engine runs in the backend so MCP / `/api/ai/command` can mutate authoritative state. Default scenario for both is `client/src/scenarios/SCS.json`. When changing simulation semantics, both copies usually need the change — they are not auto-synchronized.

### Frontend (`client/src/`)

- React 18 + Vite 6 + TypeScript. Routing in `App.tsx`: `/scenarios` (list), `/play/:scenarioId` (Cesium scenario view), `/login` + `/register` (same `LoginPage` component switching on pathname). Both protected routes are wrapped in `RequireAuth`.
- `main.tsx` provider order: `BrowserRouter` → `AuthProvider` → `AppProvider` → `App`. `BrowserRouter` must be outermost because `AuthProvider` uses `useNavigate` for redirect-after-logout.
- `api/client.ts` — single fetch wrapper. Reads JWT from `localStorage["aicc.auth.token"]`, attaches as Bearer, picks base URL from `VITE_AI_SERVER_URL` (dev) or relative (prod, where nginx proxies `/api/*`). On 401 it clears the token and dispatches `aicc:auth:logout` for `AuthProvider` to react.
- `features/auth/`, `features/scenarios/`, `features/tactical/` — top-level pages and panels (login, scenario list, play page, AI sidebar, AAR dialog, simulation inspector).
- `gui/` — Cesium map, toolbars, mission UI, popups. Cesium is plugged in via `vite-plugin-cesium`.
- `game/` — client-side simulation engine (TypeScript twin of `gym/blade`).

### Frontend ↔ backend URL plumbing

- Dev: Vite serves on `:3000`, frontend reads `VITE_AI_SERVER_URL=http://127.0.0.1:8000` from `.env.local`, and hits the backend cross-origin. Backend CORS is explicit and comes from `AICC_CORS_ORIGINS`; wildcard origins are rejected.
- Prod (docker-compose): `VITE_AI_SERVER_URL=""` in the build args; nginx in the client container reverse-proxies `/api/*` to the server.

### Electron desktop package

- Root `package.json` owns desktop packaging. `electron-builder` publishes to GitHub repo `Alec1003/tianshu`; `electron-updater` checks that GitHub Releases feed in packaged builds.
- `electron/main.cjs` starts the bundled FastAPI backend on `127.0.0.1:<random>` and a local Node static server on `127.0.0.1:<random>`. The static server serves `client/dist`, proxies `/api/*` to FastAPI, and loads `/scenarios`, so React keeps using the same relative API paths as Docker production.
- Electron windows should keep `contextIsolation: true`, `nodeIntegration: false`, and `sandbox: true`; expose desktop capabilities only through named preload APIs, and keep external navigation default-deny with an http/https allowlist.
- Packaged read-only resources are copied via `extraResources`: `server/`, `gym/`, `client/dist/`, `client/src/scenarios/`, and `.python312/`.
- Mutable desktop data must stay outside `app.asar`: Electron sets `AICC_USER_DATA_DIR`, `AICC_SKILLS_DIR`, SQLite `AICC_DATABASE_URL`, generated JWT/model secrets, and backend logs under `app.getPath("userData")`.
- Release/update flow: bump root `package.json` version, commit, tag `vX.Y.Z`, then push the branch and tag to `tianshu`. The `.github/workflows/electron-release.yml` workflow publishes the installer and `latest.yml` update metadata.
- Current unsigned Windows CI builds deliberately set `win.signExts: ["!.exe"]` so NSIS installer/uninstaller signing is skipped. Remove that exclusion only after a real Windows code-signing certificate is configured.
- Do not bind the desktop backend to `0.0.0.0`; it is an internal loopback service.

## Environment variables

Backend (prefix `AICC_`, see `server/app/config.py`):

- `AICC_DATABASE_URL` — async SQLAlchemy DSN. Defaults to SQLite under `./data/`. Compose mounts a named volume here.
- `AICC_SKILLS_DIR` — folder-backed custom AI skills store. Defaults to `./data/skills`; Docker mounts this under the server data volume. For exe packaging, point this at the app's writable skills folder and do not reintroduce frontend `localStorage` as the durable skills source.
- `AICC_RESOURCE_DIR` — read-only bundled resource root for packaged runs. Defaults to the source/Docker repo-shaped root. Electron should point this at `extraResources`.
- `AICC_USER_DATA_DIR` — writable desktop/server data root. Electron should point this at `app.getPath("userData")`; keep DB, skills, logs, and mutable app data outside `app.asar`.
- `AICC_GYM_DIR` / `AICC_SCENARIOS_DIR` / `AICC_UNIT_ASSETS_FILE` — optional resource overrides when the packaged layout does not mirror the source tree.
- `AICC_JWT_SECRET` — JWT signing secret. **Must be overridden in production.**
- `AICC_MCP_TOKEN` / `AICC_MCP_USER_ID` — stdio MCP auth.
- `AICC_MCP_HTTP_DEV_USER_ID` — local-only HTTP MCP auth bypass.
- `AICC_MCP_RUNTIME_SCENARIO` — override the default `SCS.json` boot scenario. Relative paths resolve from `AICC_RESOURCE_DIR`.

Frontend (see `client/.env.example`): `VITE_AI_SERVER_URL`, `VITE_API_SERVER_URL`, `VITE_CESIUM_ION_TOKEN`, `VITE_AUTH0_*`, `VITE_ENV`.

## Development notes

- Platform entry point is `http://localhost:3000/` — no `?map=ol` query param needed; default map is `CesiumScenarioMap`.
- Cesium can double-initialize under React `StrictMode` (WebGL); the current entry deliberately omits StrictMode.
- On Windows + Docker bind mounts, file watching can be flaky; Vite is configured with polling for HMR.
- When the user is viewing the Docker-served frontend, client source/UI changes are not visible after `docker compose restart client` alone. The client container serves static Nginx assets built into the image, so run `npm.cmd run build` from `client/` when useful, then `docker compose up --build -d client`, and verify `docker compose ps`, `http://localhost:3000/`, and `http://localhost:8000/health`.
- `runtime_step(steps=N)` is capped at 7200 (= 2 simulation hours) per call. Loop for longer runs.
- Single-process / single-runtime: each `python -m app.mcp` invocation owns its own runtime; HTTP MCP shares the FastAPI bridge runtime. There is no multi-tenant runtime registry yet.
- Coding style is enforced by ESLint + Prettier (client) and pytest's `filterwarnings = ignore::DeprecationWarning` (server, to silence fastapi-users 14 + SQLAlchemy 2 noise). Match underscore-prefix conventions for private members and follow the existing camelCase / snake_case split (TS vs Python).
- README ground rule (from `README.md`): only document capabilities that exist in code today — verify against source before adding feature docs.
