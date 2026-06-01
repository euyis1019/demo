"""F07 conversation — read-only world.db query helpers（通用，无故事/HBM 耦合）。

叶子模块：control 的通用对话节奏提示经这里读 world.db（谁有未读 RDC、对方是否已回复）。
"""

from __future__ import annotations

from typing import Any, List


def _has_rdc_reply_from(
    world_db: Any,
    *,
    agent_id: int,
    sender_id: int,
    since_t: int,
    t_now: int,
) -> bool:
    """True when ``sender_id`` replied via delivered RDC or executive GRP."""
    try:
        rows = world_db.fetch_arrived_for(int(agent_id), int(t_now), int(since_t) - 1)
    except Exception:  # noqa: BLE001
        return False
    sid = int(sender_id)
    for row in rows:
        if int(getattr(row, "sender_id", -1)) != sid:
            continue
        channel = str(getattr(row, "channel_type", "RDC") or "RDC").upper()
        if channel == "RDC":
            return True
        if channel == "GRP" and int(getattr(row, "group_id", 0) or 0) == 100:
            return True
    return False


def _unread_rdc_sender_ids(
    agent_id: int,
    agent: Any,
    world: Any,
    t: int,
    db: Any,
) -> List[int]:
    """Senders with delivered RDC not yet covered by this agent's outbound reply."""
    last = getattr(agent, "last_message_seen_at", None)
    last_seen = -1 if last is None else int(last)
    try:
        rows = db.fetch_arrived_for(int(agent_id), int(t), last_seen)
    except Exception:  # noqa: BLE001
        return []

    senders: List[int] = []
    seen: set[int] = set()
    for row in rows:
        channel = str(getattr(row, "channel_type", "RDC") or "RDC").upper()
        if channel != "RDC":
            continue
        sid = int(getattr(row, "sender_id", -1))
        if sid < 0 or sid in seen:
            continue
        seen.add(sid)
        senders.append(sid)
    return senders
