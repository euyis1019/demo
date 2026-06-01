"""F11 incremental message delta for action-result processing polls."""

from __future__ import annotations

from typing import Any, Dict

from agent_world.drama_demo.features.f02_player_turn.task import PendingTask
from agent_world.drama_demo.features.f06_read_model.world_db import ReadOnlyWorldDB
from agent_world.drama_demo.features.f12_world_sync.delta import (
    build_world_delta as build_f12_world_delta,
    empty_delta as f12_empty_delta,
)


def build_turn_delta(
    task: PendingTask,
    since_tick: int,
    effective_tick: int,
    db: ReadOnlyWorldDB,
    name_map: Dict[int, str],
) -> Dict[str, Any]:
    """Messages and world sync fields with ``attempted_at > since_tick``."""
    return build_f12_world_delta(
        task,
        since_tick,
        effective_tick,
        db,
        name_map,
    )


def empty_delta(through_tick: int, *, player_place_id: str = "") -> Dict[str, Any]:
    return f12_empty_delta(through_tick, player_place_id=player_place_id)
