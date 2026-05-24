"""F11 background inject + routing (runs off the HTTP request thread)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_world.hbm_demo.features.f01_session.logging import log_turn_event
from agent_world.hbm_demo.features.f01_session.models import HbmSession
from agent_world.hbm_demo.features.f02_player_turn.task import (
    INJECT_STATUS_DONE,
    INJECT_STATUS_FAILED,
    INJECT_STATUS_RUNNING,
    PendingTask,
)
from agent_world.hbm_demo.features.f05_story_routing import routing
from agent_world.hbm_demo.features.f06_read_model.world_db import make_readonly_db
from agent_world.hbm_demo.features.f11_live_turn_sync.task_state import save_task_runtime
from agent_world.hbm_demo.http.ipc_helper import get_ipc_client, send_inject_batch
from agent_world.hbm_demo.shared.env_status import read_env_status

log = logging.getLogger("agent_world.hbm_demo.f11")


def run_background_inject(
    *,
    sim_dir: Path,
    sim_id: str,
    task_id: str,
    hbm: HbmSession,
    events: List[Dict[str, Any]],
    broadcast: Optional[Dict[str, Any]],
    start_tick: int,
    task_place_id: str,
    task_phase: str,
    task_player_turn: int,
    tick_count: int,
    ipc_timeout: float,
) -> None:
    task = PendingTask(
        task_id=task_id,
        start_tick=start_tick,
        place_id=task_place_id,
        phase=task_phase,
        player_turn=task_player_turn,
        inject_status=INJECT_STATUS_RUNNING,
    )
    try:
        ipc_client = get_ipc_client(str(sim_dir))
        resp = send_inject_batch(
            ipc_client,
            events=events,
            broadcast=broadcast,
            tick_count=tick_count,
            timeout=ipc_timeout,
        )

        ipc_result = dict(resp.result or {})
        env_after = read_env_status(sim_dir) or {}
        current_tick = int(env_after.get("current_tick", start_tick))
        ipc_end_tick = int(
            ipc_result.get("end_tick", ipc_result.get("world_t", current_tick))
        )
        current_tick = max(current_tick, ipc_end_tick)
        db = make_readonly_db(sim_dir)

        routing_info = routing.apply_routing(
            hbm,
            ipc_client=ipc_client,
            db=db,
            task_id=task_id,
            current_tick=current_tick,
            tick_count=tick_count,
            ipc_timeout=ipc_timeout,
        )
        if routing_info.get("nodes"):
            log_turn_event(
                event="routing_applied",
                task_id=task_id,
                phase=hbm.phase,
                player_turn=hbm.player_turn,
                start_tick=start_tick,
                end_tick=current_tick,
                extra={"nodes": routing_info.get("nodes"), "async": True},
            )

        hbm.player_turn += 1

        task.ipc_end_tick = ipc_end_tick
        task.inject_status = INJECT_STATUS_DONE
        task.inject_error = None
        save_task_runtime(sim_dir, task.to_dict(), session_dict=hbm.to_dict())

        log_turn_event(
            event="player_turn_async_completed",
            task_id=task_id,
            phase=hbm.phase,
            player_turn=task_player_turn,
            start_tick=start_tick,
            end_tick=ipc_end_tick,
            extra={"inject_status": INJECT_STATUS_DONE},
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("F11 async inject failed task_id=%s", task_id)
        task.inject_status = INJECT_STATUS_FAILED
        task.inject_error = str(exc)
        save_task_runtime(sim_dir, task.to_dict())
        log_turn_event(
            event="player_turn_async_failed",
            task_id=task_id,
            phase=task_phase,
            player_turn=task_player_turn,
            start_tick=start_tick,
            end_tick=start_tick,
            extra={"error": str(exc)},
        )
