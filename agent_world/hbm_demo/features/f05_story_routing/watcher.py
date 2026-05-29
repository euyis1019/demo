"""F05 RoutingWatcher — scan DB on tick advance during F14 poll (dev_logs/31 Phase 2/4)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

from agent_world.hbm_demo.features.f01_session.lifecycle import save_session
from agent_world.hbm_demo.features.f01_session.models import HbmSession
from agent_world.hbm_demo.features.f01_session.paths import get_name_map
from agent_world.hbm_demo.features.f05_story_routing import routing
from agent_world.hbm_demo.features.f05_story_routing.agent_signals import (
    detect_bad_end,
    detect_phase4_offer_ending,
    fetch_bad_end_public_messages,
    phase4_deal_transcript,
)
from agent_world.hbm_demo.features.f05_story_routing.routing_config import is_agent_driven
from agent_world.hbm_demo.features.f06_read_model.world_db import make_readonly_db
from agent_world.hbm_demo.features.f07_agent_control.config import is_world_loop_enabled
from agent_world.hbm_demo.shared.routing_events import format_routing_world_events
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

    if is_agent_driven() and detect_bad_end(hbm, db, t_now=tick):
        name_map = get_name_map()
        public_messages = fetch_bad_end_public_messages(
            db, t_now=tick, name_map=name_map, since_t=int(hbm.start_tick or 0)
        )
        hbm.ending_id = "bad_reject"
        save_session(flask_session, hbm, sim_id)
        try:
            pause_world_loop(sim_dir=sim_dir)
        except Exception as exc:  # noqa: BLE001
            log.warning("bad_end pause_world_loop failed: %s", exc)
        state["pending_game_over"] = {
            "status": "game_over",
            "ending_id": "bad_reject",
            "public_messages": public_messages,
            "stats_update": dict(hbm.stats),
            "current_phase": hbm.phase,
            "at_tick": tick,
        }
        state["last_scan_tick"] = tick
        state["last_routing_info"] = {"bad_end": True}
        log.info("routing watcher bad_end at tick=%s", tick)
        return dict(state["last_routing_info"])

    # Phase 4 early-end: settle the finale the moment the deal concludes instead
    # of idling to the Turn-25 gate. Two paths: (1) precise story_advance offer_*
    # signal; (2) when Jensen only *talks* the deal (he rarely calls the tool),
    # a cheap broad keyword gate on NEW Jensen F2F triggers one LLM check that
    # robustly decides "concluded? join/seed?" — beating brittle keyword lists.
    if hbm.phase == "Phase 4":
        offer_since = max(0, int(getattr(hbm, "start_tick", 0) or 0))
        early_ending = detect_phase4_offer_ending(db, since_t=offer_since, t_now=tick)
        if not early_ending:
            transcript = phase4_deal_transcript(
                db, gate_since=last_scan, context_since=offer_since, t_now=tick
            )
            if transcript:
                early_ending = routing.classify_phase4_conclusion(transcript)
        if early_ending:
            hbm.ending_id = early_ending
            save_session(flask_session, hbm, sim_id)
            try:
                pause_world_loop(sim_dir=sim_dir)
            except Exception as exc:  # noqa: BLE001
                log.warning("phase4 early-end pause_world_loop failed: %s", exc)
            state["pending_game_over"] = {
                "status": "completed",
                "ending_id": early_ending,
                "stats_update": dict(hbm.stats),
                "current_phase": hbm.phase,
                "at_tick": tick,
            }
            state["last_scan_tick"] = tick
            state["last_routing_info"] = {"phase4_offer_end": early_ending}
            log.info(
                "routing watcher phase4 early-end %s at tick=%s", early_ending, tick
            )
            return dict(state["last_routing_info"])

    routing_info = routing.apply_routing(
        hbm,
        ipc_client=ipc_client,
        db=db,
        task_id=task_id,
        current_tick=tick,
        tick_count=1,
        ipc_timeout=ipc_timeout,
    )

    if routing_info.get("nodes"):
        save_session(flask_session, hbm, sim_id)
        push_session_mirror(ipc_client, hbm, timeout=ipc_timeout)
        applied_nodes = set(state.get("applied_routing_nodes") or [])
        new_nodes = [n for n in routing_info.get("nodes") or [] if n not in applied_nodes]
        if new_nodes:
            applied_nodes.update(new_nodes)
            state["applied_routing_nodes"] = sorted(applied_nodes)
            events = format_routing_world_events(
                {**routing_info, "nodes": new_nodes},
                at_tick=tick,
                task_id=task_id,
            )
            pending = state.setdefault("pending_world_events", [])
            known_ids = {str(e.get("id") or "") for e in pending}
            for event in events:
                event_id = str(event.get("id") or "")
                if event_id and event_id in known_ids:
                    continue
                pending.append(event)
                if event_id:
                    known_ids.add(event_id)
        log.info(
            "routing watcher applied nodes=%s at tick=%s",
            routing_info.get("nodes"),
            tick,
        )

    state["last_scan_tick"] = tick
    state["last_routing_info"] = dict(routing_info) if routing_info else {}
    _mark_session_modified(flask_session)
    return dict(state["last_routing_info"])


__all__ = [
    "ROUTING_WATCHER_KEY",
    "consume_game_over_payload",
    "consume_routing_world_events",
    "scan_routing_if_needed",
]
