from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai.bridge import PanopticonOpenClawBridge
from app.api.ai import router as ai_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Panopticon OpenClaw Embedded Backend",
        version="0.1.0",
        description="Single-process FastAPI backend with embedded OpenClaw-style skill agent.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.bridge = PanopticonOpenClawBridge.from_env()
    app.include_router(ai_router)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()

