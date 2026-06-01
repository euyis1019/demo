"""F12 full world snapshot for session refresh / calibration."""

from __future__ import annotations

from typing import Any, Dict, Optional

from agent_world.drama_demo.features.f06_read_model.world_db import ReadOnlyWorldDB
from agent_world.drama_demo.features.f12_world_sync.constants import room_places
from agent_world.drama_demo.features.f12_world_sync.formatter import (
    format_agent_locations,
    parse_place_attrs,
)
from agent_world.drama_demo.features.f12_world_sync.runner_bridge import (
    fetch_runner_locations,
)


def build_world_snapshot(
    db: ReadOnlyWorldDB,
    name_map: Dict[int, str],
    *,
    sim_dir: Optional[Any] = None,
    since_tick: int = 0,
    t_now: int,
    player_place_id: str = "",
) -> Dict[str, Any]:
    """Read-model snapshot; optionally merge Runner IPC locations."""
    agent_locations = format_agent_locations(db.fetch_all_agent_locations())
    runner_locations = fetch_runner_locations(sim_dir)
    if runner_locations:
        agent_locations = runner_locations

    place_attrs_raw = db.fetch_place_attrs(list(room_places()))
    place_attrs = {
        pid: parse_place_attrs(raw) for pid, raw in place_attrs_raw.items()
    }

    return {
        "through_tick": int(t_now),
        "player_place_id": player_place_id,
        "agent_locations": agent_locations,
        "place_attrs": place_attrs,
        "relations": db.fetch_relations_snapshot(),
        "group_members": {
            str(gid): members
            for gid, members in db.fetch_group_members().items()
        },
        "name_map": {str(k): v for k, v in name_map.items()},
    }
