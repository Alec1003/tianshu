"""Idempotent seeding of built-in scenario templates.

We mirror curated JSON files shipped under ``client/src/scenarios/`` into the
DB on startup so the frontend "templates" tab always shows them, even on a
fresh DB. Each template uses a stable id (``tpl-<slug>``) so re-seeding upserts
the row instead of creating duplicates.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_maker
from app.scenarios.models import Scenario

logger = logging.getLogger(__name__)


# Resolution order (first existing wins). Both prod (Docker) and local dev
# layouts are covered.
_CANDIDATE_DIRS = [
    Path("/app/client/src/scenarios"),  # docker image
    Path(__file__).resolve().parents[3] / "client" / "src" / "scenarios",  # repo
]


# Template ids retired from the template center. The JSON files still exist
# because the runtime and "new blank project" flows use them as local presets.
_RETIRED_TEMPLATE_IDS: tuple[str, ...] = (
    "tpl-SCS",
    "tpl-default_scenario",
    "tpl-blank_scenario",
)


# (file_stem, display_name, description)
_TEMPLATES: tuple[tuple[str, str, str], ...] = (
    (
        "midway_1942",
        "中途岛海战（1942）",
        "基于 1942 年 6 月中途岛海战的航母航空兵对抗模板，适合训练侦察、舰载航空兵出击与关键航母目标防护。",
    ),
    (
        "overlord_1944",
        "诺曼底登陆（1944）",
        "基于 1944 年 6 月 6 日盟军诺曼底登陆的联合登陆支援模板，适合训练空地协同、滩头火力压制与登陆节点保障。",
    ),
    (
        "desert_storm_1991",
        "沙漠风暴：诺曼底特遣队（1991）",
        "基于 1991 年 1 月沙漠风暴开端的诺曼底特遣队行动模板，适合训练防空走廊开辟、低空突防与电子支援协同。",
    ),
)


def _resolve_scenarios_dir() -> Path | None:
    for path in _CANDIDATE_DIRS:
        if path.is_dir():
            return path
    return None


async def _retire_legacy_templates(session: AsyncSession) -> None:
    if not _RETIRED_TEMPLATE_IDS:
        return
    result = await session.execute(
        delete(Scenario).where(
            Scenario.is_template == True,  # noqa: E712
            Scenario.id.in_(_RETIRED_TEMPLATE_IDS),
        )
    )
    retired = result.rowcount or 0
    if retired:
        logger.info("seed: retired %s legacy templates", retired)


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
        # Refresh content so scenario JSON updates/fixes propagate to existing DBs.
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
        await _retire_legacy_templates(session)
        for stem, name, desc in _TEMPLATES:
            await _seed_one(session, stem, name, desc, base_dir)
        await session.commit()


def template_specs() -> Iterable[tuple[str, str, str]]:
    """Exposed for tests / introspection."""
    return _TEMPLATES
