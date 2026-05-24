"""F11 incremental message delta for action-result processing polls."""

from __future__ import annotations

from typing import Any, Dict

from agent_world.hbm_demo.features.f02_player_turn.task import PendingTask
from agent_world.hbm_demo.features.f03_action_result.completion import (
    format_f2f_public_messages,
    format_messages,
)
from agent_world.hbm_demo.features.f06_read_model.world_db import ReadOnlyWorldDB


def build_turn_delta(
    task: PendingTask,
    since_tick: int,
    effective_tick: int,
    db: ReadOnlyWorldDB,
    name_map: Dict[int, str],
) -> Dict[str, Any]:
    """Messages with ``attempted_at > since_tick`` up to ``effective_tick``."""
    since_t = max(int(since_tick), task.start_tick)
    t_now = max(effective_tick, since_t)

    f2f_history = db.fetch_f2f_history_at(
        task.place_id, t_now, task.start_tick
    )
    public_messages = format_f2f_public_messages(
        [h for h in f2f_history if h[0] > since_t],
        name_map,
    )

    rdc_rows = db.fetch_messages_since(
        channel_type="RDC", since_t=since_t, t_now=t_now
    )
    observer_messages = format_messages(rdc_rows, name_map)

    grp_rows = db.fetch_messages_since(
        channel_type="GRP", since_t=since_t, t_now=t_now
    )
    group_messages = format_messages(grp_rows, name_map)

    return {
        "public_messages": public_messages,
        "observer_messages": observer_messages,
        "group_messages": group_messages,
        "through_tick": t_now,
    }


def empty_delta(through_tick: int) -> Dict[str, Any]:
    return {
        "public_messages": [],
        "observer_messages": [],
        "group_messages": [],
        "through_tick": through_tick,
    }
