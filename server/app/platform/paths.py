from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

ENV_APP_ROOT = "AICC_APP_ROOT"
ENV_RESOURCE_DIR = "AICC_RESOURCE_DIR"
ENV_USER_DATA_DIR = "AICC_USER_DATA_DIR"
ENV_GYM_DIR = "AICC_GYM_DIR"
ENV_SCENARIOS_DIR = "AICC_SCENARIOS_DIR"
ENV_UNIT_ASSETS_FILE = "AICC_UNIT_ASSETS_FILE"
ENV_RUNTIME_SCENARIO = "AICC_MCP_RUNTIME_SCENARIO"

SOURCE_ROOT = Path(__file__).resolve().parents[3]


def _normalize(path: Path) -> Path:
    return path.expanduser().resolve()


def _env_path(name: str, *, base: Path | None = None) -> Path | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_absolute() and base is not None:
        path = base / path
    return path.resolve()


def _unique(paths: Iterable[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        normalized = _normalize(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def app_root() -> Path:
    """Return the source-style application root.

    In source and Docker runs this is the repository root. Desktop launchers can
    set ``AICC_APP_ROOT`` when the Python server is extracted elsewhere.
    """

    return _env_path(ENV_APP_ROOT) or SOURCE_ROOT


def resource_root() -> Path:
    """Return the read-only packaged resources root.

    Electron should point ``AICC_RESOURCE_DIR`` at extraResources; source and
    Docker keep using the repository-shaped root.
    """

    return _env_path(ENV_RESOURCE_DIR, base=app_root()) or app_root()


def user_data_dir() -> Path:
    """Return the writable desktop/server data directory."""

    return (
        _env_path(ENV_USER_DATA_DIR, base=app_root())
        or app_root() / "server" / "data"
    )


def gym_dir() -> Path:
    return _env_path(ENV_GYM_DIR, base=resource_root()) or resource_root() / "gym"


def resolve_resource_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (resource_root() / candidate).resolve()


def scenario_dir_candidates() -> list[Path]:
    candidates: list[Path] = []
    explicit = _env_path(ENV_SCENARIOS_DIR, base=resource_root())
    if explicit is not None:
        candidates.append(explicit)
    for root in (resource_root(), app_root()):
        candidates.extend(
            [
                root / "client" / "src" / "scenarios",
                root / "scenarios",
            ]
        )
    return _unique(candidates)


def scenarios_dir() -> Path | None:
    for candidate in scenario_dir_candidates():
        if candidate.is_dir():
            return candidate
    return None


def default_scenario_path() -> Path:
    override = os.environ.get(ENV_RUNTIME_SCENARIO, "").strip()
    if override:
        return resolve_resource_path(override)

    for candidate_dir in scenario_dir_candidates():
        candidate = candidate_dir / "SCS.json"
        if candidate.is_file():
            return candidate

    return scenario_dir_candidates()[0] / "SCS.json"


def unit_assets_file() -> Path:
    explicit = _env_path(ENV_UNIT_ASSETS_FILE, base=resource_root())
    if explicit is not None:
        return explicit

    candidates = _unique(
        [
            resource_root() / "server" / "app" / "unit_assets" / "default_unit_assets.json",
            resource_root() / "unit_assets" / "default_unit_assets.json",
            app_root() / "server" / "app" / "unit_assets" / "default_unit_assets.json",
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]
