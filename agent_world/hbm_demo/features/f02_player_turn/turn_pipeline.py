"""Shared F02/F11 inject + routing pipeline (dev_logs/38 R4)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent_world.hbm_demo.features.f01_session.models import HbmSession
from agent_world.hbm_demo.features.f05_story_routing import routing
from agent_world.hbm_demo.features.f06_read_model.world_db import make_readonly_db
from agent_world.hbm_demo.features.f17_virtual_player.player_f2f import (
    build_player_f2f_payload,
)
from agent_world.hbm_demo.features.f07_agent_control.config import is_world_loop_enabled
from agent_world.hbm_demo.http.ipc_helper import (
    get_ipc_client,
    push_session_mirror,
    push_turn_context_mirror,
    resolve_loop_min_ticks,
    send_enqueue_player_input,
    send_inject_batch,
    wait_for_loop_window,
)
from agent_world.hbm_demo.shared.env_status import read_env_status

log = logging.getLogger("agent_world.hbm_demo.turn_pipeline")


def execute_inject(
    *,
    sim_dir: Path,
    hbm: HbmSession,
    player_text: str,
    events: List[Dict[str, Any]],
    broadcast: Optional[Dict[str, Any]],
    turn_context: Optional[Dict[str, Any]],
    start_tick: int,
    task_phase: str,
    tick_count: int,
    ipc_timeout: float,
) -> Tuple[int, Dict[str, Any], int]:
    """Run IPC inject (world loop enqueue or legacy batch). Returns ipc_end_tick, ipc_result, current_tick."""
    ipc_client = get_ipc_client(str(sim_dir))
    min_ticks = resolve_loop_min_ticks(task_phase, tick_count)
    player_f2f = build_player_f2f_payload(hbm, player_text)

    if is_world_loop_enabled():
        send_enqueue_player_input(
            ipc_client,
            events=events,
            broadcast=broadcast,
            turn_context=turn_context,
            player_f2f=player_f2f,
            timeout=ipc_timeout,
        )
        push_turn_context_mirror(
            ipc_client,
            turn_context,
            stats=dict(hbm.stats),
            timeout=ipc_timeout,
        )
        hbm.player_turn += 1
        loop_status = wait_for_loop_window(
            ipc_client,
            start_tick=start_tick,
            min_ticks=min_ticks,
            timeout=ipc_timeout,
        )
        ipc_result = dict(loop_status)
        ipc_end_tick = int(loop_status.get("current_tick", start_tick))
        push_session_mirror(ipc_client, hbm, timeout=ipc_timeout)
    else:
        resp = send_inject_batch(
            ipc_client,
            events=events,
            broadcast=broadcast,
            turn_context=turn_context,
            tick_count=tick_count,
            player_f2f=player_f2f,
            timeout=ipc_timeout,
        )
        ipc_result = dict(resp.result or {})
        env_after = read_env_status(sim_dir) or {}
        current_tick = int(env_after.get("current_tick", start_tick))
        ipc_end_tick = int(
            ipc_result.get("end_tick", ipc_result.get("world_t", current_tick))
        )
        ipc_end_tick = max(current_tick, ipc_end_tick)
        hbm.player_turn += 1

    env_after = read_env_status(sim_dir) or {}
    current_tick = int(env_after.get("current_tick", ipc_end_tick))
    ipc_end_tick = max(current_tick, ipc_end_tick)
    return ipc_end_tick, ipc_result, ipc_end_tick


def apply_routing_side_effects(
    *,
    hbm: HbmSession,
    sim_dir: Path,
    task_id: str,
    start_tick: int,
    current_tick: int,
    tick_count: int,
    ipc_timeout: float,
    async_mode: bool = False,
) -> Dict[str, Any]:
    """F05 routing after inject; mirrors session when nodes fire."""
    ipc_client = get_ipc_client(str(sim_dir))
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
        push_session_mirror(ipc_client, hbm, timeout=ipc_timeout)
        log.info(
            "routing applied nodes=%s async=%s start=%s end=%s",
            routing_info.get("nodes"),
            async_mode,
            start_tick,
            current_tick,
        )
    return dict(routing_info) if routing_info else {}
