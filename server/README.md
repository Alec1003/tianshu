# Panopticon OpenClaw Embedded Backend

## Design Summary
- Single FastAPI process.
- No extra OpenClaw gateway process and no extra OpenClaw-only port.
- Panopticon native simulation functions are wrapped as Skills and called in-process.
- MCP support is scaffold-only (connection/invocation framework, no business implementation).

## Directory
- `app/main.py`: FastAPI app entry.
- `app/api/ai.py`: `/api/ai/command` API.
- `app/ai/agent.py`: Panopticon Commander agent (NL parsing + skill dispatch).
- `app/ai/openclaw_sdk_adapter.py`: Embedded OpenClaw SDK adapter seam (in-process).
- `app/ai/skill_registry.py`: Skill definitions and registration.
- `app/ai/mcp_client.py`: MCP client skeleton (extension area).
- `app/ai/bridge.py`: Unified OpenClaw bridge module.
- `app/panopticon/runtime.py`: Native engine runtime adapter (calls `gym/blade` in-process).

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
  - `app/ai/bridge.py::_register_default_mcp_skeleton()`
