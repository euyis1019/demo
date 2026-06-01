"""F02 API 1 — player turn orchestration."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from agent_world.drama_demo.features.f01_session.constants import DEFAULT_SIM_ID
from agent_world.drama_demo.features.f01_session.lifecycle import (
    get_or_create_session,
    save_session,
)
from agent_world.drama_demo.features.f01_session.logging import log_turn_event
from agent_world.drama_demo.features.f01_session.models import DramaSession
from agent_world.drama_demo.features.f01_session.paths import get_sim_dir
from agent_world.drama_demo.features.f02_player_turn.inject import (
    BAD_END_PUBLIC_MESSAGES,
    build_inject_events,
)
from agent_world.drama_demo.features.f02_player_turn.task import (
    INJECT_STATUS_RUNNING,
    PendingTask,
    save_task,
)
from agent_world.drama_demo.features.f05_story_routing import routing
from agent_world.drama_demo.features.f02_player_turn.turn_pipeline import (
    prepare_turn,
)
from agent_world.drama_demo.features.f06_read_model.world_db import make_readonly_db
from agent_world.drama_demo.features.f07_agent_control.config import is_world_loop_enabled
from agent_world.drama_demo.features.f17_virtual_player.player_f2f import (
    build_player_f2f_payload,
)
from agent_world.drama_demo.features.f11_live_turn_sync.handler import start_background_turn
from agent_world.drama_demo.features.f11_live_turn_sync.task_state import sync_runtime_state
from agent_world.drama_demo.http.ipc_helper import (
    get_ipc_client,
    push_turn_context_mirror,
    resolve_loop_min_ticks,
    send_enqueue_player_input,
    send_inject_batch,
    wait_for_loop_window,
)
from agent_world.drama_demo.shared.env_status import is_runner_ready, read_env_status
from agent_world.drama_demo.shared.errors import RunnerNotReadyError
from agent_world.drama_demo.shared.settings import DEFAULT_IPC_TIMEOUT

log = logging.getLogger("agent_world.drama_demo.game_service")


def _pause_loop_after_terminal(*, sim: Path) -> None:
    """Freeze resident loop after game_over / Turn 25 ending (Phase 2)."""
    if not is_world_loop_enabled():
        return
    try:
        from agent_world.drama_demo.features.f13_world_loop_control.handler import (
            pause_world_loop,
        )

        pause_world_loop(sim_dir=sim)
    except Exception:  # noqa: BLE001
        log.exception("failed to pause world loop after terminal turn")


def run_debug_inject(
    session: DramaSession,
    player_text: str,
    *,
    sim_dir: Path | None = None,
    tick_count: int = 6,
    timeout: float = 600.0,
) -> Dict[str, Any]:
    sim = sim_dir or get_sim_dir()
    if not is_runner_ready(sim):
        raise RunnerNotReadyError(
            "Runner not ready: start run_drama first and wait for env_status.status=running"
        )
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    events, _broadcast, turn_context = build_inject_events(
        session, player_text, task_id=task_id
    )
    # bert 世界：玩家可对着没有 NPC 的房间说话——台词仍会记进 f2f（下方 player_f2f），供 Bert 导演读判触发；
    # 命中后导演再把 target NPC 聚到玩家面前。故世界循环模式下「当前没有同处 NPC」不再硬失败。
    # 非世界循环模式（同步注入批）没有 player_f2f 独立落库通道，无在场 NPC 仍按旧约定报错。
    if not events and not is_world_loop_enabled():
        raise RuntimeError(f"no agents at place_id={session.place_id!r}")

    ipc_client = get_ipc_client(str(sim))
    env_before = read_env_status(sim) or {}
    start_tick = int(env_before.get("current_tick", 0))
    player_f2f = build_player_f2f_payload(session, player_text)
    if is_world_loop_enabled():
        send_enqueue_player_input(
            ipc_client,
            events=events,
            turn_context=turn_context,
            player_f2f=player_f2f,
            timeout=timeout,
        )
        push_turn_context_mirror(
            ipc_client,
            turn_context,
            stats=dict(session.stats),
            timeout=timeout,
        )
        session.player_turn += 1
        loop_status = wait_for_loop_window(
            ipc_client,
            start_tick=start_tick,
            min_ticks=resolve_loop_min_ticks(tick_count),
            timeout=timeout,
        )
        resp_result = dict(loop_status)
    else:
        resp = send_inject_batch(
            ipc_client,
            events=events,
            tick_count=tick_count,
            turn_context=turn_context,
            player_f2f=player_f2f,
            timeout=timeout,
        )
        session.player_turn += 1
        resp_result = dict(resp.result or {})

    return {
        "ipc": resp_result,
        "events_count": len(events),
        "agent_ids": [ev["effect"]["agent_id"] for ev in events],
    }


def _handle_v2_player_turn(
    flask_session: Any,
    hbm: DramaSession,
    *,
    sim: Path,
    sim_id: str,
    player_text: str,
    task_id: str,
    ipc_timeout: float,
) -> Dict[str, Any]:
    """Phase 2 — score, enqueue, mirror; F14 poll captures world activity."""
    prep = prepare_turn(hbm, player_text, task_id=task_id)
    if prep.bad_end:
        save_session(flask_session, hbm, sim_id)
        _pause_loop_after_terminal(sim=sim)
        return {
            "status": "game_over",
            "ending_id": "bad_reject",
            "public_messages": list(BAD_END_PUBLIC_MESSAGES),
            "stats_update": dict(hbm.stats),
        }

    events, broadcast, turn_context = prep.events, prep.broadcast, prep.turn_context

    ipc_client = get_ipc_client(str(sim))
    player_f2f = build_player_f2f_payload(hbm, player_text)
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
    save_session(flask_session, hbm, sim_id)

    log_turn_event(
        event="player_turn_accepted",
        task_id=task_id,
        player_turn=hbm.player_turn - 1,
        start_tick=int((read_env_status(sim) or {}).get("current_tick", 0)),
        end_tick=int((read_env_status(sim) or {}).get("current_tick", 0)),
        extra={"accepted": True},
    )

    return {
        "accepted": True,
        "stats_update": dict(hbm.stats),
        "player_turn": hbm.player_turn,
    }


def handle_player_turn(
    flask_session: Any,
    *,
    sim_id: str,
    player_text: str,
    request_place_id: Optional[str] = None,
    request_player_turn: Optional[int] = None,
    sim_dir: Path | None = None,
    tick_count: int = 6,
    ipc_timeout: float = DEFAULT_IPC_TIMEOUT,
) -> Dict[str, Any]:
    sim = sim_dir or get_sim_dir()
    if not is_runner_ready(sim):
        raise RunnerNotReadyError(
            "Runner not ready: start run_drama first and wait for env_status.status=running"
        )

    sync_runtime_state(flask_session, sim_id, sim_dir=sim)

    hbm = get_or_create_session(flask_session, sim_id, sim_dir=sim)
    from agent_world.drama_demo.features.f07_agent_control.config import (
        resolve_inject_tick_count,
    )

    tick_count = resolve_inject_tick_count(tick_count)
    if request_place_id and request_place_id != hbm.place_id:
        log.debug(
            "ignoring request place_id=%s; session authority=%s",
            request_place_id,
            hbm.place_id,
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
    # 结局何时到达完全由 LLM 导演按对话判定，回合数不再封顶（旧「第 25 回合强制结局」硬规则已移除）。

    if is_world_loop_enabled():
        return _handle_v2_player_turn(
            flask_session,
            hbm,
            sim=sim,
            sim_id=sim_id,
            player_text=player_text,
            task_id=task_id,
            ipc_timeout=ipc_timeout,
        )

    # Legacy F11 async path when world loop disabled.
    save_session(flask_session, hbm, sim_id)

    task_place_id = hbm.place_id
    task_player_turn = hbm.player_turn

    task = PendingTask(
        task_id=task_id,
        start_tick=start_tick,
        place_id=task_place_id,
        player_turn=task_player_turn,
        inject_status=INJECT_STATUS_RUNNING,
    )
    save_task(flask_session, task, sim_id)

    start_background_turn(
        sim_dir=sim,
        sim_id=sim_id,
        task_id=task_id,
        hbm=hbm,
        player_text=player_text,
        start_tick=start_tick,
        task_place_id=task_place_id,
        task_player_turn=task_player_turn,
        tick_count=tick_count,
        ipc_timeout=ipc_timeout,
    )

    log_turn_event(
        event="player_turn_async_started",
        task_id=task_id,
        player_turn=task_player_turn,
        start_tick=start_tick,
        end_tick=start_tick,
    )

    return {
        "task_id": task_id,
        "status": "processing",
        "stats_update": dict(hbm.stats),
        "start_tick": start_tick,
        "inject_status": INJECT_STATUS_RUNNING,
    }
