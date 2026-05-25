"""F11 background turn pipeline: F04 scoring + enqueue + routing."""

from __future__ import annotations

import logging
from pathlib import Path

from agent_world.hbm_demo.features.f01_session.logging import log_turn_event
from agent_world.hbm_demo.features.f01_session.models import HbmSession
from agent_world.hbm_demo.features.f02_player_turn.inject import (
    BAD_END_PUBLIC_MESSAGES,
    build_inject_events,
    check_turn4_bad_end,
)
from agent_world.hbm_demo.features.f02_player_turn.task import (
    INJECT_STATUS_DONE,
    INJECT_STATUS_FAILED,
    INJECT_STATUS_RUNNING,
    PendingTask,
)
from agent_world.hbm_demo.features.f04_stats.deltas import apply_stat_deltas
from agent_world.hbm_demo.features.f04_stats.scoring import score_player_turn
from agent_world.hbm_demo.features.f05_story_routing import routing
from agent_world.hbm_demo.features.f06_read_model.world_db import make_readonly_db
from agent_world.hbm_demo.features.f07_agent_control.config import is_world_loop_enabled
from agent_world.hbm_demo.features.f11_live_turn_sync.task_state import save_task_runtime
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

log = logging.getLogger("agent_world.hbm_demo.f11")


def run_background_turn(
    *,
    sim_dir: Path,
    sim_id: str,
    task_id: str,
    hbm: HbmSession,
    player_text: str,
    start_tick: int,
    task_place_id: str,
    task_phase: str,
    task_player_turn: int,
    tick_count: int,
    ipc_timeout: float,
) -> None:
    """Score (F04), enqueue inject, route — all off the HTTP request thread."""
    task = PendingTask(
        task_id=task_id,
        start_tick=start_tick,
        place_id=task_place_id,
        phase=task_phase,
        player_turn=task_player_turn,
        inject_status=INJECT_STATUS_RUNNING,
    )
    try:
        deltas = score_player_turn(hbm, player_text)
        apply_stat_deltas(hbm, deltas)

        if check_turn4_bad_end(hbm):
            task.inject_status = INJECT_STATUS_DONE
            save_task_runtime(
                sim_dir,
                task.to_dict(),
                session_dict=hbm.to_dict(),
                turn_outcome={
                    "status": "game_over",
                    "ending_id": "bad_reject",
                    "public_messages": list(BAD_END_PUBLIC_MESSAGES),
                    "stats_update": dict(hbm.stats),
                    "current_phase": hbm.phase,
                },
            )
            log_turn_event(
                event="player_turn_async_bad_end",
                task_id=task_id,
                phase=hbm.phase,
                player_turn=task_player_turn,
                start_tick=start_tick,
                end_tick=start_tick,
            )
            return

        events, broadcast, turn_context = build_inject_events(
            hbm, player_text, task_id=task_id
        )
        if not events:
            raise RuntimeError(
                f"no inject events for phase={hbm.phase!r} turn={hbm.player_turn}"
            )

        ipc_client = get_ipc_client(str(sim_dir))
        min_ticks = resolve_loop_min_ticks(task_phase, tick_count)

        if is_world_loop_enabled():
            send_enqueue_player_input(
                ipc_client,
                events=events,
                broadcast=broadcast,
                turn_context=turn_context,
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
            ipc_end_tick = int(loop_status.get("current_tick", start_tick))
            push_session_mirror(ipc_client, hbm, timeout=ipc_timeout)
        else:
            resp = send_inject_batch(
                ipc_client,
                events=events,
                broadcast=broadcast,
                turn_context=turn_context,
                tick_count=tick_count,
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
            log_turn_event(
                event="routing_applied",
                task_id=task_id,
                phase=hbm.phase,
                player_turn=hbm.player_turn,
                start_tick=start_tick,
                end_tick=current_tick,
                extra={"nodes": routing_info.get("nodes"), "async": True},
            )

        task.ipc_end_tick = ipc_end_tick
        task.inject_status = INJECT_STATUS_DONE
        task.inject_error = None
        task.routing_info = dict(routing_info) if routing_info else None
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
        log.exception("F11 async turn failed task_id=%s", task_id)
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


run_background_inject = run_background_turn
