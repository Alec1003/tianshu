from __future__ import annotations

from pathlib import Path


def test_alembic_baseline_exists() -> None:
    server_root = Path(__file__).resolve().parents[1]

    assert (server_root / "alembic.ini").is_file()
    assert (server_root / "alembic" / "env.py").is_file()
    assert (server_root / "alembic" / "versions" / "0001_baseline.py").is_file()
