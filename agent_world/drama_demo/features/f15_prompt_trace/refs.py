"""F15 ref_key builders and delta enrichment."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional


def f2f_ref_key(place_id: str, at_tick: int, sender_id: int) -> str:
    return f"f2f:{place_id}:{at_tick}:{sender_id}"


def rdc_ref_key(at_tick: int, sender_id: int, recipient_id: int) -> str:
    return f"rdc:{at_tick}:{sender_id}:{recipient_id}"


def grp_ref_key(at_tick: int, sender_id: int, group_id: int) -> str:
    return f"grp:{at_tick}:{sender_id}:{group_id}"


def state_ref_key(at_tick: int, agent_id: int, content: str) -> str:
    digest = hashlib.sha256(str(content).encode("utf-8")).hexdigest()[:8]
    return f"state:{at_tick}:{agent_id}:{digest}"


def location_ref_key(at_tick: int, agent_id: int) -> str:
    return f"loc:{at_tick}:{agent_id}"


def noop_ref_key(at_tick: int, agent_id: int) -> str:
    return f"noop:{at_tick}:{agent_id}"


def build_link_map(links: List[Dict[str, Any]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for row in links:
        ref = str(row.get("ref_key") or "")
        trace_id = str(row.get("trace_id") or "")
        if ref and trace_id:
            out[ref] = trace_id
    return out


def attach_trace_fields(
    item: Dict[str, Any],
    *,
    ref_key: str,
    link_map: Dict[str, str],
) -> None:
    # 只有当这条行动**确有 trace 链接**时才挂 ref_key+prompt_trace_id——前端据 ref_key 渲染「查看 Prompt」
    # 入口。没有 LLM 决策的行动（玩家自己的台词/私信/群聊、或本拍因故没建 trace）就不挂，前端自然不可点，
    # 从根上杜绝「点开报 no trace」的死链：可点 ⟺ 真有 prompt 可看。
    trace_id = link_map.get(ref_key)
    if trace_id:
        item["ref_key"] = ref_key
        item["prompt_trace_id"] = trace_id


def enrich_f2f_messages(
    messages: List[Dict[str, Any]],
    *,
    place_id: str,
    link_map: Dict[str, str],
) -> None:
    for msg in messages:
        sender_id = msg.get("sender_id")
        at_tick = msg.get("attempted_at")
        if sender_id is None or at_tick is None:
            continue
        attach_trace_fields(
            msg,
            ref_key=f2f_ref_key(str(place_id), int(at_tick), int(sender_id)),
            link_map=link_map,
        )


def enrich_channel_messages(
    messages: List[Dict[str, Any]],
    *,
    channel: str,
    link_map: Dict[str, str],
) -> None:
    for msg in messages:
        sender_id = msg.get("sender_id")
        at_tick = msg.get("attempted_at")
        if sender_id is None or at_tick is None:
            continue
        if channel == "RDC":
            recipient_id = msg.get("recipient_id")
            if recipient_id is None:
                continue
            ref = rdc_ref_key(int(at_tick), int(sender_id), int(recipient_id))
        elif channel == "GRP":
            group_id = msg.get("group_id")
            if group_id is None:
                continue
            ref = grp_ref_key(int(at_tick), int(sender_id), int(group_id))
        else:
            continue
        attach_trace_fields(msg, ref_key=ref, link_map=link_map)


def enrich_state_changes(
    changes: List[Dict[str, Any]],
    link_map: Dict[str, str],
) -> None:
    for row in changes:
        attach_trace_fields(
            row,
            ref_key=state_ref_key(
                int(row["at_tick"]),
                int(row["agent_id"]),
                str(row.get("content") or ""),
            ),
            link_map=link_map,
        )


def enrich_location_changes(
    changes: List[Dict[str, Any]],
    link_map: Dict[str, str],
) -> None:
    for row in changes:
        source = str(row.get("source") or "")
        if source == "ipc_move":
            continue
        attach_trace_fields(
            row,
            ref_key=location_ref_key(int(row["at_tick"]), int(row["agent_id"])),
            link_map=link_map,
        )


def enrich_world_delta(
    delta: Dict[str, Any],
    link_map: Dict[str, str],
) -> Dict[str, Any]:
    link_map = link_map or {}

    room_f2f = delta.get("room_f2f") or {}
    if isinstance(room_f2f, dict):
        for place_id, messages in room_f2f.items():
            if isinstance(messages, list):
                enrich_f2f_messages(messages, place_id=str(place_id), link_map=link_map)

    agent_messages = delta.get("agent_messages") or {}
    if isinstance(agent_messages, dict):
        for bucket in agent_messages.values():
            if not isinstance(bucket, dict):
                continue
            enrich_channel_messages(bucket.get("rdc") or [], channel="RDC", link_map=link_map)
            enrich_channel_messages(bucket.get("grp") or [], channel="GRP", link_map=link_map)

    for key in ("public_messages", "observer_messages", "group_messages"):
        items = delta.get(key)
        if isinstance(items, list):
            for msg in items:
                ch = str(msg.get("type") or "")
                if ch == "F2F":
                    place_id = msg.get("place_id")
                    sender_id = msg.get("sender_id")
                    at_tick = msg.get("attempted_at")
                    if place_id and sender_id is not None and at_tick is not None:
                        attach_trace_fields(
                            msg,
                            ref_key=f2f_ref_key(
                                str(place_id), int(at_tick), int(sender_id)
                            ),
                            link_map=link_map,
                        )
                elif ch == "RDC":
                    enrich_channel_messages([msg], channel="RDC", link_map=link_map)
                elif ch == "GRP":
                    enrich_channel_messages([msg], channel="GRP", link_map=link_map)

    enrich_state_changes(delta.get("state_changes") or [], link_map)
    enrich_location_changes(delta.get("location_changes") or [], link_map)
    return delta
