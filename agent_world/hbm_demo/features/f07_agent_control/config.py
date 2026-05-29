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


_PASSIVE_PROB = {"low": 0.25, "medium": 0.50, "high": 0.75}


def passive_tick_probability(phase: str) -> float:
    """L3 passive agent sampling probability per phase."""
    phases = load_turn_control().get("phases") or {}
    block = phases.get(phase) or {}
    key = str(block.get("passive_tick_probability", "medium"))
    return _PASSIVE_PROB.get(key, 0.5)


def inject_exclusive_ticks_for(phase: str) -> int:
    """First N ticks after player inject only run inject targets (L3 staging)."""
    phases = load_turn_control().get("phases") or {}
    phase_block = phases.get(str(phase)) or {}
    if "inject_exclusive_ticks" in phase_block:
        return max(0, int(phase_block["inject_exclusive_ticks"]))
    return 0


def max_inject_tick_loops() -> int:
    """IPC inject batch tick cap (sync with resolve_inject_tick_count floor)."""
    return 8


def resolve_inject_tick_loops(tick_count: int) -> int:
    n = int(tick_count)
    return max(3, min(n, max_inject_tick_loops()))


def resolve_inject_tick_count(phase: str, tick_count: int) -> int:
    """Floor inject batch length for F07 completion semantics."""
    n = int(tick_count)
    if not is_f07_enabled():
        return n
    if str(phase) == "Phase 1":
        return max(n, 8)
    return n


def story_knowledge_dir() -> Path:
    return _FEATURE_DIR / "story_knowledge"


def world_loop_block() -> Dict[str, Any]:
    block = load_turn_control().get("world_loop") or {}
    return dict(block) if isinstance(block, dict) else {}


def player_input_block() -> Dict[str, Any]:
    block = load_turn_control().get("player_input") or {}
    return dict(block) if isinstance(block, dict) else {}


def is_world_loop_enabled() -> bool:
    return bool(world_loop_block().get("enabled", False))


def world_loop_tick_interval() -> float:
    return float(world_loop_block().get("tick_interval_sec", 1.0))


def world_loop_max_ticks() -> int:
    return int(world_loop_block().get("max_ticks_per_session", 10000))


def player_input_max_depth() -> int:
    return int(player_input_block().get("max_queue_depth", 32))


def is_manual_pause_allowed() -> bool:
    return bool(world_loop_block().get("allow_manual_pause", True))


def pause_drains_queue() -> bool:
    return bool(world_loop_block().get("pause_drains_queue", False))


def prompt_trace_block() -> Dict[str, Any]:
    block = load_turn_control().get("prompt_trace") or {}
    return dict(block) if isinstance(block, dict) else {}


def is_prompt_trace_enabled() -> bool:
    return bool(prompt_trace_block().get("enabled", False))


def prompt_trace_max_per_session() -> int:
    return int(prompt_trace_block().get("max_traces_per_session", 5000))


def prompt_trace_truncate_chars() -> int:
    return int(prompt_trace_block().get("truncate_prompt_chars", 0))


def recap_window_ticks() -> int:
    raw = load_turn_control().get("recap_window_ticks", 20)
    return max(1, int(raw))
