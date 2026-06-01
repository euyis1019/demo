"""F03 API 2 — poll action completion and fetch messages."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from agent_world.drama_demo.features.f01_session.constants import DEFAULT_SIM_ID
from agent_world.drama_demo.features.f01_session.lifecycle import load_session
from agent_world.drama_demo.features.f01_session.logging import log_turn_event
from agent_world.drama_demo.features.f01_session.paths import get_name_map, get_sim_dir
from agent_world.drama_demo.features.f03_action_result.completion import (
    check_action_complete,
    effective_tick_for_task,
)
from agent_world.drama_demo.features.f04_stats.deltas import initial_stats
from agent_world.drama_demo.features.f06_read_model.world_db import make_readonly_db
from agent_world.drama_demo.features.f02_player_turn.task import INJECT_STATUS_FAILED
from agent_world.drama_demo.features.f11_live_turn_sync.task_state import (
    get_turn_outcome,
    load_task_resolved,
    sync_runtime_state,
)
from agent_world.drama_demo.features.f11_live_turn_sync.delta import (
    build_turn_delta,
    empty_delta,
)
from agent_world.drama_demo.features.f12_world_sync.delta import build_completed_payload
from agent_world.drama_demo.features.f07_agent_control.config import is_world_loop_enabled
from agent_world.drama_demo.shared.env_status import read_env_status

log = logging.getLogger("agent_world.drama_demo.game_service")


def get_action_result(
    flask_session: Any,
    *,
    sim_id: str,
    task_id: str,
    request_place_id: Optional[str] = None,
    since_tick: Optional[int] = None,
    sim_dir: Path | None = None,
) -> Dict[str, Any]:
    sim = sim_dir or get_sim_dir()

    if is_world_loop_enabled():
        from agent_world.drama_demo.features.f14_world_delta.handler import get_world_delta

        client_since = int(since_tick) if since_tick is not None else 0
        return get_world_delta(
            flask_session,
            sim_id=sim_id,
            since_tick=client_since,
            sim_dir=sim,
        )

    sync_runtime_state(flask_session, sim_id, sim_dir=sim)

    hbm = load_session(flask_session, sim_id)
    task = load_task_resolved(flask_session, task_id, sim_id, sim_dir=sim)
    if task is None:
        raise KeyError(f"unknown task_id: {task_id}")

    outcome = get_turn_outcome(sim, task_id)
    if outcome and outcome.get("status") == "game_over":
        return {
            "status": "game_over",
            "task_id": task_id,
            "ending_id": outcome.get("ending_id", "bad_reject"),
            "public_messages": outcome.get("public_messages") or [],
            "stats_update": outcome.get("stats_update") or initial_stats(),
        }

    if task.inject_status == INJECT_STATUS_FAILED:
        return {
            "status": "error",
            "task_id": task_id,
            "inject_status": task.inject_status,
            "error": task.inject_error or "inject failed",
        }

    if request_place_id and request_place_id != task.place_id:
        log.debug(
            "ignoring request place_id=%s; task authority=%s",
            request_place_id,
            task.place_id,
        )

    env = read_env_status(sim)
    client_since = int(since_tick) if since_tick is not None else task.start_tick

    if not env or "current_tick" not in env:
        return {
            "status": "processing",
            "task_id": task_id,
            "inject_status": task.inject_status,
            "start_tick": task.start_tick,
            "delta": empty_delta(task.start_tick, player_place_id=task.place_id),
        }

    env_tick = int(env["current_tick"])
    effective_tick = effective_tick_for_task(task, env_tick)
    db = make_readonly_db(sim)
    name_map = get_name_map()
    delta = build_turn_delta(task, client_since, effective_tick, db, name_map)

    if not check_action_complete(task, effective_tick, db):
        return {
            "status": "processing",
            "task_id": task_id,
            "current_tick": env_tick,
            "effective_tick": effective_tick,
            "start_tick": task.start_tick,
            "ipc_end_tick": task.ipc_end_tick,
            "inject_status": task.inject_status,
            "delta": delta,
        }

    stats_update = dict(hbm.stats) if hbm else initial_stats()

    completed = build_completed_payload(
        task,
        effective_tick,
        db,
        name_map,
        stats_update=stats_update,
    )

    log_turn_event(
        event="action_result_completed",
        task_id=task_id,
        player_turn=task.player_turn,
        start_tick=task.start_tick,
        end_tick=effective_tick,
        extra={
            "public_count": len(completed.get("public_messages") or []),
            "rdc_count": len(completed.get("observer_messages") or []),
            "grp_count": len(completed.get("group_messages") or []),
            "room_f2f_places": sum(
                len(v) for v in (completed.get("room_f2f") or {}).values()
            ),
        },
    )

    return completed
