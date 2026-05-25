"""Agent-driven routing signals — read world.db (dev_logs/30 PR3 · dev_logs/31 Phase 4)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent_world.hbm_demo.features.f05_story_routing.routing_config import (
    approve_keywords,
    escort_keywords,
    expel_keywords,
    max_turns_phase1_without_approve,
    reject_keywords,
)
from agent_world.hbm_demo.features.f06_read_model.world_db import sender_display_name

RECEPTION_AGENT_ID = 1
JENSEN_ID = 2
TECH_VP_ID = 3
CEO_IDS = (4, 5, 6)

PLACE_RECEPTION = "nvidia_reception"
PLACE_JENSEN_ROOM = "jensen_private_room"
PLACE_NEGOTIATION = "negotiation_room"


def _content_matches(content: str, keywords: tuple[str, ...]) -> bool:
    text = str(content or "")
    return any(kw in text for kw in keywords)


def _has_rdc_pair(db: Any, *, sender_id: int, recipient_id: int, since_t: int, t_now: int) -> bool:
    rows = db.fetch_rdc_messages(
        sender_id=int(sender_id),
        recipient_id=int(recipient_id),
        since_t=int(since_t),
        t_now=int(t_now),
    )
    return len(rows) > 0


def detect_node_a(db: Any, *, since_t: int, t_now: int) -> bool:
    """Phase 1 → 2: RDC chain 1→2, 2→3, 2→1 approve."""
    if not _has_rdc_pair(db, sender_id=1, recipient_id=2, since_t=since_t, t_now=t_now):
        return False
    if not _has_rdc_pair(db, sender_id=2, recipient_id=3, since_t=since_t, t_now=t_now):
        return False
    rows = db.fetch_rdc_messages(
        sender_id=JENSEN_ID,
        recipient_id=RECEPTION_AGENT_ID,
        since_t=since_t,
        t_now=t_now,
    )
    for row in rows:
        if _content_matches(str(row["content"] or ""), approve_keywords()):
            return True
    return False


def detect_node_b(db: Any, *, since_t: int, t_now: int) -> bool:
    """Phase 2 → 3: Jensen F2F @ private room and/or VP positive RDC."""
    from agent_world.hbm_demo.features.f05_story_routing.routing import (
        POSITIVE_RDC_KEYWORDS,
        has_positive_tech_vp_rdc,
    )

    history = db.fetch_f2f_history_at(PLACE_JENSEN_ROOM, t_now, since_t)
    if any(int(sender_id) == JENSEN_ID for _t, sender_id, _mid, _content in history):
        return True
    return has_positive_tech_vp_rdc(db, since_tick=since_t, t_now=t_now)


def detect_node_c(db: Any, *, since_t: int, t_now: int) -> bool:
    """Phase 3 → 4: Jensen expels CEOs via F2F/RDC."""
    for ceo_id in CEO_IDS:
        rows = db.fetch_rdc_messages(
            sender_id=JENSEN_ID,
            recipient_id=int(ceo_id),
            since_t=since_t,
            t_now=t_now,
        )
        for row in rows:
            if _content_matches(str(row["content"] or ""), expel_keywords()):
                return True

    history = db.fetch_f2f_history_at(PLACE_NEGOTIATION, t_now, since_t)
    for _at_t, sender_id, _mid, content in history:
        if int(sender_id) == JENSEN_ID and _content_matches(content, expel_keywords()):
            return True
    return False


def detect_bad_end(session: Any, db: Any, *, t_now: int) -> bool:
    """Bad End: reception reject F2F or Phase1 timeout without approve chain."""
    if str(getattr(session, "phase", "")) != "Phase 1":
        return False

    since_t = max(0, int(getattr(session, "start_tick", 0) or 0))
    history = db.fetch_f2f_history_at(PLACE_RECEPTION, int(t_now), since_t)
    for _at_t, sender_id, _mid, content in history:
        if int(sender_id) == RECEPTION_AGENT_ID and _content_matches(content, reject_keywords()):
            return True

    player_turn = int(getattr(session, "player_turn", 1))
    limit = max_turns_phase1_without_approve()
    if player_turn >= limit and not detect_node_a(db, since_t=since_t, t_now=int(t_now)):
        return True
    return False


def fetch_bad_end_public_messages(
    db: Any,
    *,
    t_now: int,
    name_map: Dict[int, str],
    since_t: int = 0,
) -> List[Dict[str, Any]]:
    """Return Agent1 reject F2F from DB for bad_end UI."""
    history = db.fetch_f2f_history_at(PLACE_RECEPTION, int(t_now), int(since_t))
    for at_t, sender_id, _mid, content in reversed(history):
        if int(sender_id) != RECEPTION_AGENT_ID:
            continue
        if not _content_matches(content, reject_keywords()):
            continue
        return [
            {
                "sender": sender_display_name(RECEPTION_AGENT_ID, name_map),
                "content": str(content),
                "type": "F2F",
                "attempted_at": int(at_t),
                "sender_id": RECEPTION_AGENT_ID,
                "place_id": PLACE_RECEPTION,
            }
        ]
    return [
        {
            "sender": sender_display_name(RECEPTION_AGENT_ID, name_map),
            "content": "保安，请这位先生离开。",
            "type": "F2F",
        }
    ]


__all__ = [
    "CEO_IDS",
    "JENSEN_ID",
    "TECH_VP_ID",
    "detect_bad_end",
    "detect_node_a",
    "detect_node_b",
    "detect_node_c",
    "fetch_bad_end_public_messages",
]
