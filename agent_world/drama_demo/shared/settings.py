"""Environment-driven settings for drama demo (Phase 5)."""

from __future__ import annotations

import os


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


# IPC
DEFAULT_IPC_TIMEOUT = _float("DRAMA_IPC_TIMEOUT", 600.0)
DEFAULT_MOVE_TIMEOUT = _float("DRAMA_MOVE_TIMEOUT", 30.0)
DEFAULT_RESET_TIMEOUT = _float("DRAMA_RESET_TIMEOUT", 120.0)

# SQLite read-side (Flask API 2)
DB_CONNECT_TIMEOUT = _float("DRAMA_DB_TIMEOUT", 5.0)
DB_READ_RETRIES = _int("DRAMA_DB_READ_RETRIES", 6)
