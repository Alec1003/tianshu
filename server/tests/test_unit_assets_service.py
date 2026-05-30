from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.ai import model_endpoint_policy as endpoint_policy
from app.config import Settings
from app.unit_assets.errors import (
    UnitAssetConflictError,
    UnitAssetForbiddenError,
    UnitAssetInvalidError,
)
from app.unit_assets.generator import estimate_unit_asset, generate_unit_asset_payload
from app.unit_assets.models import UnitAsset
from app.unit_assets.schemas import UnitAssetImportRequest
from app.unit_assets import service as svc

pytestmark = pytest.mark.asyncio


AIRCRAFT = {
    "className": "Test Jet",
    "speed": 900,
    "maxFuel": 12000,
    "fuelRate": 3000,
    "range": 800,
    "dataSource": {
        "speedSrc": "Manual",
        "maxFuelSrc": "Manual",
        "fuelRateSrc": "Manual",
        "rangeSrc": "Manual",
    },
    "units": {
        "speedUnit": "kts",
        "maxFuelUnit": "kg",
        "fuelRateUnit": "kg/h",
        "rangeUnit": "nm",
    },
}


async def test_seed_default_unit_assets_loads_existing_unit_db(db_session):
    seeded = await svc.seed_default_unit_assets(db_session)
    rows = await db_session.execute(select(UnitAsset))
    assets = rows.scalars().all()

    assert seeded == 111
    assert len(assets) == 111
    assert any(a.type == "aircraft" and a.name == "KC-135R Stratotanker" for a in assets)
    growler = next(
        a for a in assets if a.type == "aircraft" and a.name == "EA-18G Growler"
    )
    assert growler.data["isElectronicWarfare"] is True
    assert growler.data["jammingRange"] > 0


async def test_create_lists_own_custom_asset(db_session, user):
    asset = await svc.create_unit_asset(
        db_session,
        user,
        asset_type="aircraft",
        data=AIRCRAFT,
    )

    rows = await svc.list_unit_assets(db_session, user, asset_type="aircraft")
    assert asset in rows
    assert asset.owner_id == user.id
    assert asset.is_system is False


async def test_create_rejects_duplicate_type_name(db_session, user):
    await svc.create_unit_asset(
        db_session,
        user,
        asset_type="aircraft",
        data=AIRCRAFT,
    )

    with pytest.raises(UnitAssetConflictError):
        await svc.create_unit_asset(
            db_session,
            user,
            asset_type="aircraft",
            data=AIRCRAFT,
        )


async def test_users_can_create_same_type_name_in_their_own_scope(
    db_session, user, other_user
):
    first = await svc.create_unit_asset(
        db_session,
        user,
        asset_type="aircraft",
        data=AIRCRAFT,
    )
    second = await svc.create_unit_asset(
        db_session,
        other_user,
        asset_type="aircraft",
        data=AIRCRAFT,
    )

    assert first.id != second.id
    assert first.owner_id == user.id
    assert second.owner_id == other_user.id


async def test_user_can_create_custom_asset_with_system_name(db_session, user):
    await svc.seed_default_unit_assets(db_session)

    asset = await svc.create_unit_asset(
        db_session,
        user,
        asset_type="aircraft",
        data={**AIRCRAFT, "className": "KC-135R Stratotanker"},
    )

    assert asset.owner_id == user.id
    rows = await svc.list_unit_assets(db_session, user, asset_type="aircraft")
    matches = [row for row in rows if row.name == "KC-135R Stratotanker"]
    assert len(matches) == 2
    assert {row.is_system for row in matches} == {False, True}


async def test_create_validates_required_fields(db_session, user):
    with pytest.raises(UnitAssetInvalidError) as exc_info:
        await svc.create_unit_asset(
            db_session,
            user,
            asset_type="weapon",
            data={"className": "No Numbers"},
        )

    assert exc_info.value.details["field"] == "speed"


async def test_other_user_cannot_edit_custom_asset(db_session, user, other_user):
    asset = await svc.create_unit_asset(
        db_session,
        user,
        asset_type="aircraft",
        data=AIRCRAFT,
    )

    with pytest.raises(UnitAssetForbiddenError):
        await svc.update_unit_asset(db_session, other_user, asset.id, data=AIRCRAFT)


async def test_import_catalog_skips_system_conflicts(db_session, user):
    await svc.seed_default_unit_assets(db_session)
    payload = UnitAssetImportRequest(
        aircraftDb=[
            {
                **AIRCRAFT,
                "className": "KC-135R Stratotanker",
            }
        ]
    )

    result = await svc.import_unit_assets(db_session, user, payload)

    assert result.created == 0
    assert result.updated == 0
    assert result.skipped == 1


async def test_reset_removes_only_current_user_custom_assets(
    db_session, user, other_user
):
    own = await svc.create_unit_asset(
        db_session,
        user,
        asset_type="aircraft",
        data=AIRCRAFT,
    )
    other = await svc.create_unit_asset(
        db_session,
        other_user,
        asset_type="ship",
        data={
            "className": "Other Ship",
            "speed": 30,
            "maxFuel": 1000,
            "fuelRate": 50,
            "range": 300,
        },
    )

    rows = await svc.reset_user_unit_assets(db_session, user)
    ids = {row.id for row in rows}

    assert own.id not in ids
    assert await db_session.get(UnitAsset, own.id) is None
    assert await db_session.get(UnitAsset, other.id) is not None


