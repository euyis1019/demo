"""Structured turn logging for Flask-side features."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

log = logging.getLogger("agent_world.drama_demo.game_service")


def log_turn_event(
    *,
    event: str,
    task_id: str,
    phase: str,
    player_turn: int,
    start_tick: int,
    end_tick: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    payload: Dict[str, Any] = {
        "event": event,
        "task_id": task_id,
        "phase": phase,
        "player_turn": player_turn,
        "start_tick": start_tick,
    }
    if end_tick is not None:
        payload["end_tick"] = end_tick
    if extra:
        payload.update(extra)
    log.info("hbm %s", payload)
