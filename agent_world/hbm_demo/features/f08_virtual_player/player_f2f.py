"""F08 — player-turn F2F rows (sender=agent 0)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from agent_world.hbm_demo.features.f08_virtual_player.config import (
    is_f08_enabled,
    player_agent_id,
)
from agent_world.hbm_demo.features.f05_story_routing.routing import (
    inject_agent_ids_for_phase,
)

log = logging.getLogger("agent_world.hbm_demo.f08.player_f2f")

_PHASE_RECIPIENT: Dict[str, int] = {
    "Phase 1": 1,
    "Phase 2": 2,
    "Phase 3": 2,
    "Phase 4": 2,
}


def f2f_recipient_for_phase(phase: str) -> int:
    targets = inject_agent_ids_for_phase(str(phase))
    if targets:
        return int(targets[0])
    return int(_PHASE_RECIPIENT.get(str(phase), 1))


def build_player_f2f_payload(session: Any, player_text: str) -> Optional[Dict[str, Any]]:
    """Build IPC payload for Runner-side F2F insert (§5.3.1)."""
    if not is_f08_enabled():
        return None
    text = str(player_text or "").strip()
    if not text:
        return None
    phase = str(getattr(session, "phase", "Phase 1"))
    place_id = str(getattr(session, "place_id", "nvidia_reception"))
    return {
        "sender_id": int(player_agent_id()),
        "recipient_id": f2f_recipient_for_phase(phase),
        "place_id": place_id,
        "content": text,
    }


async def apply_player_f2f_payload(
    world_db: Any,
    payload: Optional[Dict[str, Any]],
    *,
    t: int,
) -> Optional[int]:
    """Insert one player F2F row at tick ``t`` (attempted_at = t + 0.5 for ordering)."""
    if not payload or not is_f08_enabled():
        return None
    content = str(payload.get("content") or "").strip()
    if not content:
        return None
    sender_id = int(payload.get("sender_id", player_agent_id()))
    recipient_id = int(payload.get("recipient_id", 0))
    place_id = str(payload.get("place_id") or "nvidia_reception")
    at_t = max(1, int(t))
    mid = await world_db.insert_message(
        sender_id=sender_id,
        recipient_id=recipient_id,
        group_id=None,
        channel_type="F2F",
        content=content,
        place_id=place_id,
        attempted_at=at_t,
        arrive_at=at_t,
        delivered=1,
    )
    log.debug(
        "F08 player F2F sender=%s recipient=%s place=%s t=%s mid=%s",
        sender_id,
        recipient_id,
        place_id,
        at_t,
        mid,
    )
    return int(mid)


__all__ = [
    "apply_player_f2f_payload",
    "build_player_f2f_payload",
    "f2f_recipient_for_phase",
]
