"""F17 — player-turn F2F rows (sender=agent 0, the virtual player)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from agent_world.hbm_demo.features.f17_virtual_player.config import (
    is_f08_enabled,
    player_agent_id,
)
from agent_world.hbm_demo.features.f05_story_routing import node_inject_ids

log = logging.getLogger("agent_world.hbm_demo.f17.player_f2f")


def f2f_recipient_for_phase(phase: str) -> int:
    """无当前节点时的兜底收件人——默认 1（正常情况下走 build_player_f2f_payload 的节点收件人）。"""
    return 1


def build_player_f2f_payload(session: Any, player_text: str) -> Optional[Dict[str, Any]]:
    """Build IPC payload for Runner-side F2F insert (§5.3.1)."""
    if not is_f08_enabled():
        return None
    text = str(player_text or "").strip()
    if not text:
        return None
    phase = str(getattr(session, "phase", "Phase 1"))
    place_id = str(getattr(session, "place_id", ""))
    # 节点驱动：玩家台词收件人=当前节点首个在场 NPC，地点=当前节点 place_focus（数据驱动，无相位硬规则）。
    node_id = getattr(session, "current_node_id", None)
    agents = node_inject_ids(session)
    recipient_id = int(agents[0]) if agents else f2f_recipient_for_phase(phase)
    if node_id:
        from agent_world.hbm_demo.shared import story_config

        place_id = story_config.node_place(node_id) or place_id
    return {
        "sender_id": int(player_agent_id()),
        "recipient_id": recipient_id,
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
