"""Load and cache F07 turn_control.yaml."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

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


def is_experience_hardening() -> bool:
    """F07-E — player-facing F2F channel + later guard rails."""
    if not is_f07_enabled():
        return False
    block = load_turn_control().get("experience_hardening") or {}
    return bool(block.get("enabled", False))


def experience_hardening_block() -> Dict[str, Any]:
    if not is_experience_hardening():
        return {}
    block = load_turn_control().get("experience_hardening") or {}
    return dict(block) if isinstance(block, dict) else {}


def first_f2f_required_agents(phase: str) -> List[int]:
    """Agents that must emit F2F before other tools (dev_logs/29 E1)."""
    table = experience_hardening_block().get("first_f2f_required") or {}
    raw = table.get(str(phase)) or []
    return [int(x) for x in raw]


def scripted_f2f_fallback_enabled() -> bool:
    block = experience_hardening_block()
    if not block:
        return False
    return block.get("scripted_f2f_fallback", True) is not False


def resolve_inject_tick_count(phase: str, tick_count: int) -> int:
    """Floor inject batch length for F07 completion semantics (§13.2 / dev_logs/29 E5)."""
    n = int(tick_count)
    if not is_f07_enabled():
        return n
    phase_s = str(phase)
    if is_experience_hardening() and phase_s in ("Phase 1", "Phase 2", "Phase 4"):
        return max(n, 12)
    if phase_s == "Phase 1":
        return max(n, 8)
    return n


def story_knowledge_dir() -> Path:
    return _FEATURE_DIR / "story_knowledge"
