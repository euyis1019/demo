"""F05 RoutingWatcher — scan DB on tick advance during F14 poll (dev_logs/31 Phase 2/4)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

from agent_world.hbm_demo.features.f01_session.lifecycle import save_session
from agent_world.hbm_demo.features.f01_session.models import HbmSession
from agent_world.hbm_demo.features.f01_session.paths import get_name_map
from agent_world.hbm_demo.features.f05_story_routing import interpreter_routing
from agent_world.hbm_demo.features.f06_read_model.world_db import make_readonly_db
from agent_world.hbm_demo.features.f07_agent_control.config import is_world_loop_enabled
from agent_world.hbm_demo.features.f13_world_loop_control import pause_world_loop
from agent_world.hbm_demo.http.ipc_helper import get_ipc_client, push_session_mirror
from agent_world.hbm_demo.shared.env_status import read_env_status
from agent_world.hbm_demo.shared.settings import DEFAULT_IPC_TIMEOUT

log = logging.getLogger("agent_world.hbm_demo.f05")

ROUTING_WATCHER_KEY = "hbm_routing_watcher"


def _mark_session_modified(flask_session: Any) -> None:
    if hasattr(flask_session, "modified"):
        flask_session.modified = True


def _watcher_state(flask_session: Any) -> Dict[str, Any]:
    return flask_session.setdefault(ROUTING_WATCHER_KEY, {})


def consume_routing_world_events(
    flask_session: Any,
    *,
    since_tick: int,
    t_now: int,
) -> List[Dict[str, Any]]:
    """Return routing world_events in (since_tick, t_now] and prune older entries."""
    state = _watcher_state(flask_session)
    pending = list(state.get("pending_world_events") or [])
    since_t = int(since_tick)
    end_t = int(t_now)
    selected: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    for event in pending:
        at_tick = int(event.get("at_tick", 0))
        if since_t < at_tick <= end_t:
            event_id = str(event.get("id") or "")
            if event_id and event_id in seen_ids:
                continue
            if event_id:
                seen_ids.add(event_id)
            selected.append(event)
    state["pending_world_events"] = [
        event
        for event in pending
        if int(event.get("at_tick", 0)) > since_t
    ]
    _mark_session_modified(flask_session)
    return selected


def consume_game_over_payload(flask_session: Any) -> Dict[str, Any] | None:
    """Return pending game_over payload once for F14 delta."""
    state = _watcher_state(flask_session)
    payload = state.pop("pending_game_over", None)
    if payload:
        _mark_session_modified(flask_session)
    return dict(payload) if isinstance(payload, dict) else None


def scan_routing_if_needed(
    flask_session: Any,
    hbm: HbmSession,
    *,
    sim_id: str,
    sim_dir: Path,
    current_tick: int,
    ipc_timeout: float = DEFAULT_IPC_TIMEOUT,
) -> Dict[str, Any]:
    """Apply routing side effects when env tick advances (world loop mode only)."""
    if not is_world_loop_enabled():
        return {}

    env = read_env_status(sim_dir) or {}
    if str(env.get("loop_state") or "") == "paused" and not hbm.ending_id:
        return dict(_watcher_state(flask_session).get("last_routing_info") or {})

    if hbm.ending_id:
        return dict(_watcher_state(flask_session).get("last_routing_info") or {})

    state = _watcher_state(flask_session)
    last_scan = int(state.get("last_scan_tick", -1))
    tick = int(current_tick)
    if tick <= last_scan:
        return dict(state.get("last_routing_info") or {})

    ipc_client = get_ipc_client(str(sim_dir))
    db = make_readonly_db(sim_dir)
    task_id = f"route_{tick}"

    # ===== 导演驱动路由（LLM 推进世界，无任何硬规则）=====
    interp = interpreter_routing.get_interpreter(sim_id)
    if last_scan < 0:  # 开局首扫：把初始节点的场景(玩家+在场NPC)聚到初始地点
        interpreter_routing.setup_scene_for_node(
            interp, hbm, ipc_client=ipc_client, ipc_timeout=ipc_timeout
        )
    result = interpreter_routing.route_story(
        interp, hbm, ipc_client=ipc_client, db=db, task_id=task_id,
        current_tick=tick, ipc_timeout=ipc_timeout, name_map=get_name_map(),
    )
    if result.get("ending"):
        ending = str(result["ending"])
        end_node = interp.graph.endings.get(ending)
        kind = end_node.kind if end_node else "neutral"
        hbm.ending_id = ending
        save_session(flask_session, hbm, sim_id)
        try:
            pause_world_loop(sim_dir=sim_dir)
        except Exception as exc:  # noqa: BLE001
            log.warning("ending pause_world_loop failed: %s", exc)
        state["pending_game_over"] = {
            "status": "game_over" if kind == "bad" else "completed",
            "ending_id": ending,
            "ending_summary": (end_node.summary if end_node else "") or "",
            "ending_kind": kind,
            "stats_update": dict(hbm.stats),
            "current_phase": hbm.phase,
            "at_tick": tick,
        }
        state["last_scan_tick"] = tick
        state["last_routing_info"] = {"ending": ending}
        log.info("story ending %s (%s) at tick=%s", ending, kind, tick)
        return dict(state["last_routing_info"])
    if result.get("nodes"):
        save_session(flask_session, hbm, sim_id)
        push_session_mirror(ipc_client, hbm, timeout=ipc_timeout)
        pending = state.setdefault("pending_world_events", [])
        known_ids = {str(e.get("id") or "") for e in pending}
        for event in result.get("events") or []:
            eid = str(event.get("id") or "")
            if eid and eid in known_ids:
                continue
            pending.append(event)
            if eid:
                known_ids.add(eid)
        log.info("story watcher advanced nodes=%s at tick=%s", result.get("nodes"), tick)
    elif "tension" in result:
        # 导演本拍只更新了张力(stay)——持久化，让张力跨请求/跨拍存活，驱动张力弧。
        save_session(flask_session, hbm, sim_id)
    state["last_scan_tick"] = tick
    state["last_routing_info"] = {"nodes": result.get("nodes") or []}
    _mark_session_modified(flask_session)
    return dict(state["last_routing_info"])


__all__ = [
    "ROUTING_WATCHER_KEY",
    "consume_game_over_payload",
    "consume_routing_world_events",
    "scan_routing_if_needed",
]
