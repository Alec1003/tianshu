from __future__ import annotations

from app.platform import paths


def test_default_scenario_path_prefers_packaged_scenarios_dir(
    monkeypatch,
    tmp_path,
) -> None:
    packaged_scenarios = tmp_path / "scenarios"
    packaged_scenarios.mkdir()
    scenario = packaged_scenarios / "SCS.json"
    scenario.write_text("{}", encoding="utf-8")

    monkeypatch.setenv(paths.ENV_RESOURCE_DIR, str(tmp_path))
    monkeypatch.delenv(paths.ENV_RUNTIME_SCENARIO, raising=False)
    monkeypatch.delenv(paths.ENV_SCENARIOS_DIR, raising=False)

    assert paths.default_scenario_path() == scenario.resolve()


def test_default_scenario_path_resolves_relative_override_from_resource_root(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv(paths.ENV_RESOURCE_DIR, str(tmp_path))
    monkeypatch.setenv(paths.ENV_RUNTIME_SCENARIO, "runtime/scenario.json")

    assert paths.default_scenario_path() == (
        tmp_path / "runtime" / "scenario.json"
    ).resolve()


def test_scenario_dir_candidates_accept_explicit_packaged_dir(
    monkeypatch,
    tmp_path,
) -> None:
    explicit = tmp_path / "templates"
    explicit.mkdir()

    monkeypatch.setenv(paths.ENV_RESOURCE_DIR, str(tmp_path / "resources"))
    monkeypatch.setenv(paths.ENV_SCENARIOS_DIR, str(explicit))

    assert paths.scenarios_dir() == explicit.resolve()


def test_unit_assets_file_supports_packaged_layout(monkeypatch, tmp_path) -> None:
    packaged_assets = tmp_path / "unit_assets"
    packaged_assets.mkdir()
    default_assets = packaged_assets / "default_unit_assets.json"
    default_assets.write_text("{}", encoding="utf-8")

    monkeypatch.setenv(paths.ENV_RESOURCE_DIR, str(tmp_path))
    monkeypatch.delenv(paths.ENV_UNIT_ASSETS_FILE, raising=False)

    assert paths.unit_assets_file() == default_assets.resolve()


def test_user_data_dir_can_be_set_for_desktop_packaging(
    monkeypatch,
    tmp_path,
) -> None:
    user_data = tmp_path / "user-data"

    monkeypatch.setenv(paths.ENV_USER_DATA_DIR, str(user_data))

    assert paths.user_data_dir() == user_data.resolve()
