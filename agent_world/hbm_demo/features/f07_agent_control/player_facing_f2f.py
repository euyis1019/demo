"""F07-E0 — player-visible F2F rows (HBM-only; player is not an engine Agent)."""

from __future__ import annotations

from typing import Any, Dict, Optional

PLAYER_RECIPIENT_ID = 0


def is_speak_to_local_action(action_type: Any) -> bool:
    name = str(
        getattr(action_type, "tool_name", None)
        or getattr(action_type, "value", None)
        or getattr(action_type, "name", None)
        or action_type
        or ""
    )
    return name.lower().replace("-", "_") == "speak_to_local"


def bus_delivered_player_facing_f2f(
    dispatch_result: Optional[Dict[str, Any]],
) -> bool:
    """True when FaceToFaceBus already inserted F2F rows (incl. virtual player @ co-locate).

    ``recipients`` in dispatch_result holds inserted message_ids, not agent ids.
    When agent 0 is co-located, Bus delivers NPC→player without emit fallback.
    """
    if not dispatch_result or not dispatch_result.get("success"):
        return False
    inserted = dispatch_result.get("recipients")
    return isinstance(inserted, list) and len(inserted) > 0


def should_emit_player_facing_f2f(dispatch_result: Optional[Dict[str, Any]]) -> bool:
    """Emit fallback only when Bus wrote no co-located F2F rows."""
    return not bus_delivered_player_facing_f2f(dispatch_result)


def co_located_peer_count(world: Any, agent_id: int) -> int:
    places = getattr(world, "places", None)
    if places is None:
        return 0
    place = places.L_t(int(agent_id))
    if not place:
        return 0
    try:
        peers = places.agents_at(str(place)) - {int(agent_id)}
    except (TypeError, AttributeError):
        return 0
    return len(peers)


async def emit_player_facing_f2f(
    world_db: Any,
    *,
    sender_id: int,
    place_id: str,
    content: str,
    t: int,
) -> int:
    """Insert one F2F row when FaceToFaceBus had no co-located recipients (Phase 1 reception)."""
    text = str(content or "").strip()
    if not text:
        raise ValueError("player-facing F2F content must be non-empty")
    return await world_db.insert_message(
        sender_id=int(sender_id),
        recipient_id=PLAYER_RECIPIENT_ID,
        group_id=None,
        channel_type="F2F",
        content=text,
        place_id=str(place_id),
        attempted_at=int(t),
        arrive_at=int(t),
        delivered=1,
    )


__all__ = [
    "PLAYER_RECIPIENT_ID",
    "bus_delivered_player_facing_f2f",
    "co_located_peer_count",
    "emit_player_facing_f2f",
    "is_speak_to_local_action",
    "should_emit_player_facing_f2f",
]
