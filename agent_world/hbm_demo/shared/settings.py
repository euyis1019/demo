"""Environment-driven settings for HBM demo (Phase 5)."""

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
DEFAULT_IPC_TIMEOUT = _float("HBM_IPC_TIMEOUT", 600.0)
DEFAULT_MOVE_TIMEOUT = _float("HBM_MOVE_TIMEOUT", 30.0)
DEFAULT_RESET_TIMEOUT = _float("HBM_RESET_TIMEOUT", 120.0)

# SQLite read-side (Flask API 2)
DB_CONNECT_TIMEOUT = _float("HBM_DB_TIMEOUT", 5.0)
DB_READ_RETRIES = _int("HBM_DB_READ_RETRIES", 6)

# LLM helpers (API 1)
IMMEDIATE_MSG_TIMEOUT = _float("HBM_IMMEDIATE_MSG_TIMEOUT", 1.0)
