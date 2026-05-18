from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai.bridge import PanopticonOpenClawBridge
from app.api.ai import router as ai_router
from app.auth.router import router as auth_router
from app.db.session import create_db_and_tables
from app.scenarios.router import router as scenarios_router
from app.scenarios.seed import seed_system_templates

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: ensure DB schema + seed system templates.

    For S1+S2 we use ``Base.metadata.create_all`` as a dev-friendly shortcut.
    Once schema starts evolving we MUST flip to ``alembic upgrade head`` in
    the entrypoint to keep changes auditable.
    """
    await create_db_and_tables()
    try:
        await seed_system_templates()
    except Exception:
        # Seeding is best-effort; missing JSON files shouldn't take the API
        # down. We log so dev can spot the problem.
        logger.exception("seed_system_templates failed; continuing without templates")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="AICC Tactical Backend",
        version="0.2.0",
        description=(
            "FastAPI backend: AI skill bridge + user auth + scenario "
            "persistence (S1+S2)."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.bridge = PanopticonOpenClawBridge.from_env()
    # Order: existing AI routes first (kept untouched), then auth + scenarios.
    app.include_router(ai_router)
    app.include_router(auth_router)
    app.include_router(scenarios_router)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()

