"""Load and cache F07 turn_control.yaml."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml

_FEATURE_DIR = Path(__file__).resolve().parent
_TURN_CONTROL_PATH = _FEATURE_DIR / "turn_control.yaml"


@lru_cache(maxsize=1)
def load_turn_control() -> Dict[str, Any]:
    if not _TURN_CONTROL_PATH.is_file():
        return {"enabled": False}
    with _TURN_CONTROL_PATH.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        return {"enabled": False}
    return data


def is_f07_enabled() -> bool:
    return bool(load_turn_control().get("enabled", False))


def resolve_inject_tick_count(phase: str, tick_count: int) -> int:
    """Phase 1 + F07 needs inject batch ≥ start+8 for §13.2 timeout completion."""
    n = int(tick_count)
    if not is_f07_enabled():
        return n
    if str(phase) == "Phase 1":
        return max(n, 8)
    return n


def story_knowledge_dir() -> Path:
    return _FEATURE_DIR / "story_knowledge"
