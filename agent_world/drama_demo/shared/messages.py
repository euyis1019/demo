"""Shared message formatting for UI payloads (F03/F12)."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from agent_world.drama_demo.features.f06_read_model.world_db import sender_display_name


def format_messages(
    rows: List[Any],
    name_map: Dict[int, str],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        ch = str(row["channel_type"])
        item: Dict[str, Any] = {
            "sender": sender_display_name(row["sender_id"], name_map),
            "content": str(row["content"] or ""),
            "type": ch,
            "attempted_at": int(row["attempted_at"]),
        }
        if row["sender_id"] is not None:
            item["sender_id"] = int(row["sender_id"])
        if ch == "RDC":
            item["recipient"] = sender_display_name(row["recipient_id"], name_map)
            item["recipient_id"] = int(row["recipient_id"])
        if ch == "GRP" and row["group_id"] is not None:
            item["group_id"] = int(row["group_id"])
        if row["place_id"]:
            item["place_id"] = str(row["place_id"])
        if "delivered" in row.keys():
            item["delivered"] = int(row["delivered"])
        if row["sender_id"] is not None and int(row["sender_id"]) == -1:
            item["is_system"] = True
        # 情绪不再在此按关键词分类——当面台词的情绪由 f05 情绪判断 agent 统一在 delta 装配时打标（emotion_tag）。
        out.append(item)
    return out


def format_f2f_public_messages(
    history: List[Tuple[int, int, int, str]],
    name_map: Dict[int, str],
) -> List[Dict[str, Any]]:
    return [
        {
            "sender": sender_display_name(sender_id, name_map),
            "content": content,
            "type": "F2F",
            "attempted_at": at_t,
            "sender_id": int(sender_id),
        }
        for at_t, sender_id, _mid, content in history
        if at_t > 0
    ]
