"""F02 API 1 — player turn orchestration."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from agent_world.hbm_demo.features.f01_session.constants import DEFAULT_SIM_ID
from agent_world.hbm_demo.features.f01_session.lifecycle import (
    get_or_create_session,
    save_session,
)
from agent_world.hbm_demo.features.f01_session.logging import log_turn_event
from agent_world.hbm_demo.features.f01_session.models import HbmSession
from agent_world.hbm_demo.features.f01_session.paths import get_sim_dir
from agent_world.hbm_demo.features.f02_player_turn.inject import (
    build_inject_events,
    check_turn4_bad_end,
)
from agent_world.hbm_demo.features.f02_player_turn.task import PendingTask, save_task
from agent_world.hbm_demo.features.f04_stats.deltas import apply_stat_deltas
from agent_world.hbm_demo.features.f04_stats.scoring import generate_immediate_msg, score_player_turn
from agent_world.hbm_demo.features.f05_story_routing import routing
from agent_world.hbm_demo.features.f06_read_model.world_db import make_readonly_db
from agent_world.hbm_demo.http.ipc_helper import get_ipc_client, send_inject_batch
from agent_world.hbm_demo.shared.env_status import is_runner_ready, read_env_status
from agent_world.hbm_demo.shared.errors import RunnerNotReadyError
from agent_world.hbm_demo.shared.settings import DEFAULT_IPC_TIMEOUT

log = logging.getLogger("agent_world.hbm_demo.game_service")

BAD_END_PUBLIC_MESSAGES = [
    {
        "sender": "接待前台",
        "content": "保安，请这位先生离开。",
        "type": "F2F",
    }
]


def run_debug_inject(
    session: HbmSession,
    player_text: str,
    *,
    sim_dir: Path | None = None,
    tick_count: int = 6,
    timeout: float = 600.0,
) -> Dict[str, Any]:
    sim = sim_dir or get_sim_dir()
    if not is_runner_ready(sim):
        raise RunnerNotReadyError(
            "Runner not ready: start run_hbm first and wait for env_status.status=running"
        )
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    events, _broadcast, turn_ctx = build_inject_events(
        session, player_text, task_id=task_id
    )
    if not events:
        raise RuntimeError(f"no agents at place_id={session.place_id!r}")

    resp = send_inject_batch(
        get_ipc_client(str(sim)),
        events=events,
        turn_context=turn_ctx,
        tick_count=tick_count,
        timeout=timeout,
    )

    session.player_turn += 1
    return {
        "ipc": dict(resp.result or {}),
        "events_count": len(events),
        "agent_ids": [ev["effect"]["agent_id"] for ev in events],
    }


def handle_player_turn(
    flask_session: Any,
    *,
    sim_id: str,
    player_text: str,
    request_place_id: Optional[str] = None,
    request_phase: Optional[str] = None,
    request_player_turn: Optional[int] = None,
    sim_dir: Path | None = None,
    tick_count: int = 6,
    ipc_timeout: float = DEFAULT_IPC_TIMEOUT,
) -> Dict[str, Any]:
    sim = sim_dir or get_sim_dir()
    if not is_runner_ready(sim):
        raise RunnerNotReadyError(
            "Runner not ready: start run_hbm first and wait for env_status.status=running"
        )

    hbm = get_or_create_session(flask_session, sim_id, sim_dir=sim)
    if request_place_id and request_place_id != hbm.place_id:
        log.debug(
            "ignoring request place_id=%s; session authority=%s",
            request_place_id,
            hbm.place_id,
        )
    if request_phase and request_phase != hbm.phase:
        log.debug(
            "ignoring request phase=%s; session authority=%s",
            request_phase,
            hbm.phase,
        )
    if request_player_turn is not None and int(request_player_turn) != hbm.player_turn:
        log.debug(
            "ignoring request player_turn=%s; session authority=%s",
            request_player_turn,
            hbm.player_turn,
        )

    env = read_env_status(sim) or {}
    start_tick = int(env.get("current_tick", 0))
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    is_final_turn = hbm.player_turn == 25

    deltas = score_player_turn(hbm, player_text)
    apply_stat_deltas(hbm, deltas)

    if check_turn4_bad_end(hbm):
        save_session(flask_session, hbm, sim_id)
        return {
            "status": "game_over",
            "ending_id": "bad_reject",
            "public_messages": list(BAD_END_PUBLIC_MESSAGES),
            "stats_update": dict(hbm.stats),
            "current_phase": hbm.phase,
        }

    immediate_msg = generate_immediate_msg(hbm, player_text)

    events, broadcast, turn_ctx = build_inject_events(hbm, player_text, task_id=task_id)
    if not events:
        raise RuntimeError(
            f"no inject events for phase={hbm.phase!r} turn={hbm.player_turn}"
        )

    ipc_client = get_ipc_client(str(sim))
    resp = send_inject_batch(
        ipc_client,
        events=events,
        broadcast=broadcast,
        turn_context=turn_ctx,
        tick_count=tick_count,
        timeout=ipc_timeout,
    )

    ipc_result = dict(resp.result or {})
    env_after = read_env_status(sim) or {}
    current_tick = int(env_after.get("current_tick", start_tick))
    ipc_end_tick = int(
        ipc_result.get("end_tick", ipc_result.get("world_t", current_tick))
    )
    current_tick = max(current_tick, ipc_end_tick)
    db = make_readonly_db(sim)

    task_place_id = hbm.place_id
    task_phase = hbm.phase

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
            extra={"nodes": routing_info.get("nodes")},
        )

    hbm.player_turn += 1
    save_session(flask_session, hbm, sim_id)

    if is_final_turn:
        intent = routing.classify_turn25_intent(player_text)
        ending_id = routing.resolve_ending_id(intent, hbm.stats["trust"])
        log_turn_event(
            event="player_turn_completed",
            task_id=task_id,
            phase=hbm.phase,
            player_turn=hbm.player_turn - 1,
            start_tick=start_tick,
            end_tick=current_tick,
            extra={"status": "completed", "ending_id": ending_id},
        )
        return {
            "status": "completed",
            "ending_id": ending_id,
            "intent": intent,
            "immediate_msg": immediate_msg,
            "stats_update": dict(hbm.stats),
            "current_phase": hbm.phase,
            "routing": routing_info,
            "ipc": ipc_result,
        }

    task = PendingTask(
        task_id=task_id,
        start_tick=start_tick,
        place_id=task_place_id,
        phase=task_phase,
        player_turn=hbm.player_turn - 1,
        ipc_end_tick=ipc_end_tick,
    )
    save_task(flask_session, task, sim_id)

    log_turn_event(
        event="player_turn_processing",
        task_id=task_id,
        phase=hbm.phase,
        player_turn=task.player_turn,
        start_tick=start_tick,
        end_tick=ipc_end_tick,
    )

    return {
        "task_id": task_id,
        "immediate_msg": immediate_msg,
        "status": "processing",
        "stats_update": dict(hbm.stats),
        "current_phase": hbm.phase,
        "start_tick": start_tick,
        "ipc_end_tick": ipc_end_tick,
        "routing": routing_info,
        "ipc": ipc_result,
    }
