"""F12 world delta builder — merged into F11 action-result polls."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent_world.hbm_demo.features.f02_player_turn.task import PendingTask
from agent_world.hbm_demo.features.f03_action_result.completion import format_messages
from agent_world.hbm_demo.features.f06_read_model.world_db import ReadOnlyWorldDB
from agent_world.hbm_demo.features.f12_world_sync.constants import (
    HBM_AGENT_IDS,
    HBM_ROOM_PLACES,
)
from agent_world.hbm_demo.features.f12_world_sync.formatter import (
    format_agent_locations,
    format_broadcast_world_events,
    format_f2f_history_with_ids,
    format_group_social_events,
    format_location_changes,
    format_routing_world_events,
    format_state_changes,
    legacy_group_from_agent_messages,
    legacy_observer_from_agent_messages,
    legacy_public_messages_from_room_f2f,
)


def _player_place_id(task: PendingTask) -> str:
    return str(task.place_id or "nvidia_reception")


def build_world_delta(
    task: PendingTask,
    since_tick: int,
    effective_tick: int,
    db: ReadOnlyWorldDB,
    name_map: Dict[int, str],
    *,
    routing_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Incremental world sync payload for one poll window."""
    since_t = max(int(since_tick), int(task.start_tick))
    t_now = max(int(effective_tick), since_t)
    player_place = _player_place_id(task)
    routing = routing_info if routing_info is not None else task.routing_info

    room_f2f: Dict[str, List[Dict[str, Any]]] = {}
    f2f_by_place = db.fetch_f2f_by_places(
        since_t, t_now, list(HBM_ROOM_PLACES)
    )
    for place_id, history in f2f_by_place.items():
        room_f2f[place_id] = format_f2f_history_with_ids(history, name_map)

    agent_messages: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for agent_id in HBM_AGENT_IDS:
        rdc_rows = db.fetch_rdc_for_agent(agent_id, since_t, t_now)
        grp_rows = db.fetch_grp_for_agent(agent_id, since_t, t_now)
        if not rdc_rows and not grp_rows:
            continue
        agent_messages[str(agent_id)] = {
            "rdc": format_messages(rdc_rows, name_map),
            "grp": format_messages(grp_rows, name_map),
        }

    location_changes = format_location_changes(
        db.fetch_location_logs_since(since_t, t_now)
    )
    social_events = format_group_social_events(
        db.fetch_group_events_since(since_t, t_now)
    )
    state_changes = format_state_changes(
        db.fetch_state_logs_since(since_t, t_now)
    )

    world_events: List[Dict[str, Any]] = []
    world_events.extend(
        format_broadcast_world_events(
            db.fetch_broadcasts_since(since_t, t_now), name_map
        )
    )
    if routing and task.ipc_end_tick is not None:
        ipc_end = int(task.ipc_end_tick)
        if since_t < ipc_end <= t_now:
            world_events.extend(
                format_routing_world_events(
                    routing,
                    at_tick=ipc_end,
                    task_id=str(task.task_id),
                )
            )

    agent_locations = format_agent_locations(db.fetch_all_agent_locations())

    public_messages = legacy_public_messages_from_room_f2f(
        room_f2f, player_place
    )
    observer_messages = legacy_observer_from_agent_messages(agent_messages)
    group_messages = legacy_group_from_agent_messages(agent_messages)

    return {
        "through_tick": t_now,
        "player_place_id": player_place,
        "room_f2f": room_f2f,
        "agent_messages": agent_messages,
        "location_changes": location_changes,
        "social_events": social_events,
        "state_changes": state_changes,
        "world_events": world_events,
        "agent_locations": agent_locations,
        "public_messages": public_messages,
        "observer_messages": observer_messages,
        "group_messages": group_messages,
    }


def empty_delta(through_tick: int, *, player_place_id: str = "") -> Dict[str, Any]:
    room_f2f = {place_id: [] for place_id in HBM_ROOM_PLACES}
    return {
        "through_tick": int(through_tick),
        "player_place_id": player_place_id,
        "room_f2f": room_f2f,
        "agent_messages": {},
        "location_changes": [],
        "social_events": [],
        "state_changes": [],
        "world_events": [],
        "agent_locations": {},
        "public_messages": [],
        "observer_messages": [],
        "group_messages": [],
    }


def build_completed_payload(
    task: PendingTask,
    effective_tick: int,
    db: ReadOnlyWorldDB,
    name_map: Dict[int, str],
    *,
    stats_update: Dict[str, Any],
    current_phase: str,
    routing_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Full-turn payload for action-result completed status."""
    delta = build_world_delta(
        task,
        since_tick=int(task.start_tick),
        effective_tick=int(effective_tick),
        db=db,
        name_map=name_map,
        routing_info=routing_info,
    )
    return {
        "status": "completed",
        "task_id": task.task_id,
        "end_tick": int(effective_tick),
        "stats_update": dict(stats_update),
        "current_phase": current_phase,
        "inject_status": task.inject_status,
        "player_place_id": delta["player_place_id"],
        **delta,
    }
