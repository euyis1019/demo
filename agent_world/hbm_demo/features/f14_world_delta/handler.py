"""F14 GET /world-delta — session-scoped incremental sync (dev_logs/31 §十四)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from agent_world.hbm_demo.features.f01_session.lifecycle import load_session
from agent_world.hbm_demo.features.f01_session.paths import get_name_map, get_sim_dir
from agent_world.hbm_demo.features.f04_stats.deltas import initial_stats
from agent_world.hbm_demo.features.f05_story_routing.watcher import (
    consume_game_over_payload,
    consume_routing_world_events,
    scan_routing_if_needed,
)
from agent_world.hbm_demo.features.f06_read_model.world_db import make_readonly_db
from agent_world.hbm_demo.features.f12_world_sync.delta import build_session_world_delta
from agent_world.hbm_demo.shared.env_status import read_env_status
from agent_world.hbm_demo.shared.errors import RunnerNotReadyError


def get_world_delta(
    flask_session: Any,
    *,
    sim_id: str,
    since_tick: Optional[int] = None,
    sim_dir: Path | None = None,
) -> Dict[str, Any]:
    """Return incremental world delta for the current Flask session."""
    sim = sim_dir or get_sim_dir()
    env = read_env_status(sim)
    if env is None:
        raise RunnerNotReadyError(
            "Runner not ready: start run_hbm first and wait for env_status.json"
        )

    hbm = load_session(flask_session, sim_id)
    t_now = int(env.get("current_tick", 0))
    client_since = max(0, int(since_tick)) if since_tick is not None else 0

    if hbm is not None:
        scan_routing_if_needed(
            flask_session,
            hbm,
            sim_id=sim_id,
            sim_dir=sim,
            current_tick=t_now,
        )

    from agent_world.hbm_demo.shared import story_config

    db = make_readonly_db(sim)
    name_map = get_name_map()
    player_place = hbm.place_id if hbm else story_config.player_start_place()
    routing_events = consume_routing_world_events(
        flask_session,
        since_tick=client_since,
        t_now=t_now,
    )

    delta = build_session_world_delta(
        since_tick=client_since,
        t_now=t_now,
        player_place_id=player_place,
        db=db,
        name_map=name_map,
        extra_world_events=routing_events,
    )

    result: Dict[str, Any] = {
        **delta,
        "current_tick": t_now,
        "loop_state": env.get("loop_state"),
        "stats_update": dict(hbm.stats) if hbm else initial_stats(),
        "current_phase": hbm.phase if hbm else "",
        "tension": hbm.tension if hbm else 0,
        "player_turn": hbm.player_turn if hbm else 1,
        # 让 delta 自洽：带上 name_map(agent_id→名)，前端轮询不必依赖 snapshot 缓存、也无需写死角色名。
        "name_map": {str(k): v for k, v in name_map.items()},
    }

    game_over = consume_game_over_payload(flask_session)
    if game_over:
        result["game_over"] = game_over
    elif hbm and hbm.ending_id:
        # 数据驱动：结局好坏由该故事 ending 的 kind 决定（bad→game_over 屏，其余→completed 结局屏）。
        end = story_config.active_pack().graph.endings.get(hbm.ending_id)
        end_kind = end.kind if end else "neutral"
        result["game_over"] = {
            "status": "game_over" if end_kind == "bad" else "completed",
            "ending_id": hbm.ending_id,
            "ending_summary": (end.summary if end else "") or "",
            "ending_kind": end_kind,
            "stats_update": dict(hbm.stats),
            "current_phase": hbm.phase,
        }

    return result


__all__ = ["get_world_delta"]
