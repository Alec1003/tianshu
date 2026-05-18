"""Idempotent seeding of built-in scenario templates.

We mirror the three JSON files shipped under ``client/src/scenarios/`` into
the DB on startup so the frontend "templates" tab always shows them, even
on a fresh DB. Each template uses a stable id (``tpl-<slug>``) so re-seeding
upserts the row instead of creating duplicates.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_maker
from app.scenarios.models import Scenario

logger = logging.getLogger(__name__)


# Resolution order (first existing wins). Both prod (Docker) and local dev
# layouts are covered.
_CANDIDATE_DIRS = [
    Path("/app/client/src/scenarios"),                       # docker image
    Path(__file__).resolve().parents[3] / "client" / "src" / "scenarios",  # repo
]


# (file_stem, display_name, description)
_TEMPLATES: tuple[tuple[str, str, str], ...] = (
    ("SCS", "SCS 默认推演", "南海方向预设推演。包含中美双方典型机型、舰船与防空设施。"),
    (
        "default_scenario",
        "标准训练想定",
        "默认训练想定，覆盖飞机、舰船、防空与机场基础部署，适合新手熟悉操作。",
    ),
    ("blank_scenario", "空白想定", "无任何单位的空白沙盒。适合从零自定义想定。"),
)


def _resolve_scenarios_dir() -> Path | None:
    for path in _CANDIDATE_DIRS:
        if path.is_dir():
            return path
    return None


async def _seed_one(
    session: AsyncSession, file_stem: str, name: str, description: str, base_dir: Path
) -> None:
    fp = base_dir / f"{file_stem}.json"
    if not fp.is_file():
        logger.warning("seed: template file missing: %s", fp)
        return
    template_id = f"tpl-{file_stem}"

    existing = await session.get(Scenario, template_id)
    raw = json.loads(fp.read_text(encoding="utf-8"))

    if existing is None:
        session.add(
            Scenario(
                id=template_id,
                name=name,
                description=description,
                data=raw,
                is_template=True,
                owner_id=None,
            )
        )
        logger.info("seed: inserted template %s", template_id)
    else:
        # Refresh content so README updates / fixes propagate to existing DBs.
        existing.name = name
        existing.description = description
        existing.data = raw
        existing.is_template = True
        existing.version += 1
        logger.info("seed: refreshed template %s", template_id)


async def seed_system_templates() -> None:
    base_dir = _resolve_scenarios_dir()
    if base_dir is None:
        logger.warning("seed: no scenarios dir found in candidates: %s", _CANDIDATE_DIRS)
        return
    async with async_session_maker() as session:
        for stem, name, desc in _TEMPLATES:
            await _seed_one(session, stem, name, desc, base_dir)
        await session.commit()


def template_specs() -> Iterable[tuple[str, str, str]]:
    """Exposed for tests / introspection."""
    return _TEMPLATES
