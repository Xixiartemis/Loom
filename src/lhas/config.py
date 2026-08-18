"""Runtime configuration: data root, DB path, log dir (docs/03_ENGINEERING_CONSTRAINTS.md)."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_HOME = Path(__file__).resolve().parent.parent.parent.parent / "data"


def lhas_home() -> Path:
    """LHAS_HOME env override; defaults to <repo>/data."""
    return Path(os.environ.get("LHAS_HOME", DEFAULT_HOME)).expanduser().resolve()


def db_path() -> Path:
    """LHAS_DB_PATH env override; defaults to <LHAS_HOME>/lhas.db."""
    override = os.environ.get("LHAS_DB_PATH")
    if override:
        return Path(override).expanduser().resolve()
    return lhas_home() / "lhas.db"


def log_dir() -> Path:
    return lhas_home() / "logs"
