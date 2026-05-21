from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.ai.model_checker import check_model_connectivity
from app.ai.models import (
    AICommandRequest,
    AICommandResponse,
    ModelCheckRequest,
    ModelCheckResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/command", response_model=AICommandResponse)
async def command(request: Request, payload: AICommandRequest) -> AICommandResponse:
    bridge = request.app.state.bridge
    execution = await bridge.process_command_async(payload.command, payload.context)
    scenario = bridge.exported_scenario()

    if execution.status == "ok":
        message = "Command executed successfully."
    elif execution.status == "partial":
        message = "Command partially executed. Check skill call results."
    else:
        message = execution.error or "Command execution failed."

    return AICommandResponse(
        status=execution.status,
        message=message,
        execution=execution,
        scenario=scenario,
    )


@router.get("/runtime/scenario")
def runtime_scenario(request: Request) -> dict:
    """Export the current in-memory runtime scenario as JSON.

    This is the **read-only** counterpart to the MCP ``runtime_*`` tools:
    the front-end (or any HTTP client) can poll this endpoint to grab the
    latest snapshot of the shared ``AICCRuntime`` that MCP / AI
    commands are mutating. The returned shape is identical to the
    ``scenario`` field in ``POST /api/ai/command`` responses, so
    ``game.loadScenario(JSON.stringify(response))`` works on the client.

    No auth required (aligns with ``/api/ai/command`` which is also open);
    add ``Depends(current_active_user)`` when multi-tenant auth is wired.
    """
    bridge = request.app.state.bridge
    return bridge.exported_scenario()


@router.get("/skills")
def list_skills(request: Request) -> dict:
    bridge = request.app.state.bridge
    return {"skills": [definition.model_dump() for definition in bridge.skill_registry.definitions()]}


@router.post("/model/check", response_model=ModelCheckResponse)
def check_model(payload: ModelCheckRequest) -> ModelCheckResponse:
    return check_model_connectivity(payload)


# ─── S4: Streaming Chat (Pydantic AI) ─────────────────────────────────────────


def _read_model_override_from_headers(
    request: Request,
) -> tuple[str, str, str, str]:
    """Pull per-request model override fields from custom headers.

    The AI sidebar sends ``X-AICC-Model-{Provider,Name,Api-Key,Base-Url}``
    whenever the user has filled in a model config. Empty / missing
    headers fall back to "" so the caller can decide between override and
    the env-configured global agent.
    """
    return (
        (request.headers.get("x-aicc-model-provider") or "").strip(),
        (request.headers.get("x-aicc-model-name") or "").strip(),
        (request.headers.get("x-aicc-model-api-key") or "").strip(),
        (request.headers.get("x-aicc-model-base-url") or "").strip(),
    )


def _read_chat_mode_from_headers(request: Request) -> str:
    mode = (request.headers.get("x-aicc-chat-mode") or "command").strip().lower()
    return "ask" if mode == "ask" else "command"


@router.post("/chat")
async def chat(request: Request) -> StreamingResponse:
    """Streaming chat endpoint powered by pydantic-ai.

    Accepts Vercel AI SDK compatible request body (messages array).
    Returns SSE stream of text deltas + tool-invocation chunks that any
    AI-SDK–compatible frontend (``useChat`` from ``@ai-sdk/react``) can
    consume out of the box.

    Model override: when the request carries
    ``X-AICC-Model-{Provider,Name,Api-Key,Base-Url}`` headers (i.e. the
    user filled in the sidebar Settings panel) we build a one-off agent
    so the user-supplied credentials/provider actually drive the stream.
    Otherwise we fall back to the env-configured ``bridge.pydantic_agent``.

    Falls back to a non-streaming JSON error if no LLM is configured at all.
    """
    from pydantic_ai.ui.vercel_ai import VercelAIAdapter  # noqa: PLC0415

    from app.ai.pydantic_agent import AgentDeps, build_agent  # noqa: PLC0415

    bridge = request.app.state.bridge
    chat_mode = _read_chat_mode_from_headers(request)

    # Per-request model override via headers (set by AI sidebar useChat).
    provider, model_name, api_key, base_url = _read_model_override_from_headers(request)
    logger.info(
        "chat: headers received provider=%r model=%r api_key=%s base_url=%r",
        provider,
        model_name,
        ("***" + api_key[-4:]) if len(api_key) > 4 else ("set" if api_key else "EMPTY"),
        base_url,
    )
    per_request_agent = None
    if provider and model_name and api_key:
        model_id = f"{provider}:{model_name}"
        try:
            per_request_agent = build_agent(
                model_id=model_id,
                api_key=api_key,
                base_url=base_url,
                enable_tools=chat_mode == "command",
            )
            logger.info("chat: per-request agent built (model=%s)", model_id)
        except Exception as exc:  # pragma: no cover - depends on SDK install
            logger.warning(
                "chat: per-request agent build failed (%s): %s", model_id, exc
            )

    fallback_agent = (
        bridge.pydantic_agent
        if chat_mode == "command"
        else getattr(bridge, "pydantic_ask_agent", None)
    )
    agent = per_request_agent or fallback_agent
    if agent is None:
        return StreamingResponse(
            iter(
                [
                    json.dumps(
                        {
                            "error": (
                                "No LLM configured. Either set AICC_LLM_MODEL + "
                                "AICC_LLM_API_KEY on the server, or fill the "
                                "model section in the AI sidebar (Settings)."
                            )
                        }
                    )
                ]
            ),
            status_code=503,
            media_type="application/json",
        )

    deps = AgentDeps(registry=bridge.skill_registry, chat_mode=chat_mode)
    return await VercelAIAdapter.dispatch_request(
        request,
        agent=agent,
        deps=deps,
    )
