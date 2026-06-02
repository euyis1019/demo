"""F05 RoutingWatcher — scan DB on tick advance during F14 poll (dev_logs/31 Phase 2/4)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

from agent_world.drama_demo.features.f01_session.lifecycle import save_session
from agent_world.drama_demo.features.f01_session.models import DramaSession
from agent_world.drama_demo.features.f01_session.paths import get_name_map
from agent_world.drama_demo.features.f05_story_routing import interpreter_routing
from agent_world.drama_demo.features.f06_read_model.world_db import make_readonly_db
from agent_world.drama_demo.features.f07_agent_control.config import is_world_loop_enabled
from agent_world.drama_demo.features.f13_world_loop_control import pause_world_loop
from agent_world.drama_demo.http.ipc_helper import get_ipc_client, push_session_mirror
from agent_world.drama_demo.shared.env_status import read_env_status
from agent_world.drama_demo.shared.settings import DEFAULT_IPC_TIMEOUT

log = logging.getLogger("agent_world.drama_demo.f05")

ROUTING_WATCHER_KEY = "drama_routing_watcher"


def _mark_session_modified(flask_session: Any) -> None:
    if hasattr(flask_session, "modified"):
        flask_session.modified = True


def _save_keep_player_place(flask_session: Any, hbm: Any, sim_id: str, db: Any) -> None:
    """保存 hbm 前，用引擎世界 DB 里玩家(agent 0)的当前地点对齐 hbm.place_id 再存。

    routing 在 /world-delta 入口拿到的是「请求开始那一刻」的旧 hbm 快照，中间要等数秒导演 LLM；这期间玩家
    若点了移动(经 IPC 已改引擎 DB 的位置)，直接存这份旧 hbm 会把玩家**弹回旧地点**（偶发"传送回原地"）。
    引擎世界 DB 是玩家位置的权威且最新来源，据此对齐后再存即可杜绝弹回；place 的唯一权威写入仍是 move。"""
    try:
        loc = (db.fetch_all_agent_locations() or {}).get(0) or {}
        p = str(loc.get("place_id") or "")
        if p:
            hbm.place_id = p
    except Exception:  # noqa: BLE001
        pass
    save_session(flask_session, hbm, sim_id)


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
    hbm: DramaSession,
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

    # ===== bert 驱动路由（LLM 判触发→注入反应，无任何硬规则）=====
    interp = interpreter_routing.get_interpreter(sim_id)
    if last_scan < 0:  # 开局首扫（bert 化后 setup_scene 为空操作：NPC 由播种各就各位，世界自然运行）
        interpreter_routing.setup_scene_for_node(
            interp, hbm, ipc_client=ipc_client, ipc_timeout=ipc_timeout
        )
    result = interpreter_routing.route_story(
        interp, hbm, ipc_client=ipc_client, db=db, task_id=task_id,
        current_tick=tick, ipc_timeout=ipc_timeout, name_map=get_name_map(),
    )
    if result.get("ending"):
        ending = str(result["ending"])
        # 结局 bert：kind/summary 由命中的「结局 bert」经 route_story 写到 hbm（story_graph 退役，
        # 无 graph.endings 回退）；kind 缺省兜底 neutral。
        kind = hbm.ending_kind or "neutral"
        summary = hbm.ending_summary or ""
        hbm.ending_id = ending
        _save_keep_player_place(flask_session, hbm, sim_id, db)
        try:
            pause_world_loop(sim_dir=sim_dir)
        except Exception as exc:  # noqa: BLE001
            log.warning("ending pause_world_loop failed: %s", exc)
        state["pending_game_over"] = {
            "status": "game_over" if kind == "bad" else "completed",
            "ending_id": ending,
            "ending_summary": summary,
            "ending_kind": kind,
            "stats_update": dict(hbm.stats),
            "at_tick": tick,
        }
        state["last_scan_tick"] = tick
        state["last_routing_info"] = {"ending": ending}
        log.info("bert 结局 %s (%s) at tick=%s", ending, kind, tick)
        return dict(state["last_routing_info"])
    if result.get("nodes"):
        # 某条 bert 触发了：持久化 hbm（fired_berts / bert_reactions 等需跨请求存活），并推回 Runner 镜像。
        _save_keep_player_place(flask_session, hbm, sim_id, db)
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
        log.info("bert 触发 %s at tick=%s", result.get("nodes"), tick)
    else:
        # 没触发也要落盘：route_story 可能已更新 hbm.last_judged_player_tick（「只判新发言」去重锚点）。
        # 不落盘的话每次 /world-delta 轮询都 load 出旧值，同一句玩家发言会每拍重复送 LLM 判，既烧 token 又抖触发时机。
        _save_keep_player_place(flask_session, hbm, sim_id, db)
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
