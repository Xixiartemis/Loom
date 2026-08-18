"""Logging setup per docs/10_LOGGING_SPEC.md.

- module logger name: ``lhas.<module>``
- console: WARNING+ (CLI keeps its own output)
- file: INFO+, structured ``event=... task=... run=... attempt=... seq=...`` lines
- secrets are never logged; experiment logs are append-only (new file per run
  is handled by the experiment recorder, not by rotation here).
"""

from __future__ import annotations

import logging
from pathlib import Path

_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def setup_logging(log_dir: str | Path | None = None, level: int = logging.INFO) -> Path:
    """Configure root lhas loggers; returns the log file path."""
    import lhas.config as cfg

    log_path = Path(log_dir) if log_dir else (cfg.log_dir() / "lhas.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(_FORMAT)
    root = logging.getLogger("lhas")
    root.setLevel(level)
    root.handlers.clear()

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(fmt)
    root.addHandler(console)

    root.propagate = False
    return log_path
