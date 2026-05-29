"""F07 conversation — read-only world.db query/keyword helpers.

Leaf module (no intra-package imports): the rule builders in f2f_rules /
batch_rules and the control orchestrator all read through these helpers.
"""

from __future__ import annotations

from typing import Any, List, Tuple


def _recent_rdc_count(
    world_db: Any,
    *,
    sender_id: int,
    recipient_id: int,
    since_t: int,
    t_now: int,
) -> int:
    try:
        rows = world_db.fetch_rdc_messages(
            sender_id=int(sender_id),
            recipient_id=int(recipient_id),
            since_t=int(since_t),
            t_now=int(t_now),
        )
    except Exception:  # noqa: BLE001
        return 0
    return len(rows)


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


def _content_has_keywords(content: str, keywords: tuple[str, ...]) -> bool:
    text = str(content or "")
    return any(kw in text for kw in keywords)


_VP_POSITIVE_RDC_KEYWORDS: Tuple[str, ...] = (
    "可行",
    "核武器",
    "理论上成立",
    "数学上成立",
    "放他进来",
    "值得见",
    "靠谱",
)


def _rdc_row_content(row: Any) -> str:
    if isinstance(row, dict):
        return str(row.get("content") or "")
    try:
        return str(row["content"] or "")
    except (KeyError, TypeError):
        pass
    return str(getattr(row, "content", "") or "")


def _has_approve_rdc_to_reception(db: Any, *, since_t: int, t_now: int) -> bool:
    from agent_world.hbm_demo.features.f05_story_routing.routing_config import (
        approve_keywords,
    )

    try:
        rows = db.fetch_rdc_messages(
            sender_id=2, recipient_id=1, since_t=int(since_t), t_now=int(t_now)
        )
    except Exception:  # noqa: BLE001
        return False
    for row in rows:
        if _content_has_keywords(_rdc_row_content(row), approve_keywords()):
            return True
    return False


def _vp_positive_rdc_to_jensen(db: Any, *, since_t: int, t_now: int) -> bool:
    try:
        rows = db.fetch_rdc_messages(
            sender_id=3, recipient_id=2, since_t=int(since_t), t_now=int(t_now)
        )
    except Exception:  # noqa: BLE001
        return False
    for row in rows:
        if _content_has_keywords(_rdc_row_content(row), _VP_POSITIVE_RDC_KEYWORDS):
            return True
    return False


def _player_f2f_count_at_reception(db: Any, *, since_t: int, t_now: int) -> int:
    try:
        history = db.fetch_f2f_history_at(
            "nvidia_reception", int(t_now), int(since_t)
        )
    except Exception:  # noqa: BLE001
        return 0
    return sum(1 for _at_t, sender_id, _mid, _content in history if int(sender_id) == 0)


def _jensen_node_a_chain_ready(db: Any, *, since_t: int, t_now: int) -> bool:
    return (
        _recent_rdc_count(db, sender_id=1, recipient_id=2, since_t=since_t, t_now=t_now)
        > 0
        and _recent_rdc_count(db, sender_id=2, recipient_id=3, since_t=since_t, t_now=t_now)
        > 0
        and _recent_rdc_count(db, sender_id=3, recipient_id=2, since_t=since_t, t_now=t_now)
        > 0
    )


def _jensen_should_issue_approve(db: Any, *, since_t: int, t_now: int) -> bool:
    if _has_approve_rdc_to_reception(db, since_t=since_t, t_now=t_now):
        return False
    if not _jensen_node_a_chain_ready(db, since_t=since_t, t_now=t_now):
        return False
    return _vp_positive_rdc_to_jensen(db, since_t=since_t, t_now=t_now)
