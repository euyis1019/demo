"""F17 — 玩家(agent 0)主动动作 payload 构造与落地（需求二：私信/加群）。

与 player_f2f.py 平级、同款竖切：build_* 在 Flask 侧造 payload，apply_* 在 Runner 的 world_loop
tick 边界落地（写 world.db / 调引擎 grp_bus）。MOVE 走现成 send_move_agent IPC，不在此（见 http 层）。
私信默认即时投递（delivered=1），与 F2F 一致，简化首版。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from agent_world.hbm_demo.features.f17_virtual_player.config import (
    is_f08_enabled,
    player_agent_id,
)

log = logging.getLogger("agent_world.hbm_demo.f17.player_actions")


# ---------------- 私信 RDC ----------------
def build_player_rdc_payload(session: Any, recipient_id: int, text: str) -> Optional[Dict[str, Any]]:
    """玩家私信某 agent（RDC）。recipient_id 由前端指定。"""
    if not is_f08_enabled():
        return None
    content = str(text or "").strip()
    if not content or recipient_id is None:
        return None
    return {
        "sender_id": int(player_agent_id()),
        "recipient_id": int(recipient_id),
        "place_id": str(getattr(session, "place_id", "")),
        "content": content,
    }


async def apply_player_rdc_payload(world_db: Any, payload: Optional[Dict[str, Any]], *, t: int) -> Optional[int]:
    """落地一条玩家 RDC（即时投递）。"""
    if not payload or not is_f08_enabled():
        return None
    content = str(payload.get("content") or "").strip()
    if not content:
        return None
    at_t = max(1, int(t))
    mid = await world_db.insert_message(
        sender_id=int(payload.get("sender_id", player_agent_id())),
        recipient_id=int(payload.get("recipient_id", 0)),
        group_id=None,
        channel_type="RDC",
        content=content,
        place_id=str(payload.get("place_id") or ""),
        attempted_at=at_t,
        arrive_at=at_t,
        delivered=1,
    )
    log.debug("player RDC → %s @t=%s mid=%s", payload.get("recipient_id"), at_t, mid)
    return int(mid)


# ---------------- 加群 / 群发 GRP ----------------
def build_player_grp_payload(session: Any, group_id: int, text: str = "") -> Optional[Dict[str, Any]]:
    """玩家加入群聊并（可选）发一条群消息。门控判定在 Flask 受理时已做（这里只造 payload）。"""
    if not is_f08_enabled() or group_id is None:
        return None
    return {
        "sender_id": int(player_agent_id()),
        "group_id": int(group_id),
        "content": str(text or "").strip(),
    }


async def apply_player_grp_payload(
    world_db: Any, grp_bus: Any, payload: Optional[Dict[str, Any]], *, t: int
) -> bool:
    """落地：把玩家加入群（幂等），并在有内容时群发一条。Runner 入群前应已二次门控。"""
    if not payload or not is_f08_enabled() or grp_bus is None:
        return False
    sender = int(payload.get("sender_id", player_agent_id()))
    gid = int(payload.get("group_id"))
    at_t = max(1, int(t))
    try:
        # 真实签名是 join_group(agent_id, group_id)，用关键字传参杜绝位置写反。
        await grp_bus.join_group(agent_id=sender, group_id=gid)  # 幂等
    except Exception as exc:  # noqa: BLE001
        log.warning("player join_group(agent=%s, group=%s) failed: %s", sender, gid, exc)
        return False
    content = str(payload.get("content") or "").strip()
    if content:
        try:
            await grp_bus.send_to_group(sender, gid, content, at_t)
        except Exception as exc:  # noqa: BLE001
            log.warning("player send_to_group failed: %s", exc)
    log.debug("player joined group %s @t=%s", gid, at_t)
    return True


__all__ = [
    "build_player_rdc_payload",
    "apply_player_rdc_payload",
    "build_player_grp_payload",
    "apply_player_grp_payload",
]
