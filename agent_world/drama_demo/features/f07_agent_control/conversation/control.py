"""F07 — soft conversation pacing (no L5 tool hard block).

Stimulus-driven tick gating + prompt hints:
- Agents with unread inbound are always eligible to tick (reply promptly).
- Inject agents tick while ``player_memory`` is pending, then drop off.
- After outbound RDC with no reply, discourage repeat spam via prompt hints.

提示全部是数据驱动、与故事无关的通用对话节奏（未读须回、已发别重复催、本批 inject 回应过别复读），
world.db 查询经叶子模块 ``queries``。已无任何 HBM/相位/角色硬编码提示。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent_world.drama_demo.features.f07_agent_control.conversation.queries import (
    _has_rdc_reply_from,
    _unread_rdc_sender_ids,
)


def resolve_world_db(world: Any) -> Any:
    """Return the WorldDB handle attached to a world / world_state."""
    for attr in ("world_db", "db"):
        db = getattr(world, attr, None)
        if db is not None:
            return db
    return None


def has_unread_inbound(
    agent_id: int,
    agent: Any,
    world: Any,
    t: int,
    *,
    rdc_from: Optional[int] = None,
) -> bool:
    db = resolve_world_db(world)
    if db is None:
        return False
    last = getattr(agent, "last_message_seen_at", None)
    last_seen = -1 if last is None else int(last)

    try:
        rows = db.fetch_arrived_for(int(agent_id), int(t), last_seen)
    except Exception:  # noqa: BLE001
        rows = []

    if rdc_from is not None:
        return any(
            int(getattr(row, "sender_id", -1)) == int(rdc_from)
            for row in rows
            if str(getattr(row, "channel_type", "RDC") or "RDC").upper() == "RDC"
        )

    if rows:
        return True

    places = getattr(world, "places", None)
    if places is None:
        return False
    place = places.L_t(agent_id)
    if not place:
        return False
    try:
        f2f = db.fetch_f2f_history_at(str(place), int(t), last_seen, limit=10)
    except Exception:  # noqa: BLE001
        return False
    for at_tick, sender_id, _mid, _content in f2f:
        if int(sender_id) != int(agent_id) and int(at_tick) > last_seen:
            return True
    return False


def _action_name(action_type: Any) -> str:
    return str(
        getattr(action_type, "tool_name", None)
        or getattr(action_type, "value", None)
        or getattr(action_type, "name", None)
        or action_type
        or ""
    ).lower().replace("-", "_")


def mark_communication_action(
    agent: Any,
    *,
    action_type: Any,
    action_kwargs: Dict[str, Any],
    dispatch_result: Optional[Dict[str, Any]],
    t: int,
) -> None:
    """Record successful comms so inject memory clears and RDC pending is tracked."""
    if not dispatch_result or not dispatch_result.get("success"):
        return

    name = _action_name(action_type)
    if name in ("speak_to_local", "send_message", "send_to_group"):
        mem = getattr(agent, "player_memory", None)
        if mem is not None and hasattr(mem, "clear") and mem:
            mem.clear()
        setattr(agent, "_inject_responded", True)  # noqa: SLF001
        if hasattr(agent, "last_message_seen_at"):
            agent.last_message_seen_at = int(t)

    if name == "send_message":
        target = action_kwargs.get("target")
        if target is not None:
            pending: Dict[int, int] = dict(getattr(agent, "_pending_rdc_out", {}) or {})
            pending[int(target)] = int(t)
            agent._pending_rdc_out = pending  # noqa: SLF001
            content = str(action_kwargs.get("content") or "").strip()
            if content:
                last_out: Dict[int, str] = dict(
                    getattr(agent, "_last_rdc_out_content", {}) or {}
                )
                last_out[int(target)] = content
                agent._last_rdc_out_content = last_out  # noqa: SLF001


def build_conversation_hints(
    agent_id: int,
    agent: Any,
    world: Any,
    t: int,
) -> str:
    """中性事实信号块（数据驱动、与故事无关）：只陈述收件箱/已发未回/本批已回应的**事实**，
    不写「该不该回/要不要催/何时 do_nothing」这类表演判断——那由 actor 自行决定，节奏纪律由 acting_guide 指导。"""
    lines: List[str] = []
    db = resolve_world_db(world)
    aid = int(agent_id)
    tick = int(t)
    mem = getattr(agent, "player_memory", None)

    # 1) 收件箱有未读（事实）：列出待回的 RDC 发件人
    if has_unread_inbound(aid, agent, world, tick):
        senders = [str(sid) for sid in (_unread_rdc_sender_ids(aid, agent, world, tick, db) if db else [])]
        if senders:
            lines.append("【收件箱】你有来自 Agent" + "、Agent".join(senders) + " 的未读私信(RDC)。")
        else:
            lines.append("【收件箱】你有未读消息。")

    # 2) 已发 RDC 尚未收到回复（事实，含发出时刻）
    pending: Dict[int, int] = dict(getattr(agent, "_pending_rdc_out", {}) or {})
    if db is not None:
        still_pending: Dict[int, int] = {}
        for target, sent_t in pending.items():
            if _has_rdc_reply_from(
                db, agent_id=aid, sender_id=int(target), since_t=int(sent_t), t_now=tick
            ):
                continue
            still_pending[int(target)] = int(sent_t)
            if tick - int(sent_t) >= 1:
                lines.append(
                    f"【已发未回】你在 t={sent_t} 发给 Agent{target} 的私信(RDC)，对方尚未回复。"
                )
        if still_pending != pending:
            agent._pending_rdc_out = still_pending  # noqa: SLF001

    # 3) 玩家 inject 回应状态（事实）
    if mem:
        lines.append("【玩家 inject】本批你尚未首次回应玩家。")
    elif getattr(agent, "_inject_responded", False) and not has_unread_inbound(aid, agent, world, tick):
        lines.append("【本批已回应】你已处理过本轮玩家 inject，且当前无新未读消息。")

    return "\n".join(lines)


__all__ = [
    "build_conversation_hints",
    "has_unread_inbound",
    "mark_communication_action",
    "resolve_world_db",
]
