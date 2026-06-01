"""F12 GET /world-snapshot handler."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from agent_world.drama_demo.features.f01_session.lifecycle import load_session
from agent_world.drama_demo.features.f01_session.paths import get_name_map, get_sim_dir
from agent_world.drama_demo.features.f06_read_model.world_db import make_readonly_db
from agent_world.drama_demo.features.f12_world_sync.delta import build_session_world_delta
from agent_world.drama_demo.features.f12_world_sync.snapshot import build_world_snapshot
from agent_world.drama_demo.shared.env_status import read_env_status


def get_world_snapshot(
    flask_session: Any,
    *,
    sim_id: str,
    sim_dir: Path | None = None,
) -> Dict[str, Any]:
    sim = sim_dir or get_sim_dir()
    hbm = load_session(flask_session, sim_id)
    env = read_env_status(sim) or {}
    t_now = int(env.get("current_tick", 0))
    from agent_world.drama_demo.shared import story_config

    db = make_readonly_db(sim)
    name_map = get_name_map()
    player_place = hbm.place_id if hbm else story_config.player_start_place()
    snapshot = build_world_snapshot(
        db,
        name_map,
        sim_dir=sim,
        since_tick=0,
        t_now=t_now,
        player_place_id=player_place,
    )
    delta = build_session_world_delta(
        since_tick=0,
        t_now=t_now,
        player_place_id=player_place,
        db=db,
        name_map=name_map,
    )
    return {
        **snapshot,
        **delta,
    }
