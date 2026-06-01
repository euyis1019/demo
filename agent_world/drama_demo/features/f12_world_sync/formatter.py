"""F12 message and event formatting."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from agent_world.drama_demo.shared.messages import (
    format_f2f_public_messages,
    format_messages,
)
from agent_world.drama_demo.features.f06_read_model.world_db import sender_display_name
from agent_world.drama_demo.shared.routing_events import (
    format_routing_world_events,
)

_GROUP_EVENT_KIND = {
    "join": "group_join",
    "leave": "group_leave",
    "kick": "group_kick",
}


def format_f2f_history_with_ids(
    history: List[tuple],
    name_map: Dict[int, str],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for at_t, sender_id, _mid, content in history:
        if at_t <= 0:
            continue
        out.append(
            {
                "sender": sender_display_name(sender_id, name_map),
                "content": str(content),
                "type": "F2F",
                "attempted_at": int(at_t),
                "sender_id": int(sender_id),
            }
        )
    return out


def format_location_changes(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "agent_id": int(row["agent_id"]),
                "from_place": row.get("from_place"),
                "to_place": str(row["to_place"]),
                "at_tick": int(row["at_tick"]),
                "source": str(row.get("source") or "move"),
            }
        )
    return out


def format_state_changes(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from agent_world.drama_demo.shared.emotion import DEFAULT_EMOTION

    out: List[Dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "agent_id": int(row["agent_id"]),
                "content": str(row["content"]),
                "at_tick": int(row["at_tick"]),
                # 情绪改由 f05 情绪判断 agent 在「当面台词」上打标(emotion_tag)；OS 状态变更不再单独按关键词分类。
                "emotion": DEFAULT_EMOTION,
            }
        )
    return out


def format_group_social_events(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        raw_type = str(row.get("event_type") or "")
        kind = _GROUP_EVENT_KIND.get(raw_type)
        if kind is None:
            continue
        out.append(
            {
                "at_tick": int(row["occurred_at"]),
                "kind": kind,
                "agent_id": int(row["agent_id"]),
                "group_id": int(row["group_id"]),
                "peer_id": (
                    int(row["actor_id"])
                    if row.get("actor_id") is not None
                    else None
                ),
            }
        )
    return out


def format_broadcast_world_events(
    rows: List[Any],
    name_map: Dict[int, str],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        at_tick = int(row["attempted_at"])
        content = str(row["content"] or "")
        place_id = str(row["place_id"]) if row["place_id"] else None
        out.append(
            {
                "id": f"broadcast_{row['message_id']}",
                "at_tick": at_tick,
                "kind": "broadcast",
                "title": sender_display_name(row["sender_id"], name_map),
                "content": content,
                "place_id": place_id,
            }
        )
    return out


def format_agent_locations(raw: Dict[int, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {
        str(agent_id): {
            "place_id": str(info["place_id"]),
            "arrived_at": int(info["arrived_at"]),
        }
        for agent_id, info in raw.items()
    }


def parse_place_attrs(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def legacy_public_messages_from_room_f2f(
    room_f2f: Dict[str, List[Dict[str, Any]]],
    player_place_id: str,
) -> List[Dict[str, Any]]:
    return list(room_f2f.get(player_place_id) or [])


def legacy_observer_from_agent_messages(
    agent_messages: Dict[str, Dict[str, List[Dict[str, Any]]]],
) -> List[Dict[str, Any]]:
    seen: set[tuple] = set()
    out: List[Dict[str, Any]] = []
    for payload in agent_messages.values():
        for msg in payload.get("rdc") or []:
            key = (
                msg.get("type"),
                msg.get("sender"),
                msg.get("recipient"),
                msg.get("attempted_at"),
                msg.get("content"),
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(dict(msg))
    out.sort(key=lambda m: (m.get("attempted_at") or 0, m.get("sender") or ""))
    return out


def legacy_group_from_agent_messages(
    agent_messages: Dict[str, Dict[str, List[Dict[str, Any]]]],
) -> List[Dict[str, Any]]:
    seen: set[tuple] = set()
    out: List[Dict[str, Any]] = []
    for payload in agent_messages.values():
        for msg in payload.get("grp") or []:
            key = (
                msg.get("type"),
                msg.get("sender"),
                msg.get("group_id"),
                msg.get("attempted_at"),
                msg.get("content"),
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(dict(msg))
    out.sort(key=lambda m: (m.get("attempted_at") or 0, m.get("sender") or ""))
    return out


__all__ = [
    "format_f2f_history_with_ids",
    "format_messages",
    "format_f2f_public_messages",
    "format_location_changes",
    "format_state_changes",
    "format_group_social_events",
    "format_broadcast_world_events",
    "format_routing_world_events",
    "format_agent_locations",
    "legacy_public_messages_from_room_f2f",
    "legacy_observer_from_agent_messages",
    "legacy_group_from_agent_messages",
]