async def test_estimate_unit_asset_marks_tanker_aircraft():
    data, confidence, warnings = estimate_unit_asset("aircraft", "KC-135R tanker")

    assert data["className"] == "KC-135R tanker"
    assert data["isTanker"] is True
    assert data["fuelOffloadCapacity"] > 0
    assert 0 < confidence < 1
    assert warnings


async def test_estimate_unit_asset_marks_electronic_warfare_aircraft():
    data, confidence, warnings = estimate_unit_asset("aircraft", "EA-18G Growler")

    assert data["className"] == "EA-18G Growler"
    assert data["isElectronicWarfare"] is True
    assert data["jammingRange"] > 0
    assert data["jammingStrength"] > 0
    assert "radar" in data["jammingModes"]
    assert 0 < confidence < 1
    assert warnings


async def test_normalize_aircraft_accepts_electronic_warfare_fields():
    name, normalized = svc.normalize_asset_data(
        "aircraft",
        {
            **AIRCRAFT,
            "className": "Custom EW Aircraft",
            "isElectronicWarfare": True,
            "jammingRange": 120,
            "jammingStrength": 0.45,
            "jammingModes": ["radar"],
            "communicationDisruption": 0.25,
        },
    )

    assert name == "Custom EW Aircraft"
    assert normalized["jammingStrength"] == 0.45


async def test_generate_unit_asset_payload_falls_back_without_model():
    data, source, confidence, warnings = await generate_unit_asset_payload(
        asset_type="weapon",
        query="AIM-120 air to air missile",
    )

    assert source == "estimate"
    assert data["className"] == "AIM-120 air to air missile"
    assert data["range"] > 0
    assert data["lethality"] > 0
    assert 0 < confidence < 1
    assert warnings


async def test_generate_unit_asset_payload_uses_openai_responses(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {
                    "output_text": json.dumps(
                        {
                            "type": "aircraft",
                            "data": {
                                "className": "Fictional Test Jet",
                                "speed": 950,
                                "maxFuel": 14000,
                                "fuelRate": 3300,
                                "range": 1100,
                                "isTanker": False,
                                "fuelOffloadCapacity": 0,
                                "fuelTransferRate": 0,
                                "refuelRange": 0,
                                "dataSource": {
                                    "speedSrc": "AI",
                                    "maxFuelSrc": "AI",
                                    "fuelRateSrc": "AI",
                                    "rangeSrc": "AI",
                                },
                                "units": {
                                    "speedUnit": "kts",
                                    "maxFuelUnit": "kg",
                                    "fuelRateUnit": "kg/h",
                                    "rangeUnit": "nm",
                                },
                            },
                            "confidence": 0.74,
                            "warnings": ["verify values"],
                        }
                    )
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    data, source, confidence, warnings = await generate_unit_asset_payload(
        asset_type="aircraft",
        query="Fictional Test Jet",
        provider="openai-responses",
        model="gpt-5-mini",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
    )

    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["body"]["text"]["format"]["type"] == "json_schema"
    assert captured["body"]["text"]["format"]["strict"] is True
    assert source == "llm"
    assert confidence == 0.74
    assert warnings == ["verify values"]
    assert data["className"] == "Fictional Test Jet"


async def test_generate_unit_asset_payload_uses_keyless_ollama(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "type": "aircraft",
                                        "data": {
                                            "className": "Local Test Jet",
                                            "speed": 880,
                                            "maxFuel": 11000,
                                            "fuelRate": 3100,
                                            "range": 900,
                                            "isTanker": False,
                                            "fuelOffloadCapacity": 0,
                                            "fuelTransferRate": 0,
                                            "refuelRange": 0,
                                            "dataSource": {
                                                "speedSrc": "AI",
                                                "maxFuelSrc": "AI",
                                                "fuelRateSrc": "AI",
                                                "rangeSrc": "AI",
                                            },
                                            "units": {
                                                "speedUnit": "kts",
                                                "maxFuelUnit": "kg",
                                                "fuelRateUnit": "kg/h",
                                                "rangeUnit": "nm",
                                            },
                                        },
                                        "confidence": 0.7,
                                        "warnings": [],
                                    }
                                )
                            }
                        }
                    ]
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    data, source, confidence, warnings = await generate_unit_asset_payload(
        asset_type="aircraft",
        query="Local Test Jet",
        provider="ollama",
        model="llama3.1",
        api_key="",
        base_url="http://localhost:11434/v1",
    )

    assert captured["url"] == "http://localhost:11434/v1/chat/completions"
    assert "Authorization" not in captured["headers"]
    assert source == "llm"
    assert confidence == 0.7
    assert warnings == []
    assert data["className"] == "Local Test Jet"


async def test_generate_unit_asset_payload_blocks_custom_private_base_url(monkeypatch):
    monkeypatch.setattr(
        endpoint_policy,
        "get_settings",
        lambda: Settings(env="production", allow_private_model_base_urls=False),
    )

    data, source, _confidence, warnings = await generate_unit_asset_payload(
        asset_type="aircraft",
        query="Private Test Jet",
        provider="custom",
        model="test-model",
        api_key="sk-test",
        base_url="http://127.0.0.1:8000/v1",
    )

    assert source == "estimate"
    assert any("Base URL blocked" in warning for warning in warnings)
    assert data["className"] == "Private Test Jet"
