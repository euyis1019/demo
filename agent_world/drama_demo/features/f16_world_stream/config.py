"""F16 — WebSocket world delta stream (dev_logs/31 §14.4 Phase 5)."""

from __future__ import annotations

from typing import Any, Dict

from agent_world.drama_demo.features.f07_agent_control.config import load_turn_control

__all__ = ["is_world_stream_enabled", "world_stream_poll_interval"]


def _block() -> Dict[str, Any]:
    raw = load_turn_control().get("world_stream") or {}
    return dict(raw) if isinstance(raw, dict) else {}


def is_world_stream_enabled() -> bool:
    return bool(_block().get("enabled", False))


def world_stream_poll_interval() -> float:
    raw = _block().get("poll_interval_sec", 0.25)
    try:
        return max(0.1, float(raw))
    except (TypeError, ValueError):
        return 0.25
