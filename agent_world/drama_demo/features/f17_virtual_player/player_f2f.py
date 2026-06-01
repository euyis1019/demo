"""F17 — player-turn F2F rows (sender=agent 0, the virtual player)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from agent_world.drama_demo.features.f17_virtual_player.config import (
    is_f08_enabled,
    player_agent_id,
)
from agent_world.drama_demo.features.f05_story_routing import node_inject_ids

log = logging.getLogger("agent_world.drama_demo.f17.player_f2f")


def _fallback_recipient(place_id: str) -> int:
    """无当前节点 inject_agents 时，从活跃 Story Pack 推导兜底收件人：优先同地点 NPC，其次任一 NPC。
    数据驱动、无写死 agent_id；实在无 NPC 时返回 0（不投递给任何具体 NPC，避免错投到不存在的 agent）。"""
    try:
        from agent_world.drama_demo.shared import story_config

        agents = story_config.active_pack().agents.get("agents") or []
        same_place = [
            int(a["agent_id"]) for a in agents
            if int(a.get("agent_id", -1)) > 0 and str(a.get("location") or "") == str(place_id)
        ]
        if same_place:
            return same_place[0]
        npcs = [int(a["agent_id"]) for a in agents if int(a.get("agent_id", -1)) > 0]
        if npcs:
            return npcs[0]
    except Exception:  # noqa: BLE001 — 无活跃包/解析失败时返回 0
        pass
    return 0


def build_player_f2f_payload(session: Any, player_text: str) -> Optional[Dict[str, Any]]:
    """Build IPC payload for Runner-side F2F insert (§5.3.1)。"""
    if not is_f08_enabled():
        return None
    text = str(player_text or "").strip()
    if not text:
        return None
    place_id = str(getattr(session, "place_id", ""))
    # 节点驱动：玩家台词收件人=当前节点首个在场 NPC，地点=当前节点 place_focus（数据驱动，无相位/角色硬规则）。
    node_id = getattr(session, "current_node_id", None)
    agents = node_inject_ids(session)
    recipient_id = int(agents[0]) if agents else _fallback_recipient(place_id)
    if node_id:
        from agent_world.drama_demo.shared import story_config

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
    place_id = str(payload.get("place_id") or "")
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
]
