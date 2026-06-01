"""Shared F02/F11 inject + routing pipeline (dev_logs/38 R4)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent_world.drama_demo.features.f01_session.models import DramaSession
from agent_world.drama_demo.features.f02_player_turn.inject import (
    build_inject_events,
    check_turn4_bad_end,
)
from agent_world.drama_demo.features.f04_stats.deltas import apply_stat_deltas
from agent_world.drama_demo.features.f04_stats.scoring import score_player_turn
from agent_world.drama_demo.features.f05_story_routing import routing
from agent_world.drama_demo.features.f06_read_model.world_db import make_readonly_db
from agent_world.drama_demo.features.f17_virtual_player.player_f2f import (
    build_player_f2f_payload,
)
from agent_world.drama_demo.features.f07_agent_control.config import is_world_loop_enabled
from agent_world.drama_demo.http.ipc_helper import (
    get_ipc_client,
    push_session_mirror,
    push_turn_context_mirror,
    resolve_loop_min_ticks,
    send_enqueue_player_input,
    send_inject_batch,
    wait_for_loop_window,
)
from agent_world.drama_demo.shared.env_status import read_env_status

log = logging.getLogger("agent_world.drama_demo.turn_pipeline")


@dataclass
class TurnPrep:
    """Outcome of the shared turn-prep prefix."""

    bad_end: bool
    events: List[Dict[str, Any]]
    broadcast: Optional[Dict[str, Any]]
    turn_context: Optional[Dict[str, Any]]


def prepare_turn(hbm: DramaSession, player_text: str, *, task_id: str) -> TurnPrep:
    """Shared turn-prep for the sync (F02) and async (F11) paths.

    Runs F04 score + apply, the Turn-4 bad-end gate, then builds inject events
    (with the no-events guard). On the bad-end gate returns ``bad_end=True`` with
    empty events — the caller owns the divergent side effect (HTTP game_over vs
    F11 task persist). De-duplicates the prep prefix previously copied across
    handle_player_turn / _handle_v2_player_turn / run_background_turn.
    """
    deltas = score_player_turn(hbm, player_text)
    apply_stat_deltas(hbm, deltas)
    if check_turn4_bad_end(hbm):
        return TurnPrep(bad_end=True, events=[], broadcast=None, turn_context=None)
    events, broadcast, turn_context = build_inject_events(
        hbm, player_text, task_id=task_id
    )
    if not events:
        raise RuntimeError(
            f"no inject events for phase={hbm.phase!r} turn={hbm.player_turn}"
        )
    return TurnPrep(
        bad_end=False, events=events, broadcast=broadcast, turn_context=turn_context
    )


def execute_inject(
    *,
    sim_dir: Path,
    hbm: DramaSession,
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
    hbm: DramaSession,
    sim_dir: Path,
    task_id: str,
    start_tick: int,
    current_tick: int,
    tick_count: int,
    ipc_timeout: float,
    async_mode: bool = False,
) -> Dict[str, Any]:
    """剧情推进已由 watcher 里的 LLM 导演(f05/director)统一负责——玩家这一拍只做注入，
    不再在此做任何同步路由判定。保留为薄壳以兼容调用方签名。"""
    return {}
