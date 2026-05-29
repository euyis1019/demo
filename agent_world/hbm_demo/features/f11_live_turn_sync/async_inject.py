"""F11 background turn — delegates to F02 turn_pipeline."""

from __future__ import annotations

import logging
from pathlib import Path

from agent_world.hbm_demo.features.f01_session.logging import log_turn_event
from agent_world.hbm_demo.features.f01_session.models import HbmSession
from agent_world.hbm_demo.features.f02_player_turn.inject import (
    BAD_END_PUBLIC_MESSAGES,
)
from agent_world.hbm_demo.features.f02_player_turn.task import (
    INJECT_STATUS_DONE,
    INJECT_STATUS_FAILED,
    INJECT_STATUS_RUNNING,
    PendingTask,
)
from agent_world.hbm_demo.features.f02_player_turn.turn_pipeline import (
    apply_routing_side_effects,
    execute_inject,
    prepare_turn,
)
from agent_world.hbm_demo.features.f11_live_turn_sync.task_state import save_task_runtime

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
        prep = prepare_turn(hbm, player_text, task_id=task_id)
        if prep.bad_end:
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

        events, broadcast, turn_context = prep.events, prep.broadcast, prep.turn_context

        ipc_end_tick, _, current_tick = execute_inject(
            sim_dir=sim_dir,
            hbm=hbm,
            player_text=player_text,
            events=events,
            broadcast=broadcast,
            turn_context=turn_context,
            start_tick=start_tick,
            task_phase=task_phase,
            tick_count=tick_count,
            ipc_timeout=ipc_timeout,
        )

        routing_info = apply_routing_side_effects(
            hbm=hbm,
            sim_dir=sim_dir,
            task_id=task_id,
            start_tick=start_tick,
            current_tick=current_tick,
            tick_count=tick_count,
            ipc_timeout=ipc_timeout,
            async_mode=True,
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

        task.ipc_end_tick = ipc_end_tick
        task.inject_status = INJECT_STATUS_DONE
        task.inject_error = None
        task.routing_info = routing_info or None
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
