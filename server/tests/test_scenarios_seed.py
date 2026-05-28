from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.scenarios import seed as scenario_seed
from app.scenarios.models import Scenario


ROOT_DIR = Path(__file__).resolve().parents[2]


def test_template_specs_are_curated_historical_cases() -> None:
    stems = [stem for stem, _, _ in scenario_seed.template_specs()]

    assert stems == [
        "midway_1942",
        "overlord_1944",
        "desert_storm_1991",
    ]
    assert "SCS" not in stems
    assert "default_scenario" not in stems
    assert "blank_scenario" not in stems


def test_template_files_exist_and_have_basic_scenario_shape() -> None:
    scenario_dir = ROOT_DIR / "client" / "src" / "scenarios"
    minimum_counts = {
        "midway_1942": {
            "aircraft": 10,
            "ships": 8,
            "facilities": 3,
            "missions": 8,
        },
        "overlord_1944": {
            "aircraft": 10,
            "ships": 5,
            "facilities": 7,
            "missions": 8,
        },
        "desert_storm_1991": {
            "aircraft": 12,
            "facilities": 8,
            "airbases": 5,
            "missions": 10,
        },
    }

    for stem, name, description in scenario_seed.template_specs():
        data = json.loads((scenario_dir / f"{stem}.json").read_text(encoding="utf-8"))
        current = data["currentScenario"]
        expected = minimum_counts[stem]

        assert current["name"] == name
        assert description
        assert len(current["sides"]) >= 2
        assert current["relationships"]["hostiles"]
        assert current["doctrine"]
        assert "historicalCase" in current
        assert current["historicalCase"]["complexity"]
        for collection, minimum in expected.items():
            assert len(current[collection]) >= minimum


@pytest.mark.asyncio
async def test_retire_legacy_templates_only_removes_old_system_templates(db_session):
    db_session.add_all(
        [
            Scenario(
                id="tpl-SCS",
                name="Old SCS",
                description="old",
                data={},
                is_template=True,
                owner_id=None,
                status="draft",
            ),
            Scenario(
                id="tpl-default_scenario",
                name="Old Demo",
                description="old",
                data={},
                is_template=True,
                owner_id=None,
                status="draft",
            ),
            Scenario(
                id="tpl-blank_scenario",
                name="Old Blank",
                description="old",
                data={},
                is_template=True,
                owner_id=None,
                status="draft",
            ),
            Scenario(
                id="tpl-midway_1942",
                name="Midway",
                description="keep",
                data={},
                is_template=True,
                owner_id=None,
                status="draft",
            ),
        ]
    )
    await db_session.commit()

    await scenario_seed._retire_legacy_templates(db_session)
    await db_session.commit()

    rows = await db_session.execute(select(Scenario.id).order_by(Scenario.id))
    assert rows.scalars().all() == ["tpl-midway_1942"]
