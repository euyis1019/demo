"""F12 world delta builder — merged into F11 action-result polls."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent_world.drama_demo.features.f02_player_turn.task import PendingTask
from agent_world.drama_demo.shared.messages import format_messages
from agent_world.drama_demo.features.f06_read_model.world_db import ReadOnlyWorldDB
from agent_world.drama_demo.features.f12_world_sync.constants import (
    agent_roster,
    room_places,
)
from agent_world.drama_demo.features.f12_world_sync.emotion_tag import tag_message_emotions
from agent_world.drama_demo.features.f12_world_sync.formatter import (
    format_agent_locations,
    format_broadcast_world_events,
    format_f2f_history_with_ids,
    format_group_social_events,
    format_location_changes,
    format_state_changes,
    legacy_group_from_agent_messages,
    legacy_observer_from_agent_messages,
    legacy_public_messages_from_room_f2f,
)
from agent_world.drama_demo.features.f15_prompt_trace.refs import (
    build_link_map,
    enrich_world_delta,
)


def _attach_trace_refs(
    delta: Dict[str, Any],
    db: ReadOnlyWorldDB,
    since_t: int,
    t_now: int,
) -> Dict[str, Any]:
    links = db.fetch_trace_links_since(since_t, t_now)
    link_map = build_link_map(links) if links else {}
    return enrich_world_delta(delta, link_map)


def _default_player_place() -> str:
    try:
        from agent_world.drama_demo.shared import story_config
        return story_config.player_start_place()
    except Exception:  # noqa: BLE001
        return ""


def _player_place_id(task: PendingTask) -> str:
    return str(task.place_id or _default_player_place())


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

    room_f2f: Dict[str, List[Dict[str, Any]]] = {}
    f2f_by_place = db.fetch_f2f_by_places(
        since_t, t_now, list(room_places())
    )
    for place_id, history in f2f_by_place.items():
        room_f2f[place_id] = format_f2f_history_with_ids(history, name_map)
        for msg in room_f2f[place_id]:
            msg["place_id"] = place_id
    # 后端整合：本窗口所有当面台词统一过一遍 f05 情绪判断 agent（LLM，按句缓存），
    # 把判出的 emotion 写进每条消息——前端立绘据此随台词切表情（替代旧关键词分类）。
    tag_message_emotions([m for msgs in room_f2f.values() for m in msgs])

    agent_messages: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    # 含玩家(0)：让发往玩家的私信/群消息进 agent_messages["0"]，供前端玩家收件箱展示（体检 P1/B3）。
    for agent_id in (0, *agent_roster()):
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

    agent_locations = format_agent_locations(db.fetch_all_agent_locations())

    public_messages = legacy_public_messages_from_room_f2f(
        room_f2f, player_place
    )
    observer_messages = legacy_observer_from_agent_messages(agent_messages)
    group_messages = legacy_group_from_agent_messages(agent_messages)

    return _attach_trace_refs(
        {
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
        },
        db,
        since_t,
        t_now,
    )


def build_session_world_delta(
    *,
    since_tick: int,
    t_now: int,
    player_place_id: str,
    db: ReadOnlyWorldDB,
    name_map: Dict[int, str],
    extra_world_events: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Session-scoped incremental delta (F14) — no PendingTask boundary."""
    since_t = max(0, int(since_tick))
    t_end = max(int(t_now), since_t)
    player_place = str(player_place_id or _default_player_place())

    room_f2f: Dict[str, List[Dict[str, Any]]] = {
        place_id: [] for place_id in room_places()
    }
    f2f_by_place = db.fetch_f2f_by_places(
        since_t, t_end, list(room_places())
    )
    for place_id, history in f2f_by_place.items():
        room_f2f[place_id] = format_f2f_history_with_ids(history, name_map)
        for msg in room_f2f[place_id]:
            msg["place_id"] = place_id
    # 后端整合：本窗口所有当面台词统一过一遍 f05 情绪判断 agent（LLM，按句缓存），把 emotion 写进每条
    # 消息——/world-delta 走的就是本函数，前端立绘据 message.emotion 切表情（替代旧关键词分类）。
    tag_message_emotions([m for msgs in room_f2f.values() for m in msgs])

    agent_messages: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    # 含玩家(0)：发往玩家的私信/群消息进 agent_messages["0"]，供玩家收件箱展示（体检 P1/B3）。
    for agent_id in (0, *agent_roster()):
        rdc_rows = db.fetch_rdc_for_agent(agent_id, since_t, t_end)
        grp_rows = db.fetch_grp_for_agent(agent_id, since_t, t_end)
        if not rdc_rows and not grp_rows:
            continue
        agent_messages[str(agent_id)] = {
            "rdc": format_messages(rdc_rows, name_map),
            "grp": format_messages(grp_rows, name_map),
        }

    location_changes = format_location_changes(
        db.fetch_location_logs_since(since_t, t_end)
    )
    social_events = format_group_social_events(
        db.fetch_group_events_since(since_t, t_end)
    )
    state_changes = format_state_changes(
        db.fetch_state_logs_since(since_t, t_end)
    )

    world_events: List[Dict[str, Any]] = []
    world_events.extend(
        format_broadcast_world_events(
            db.fetch_broadcasts_since(since_t, t_end), name_map
        )
    )
    if extra_world_events:
        world_events.extend(extra_world_events)

    agent_locations = format_agent_locations(db.fetch_all_agent_locations())

    public_messages = legacy_public_messages_from_room_f2f(room_f2f, player_place)
    observer_messages = legacy_observer_from_agent_messages(agent_messages)
    group_messages = legacy_group_from_agent_messages(agent_messages)

    return _attach_trace_refs(
        {
            "through_tick": t_end,
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
        },
        db,
        since_t,
        t_end,
    )


def empty_delta(through_tick: int, *, player_place_id: str = "") -> Dict[str, Any]:
    room_f2f = {place_id: [] for place_id in room_places()}
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
        "inject_status": task.inject_status,
        "player_place_id": delta["player_place_id"],
        **delta,
    }
