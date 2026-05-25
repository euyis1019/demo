"""F07 — soft conversation pacing (no L5 tool hard block).

Stimulus-driven tick gating + prompt hints:
- Agents with unread inbound are always eligible to tick (reply promptly).
- Inject agents tick while ``player_memory`` is pending, then drop off.
- After outbound RDC with no reply, discourage repeat spam via prompt hints.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from agent_world.hbm_demo.features.f07_agent_control.config import load_turn_control


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
        return any(int(getattr(r, "sender_id", -1)) == int(rdc_from) for r in rows)

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


def _phase_cfg(phase: str) -> Dict[str, Any]:
    phases = load_turn_control().get("phases") or {}
    return dict(phases.get(phase) or {})


def inject_response_ticks(phase: str) -> int:
    cfg = _phase_cfg(phase)
    return max(0, int(cfg.get("inject_response_ticks", 4)))


def primary_notify_ticks(phase: str) -> int:
    cfg = _phase_cfg(phase)
    return max(0, int(cfg.get("primary_notify_ticks", 3)))


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

    if name == "send_message":
        target = action_kwargs.get("target")
        if target is not None:
            pending: Dict[int, int] = dict(getattr(agent, "_pending_rdc_out", {}) or {})
            pending[int(target)] = int(t)
            agent._pending_rdc_out = pending  # noqa: SLF001


def _has_rdc_reply_from(
    world_db: Any,
    *,
    agent_id: int,
    sender_id: int,
    since_t: int,
    t_now: int,
) -> bool:
    try:
        rows = world_db.fetch_arrived_for(int(agent_id), int(t_now), int(since_t) - 1)
    except Exception:  # noqa: BLE001
        return False
    return any(int(getattr(r, "sender_id", -1)) == int(sender_id) for r in rows)


def build_conversation_hints(
    agent_id: int,
    agent: Any,
    world: Any,
    t: int,
) -> str:
    """Soft prompt block: reply when inbox non-empty; do_nothing when spamming."""
    lines: List[str] = []
    db = resolve_world_db(world)
    aid = int(agent_id)
    tick = int(t)

    if has_unread_inbound(aid, agent, world, tick):
        lines.append(
            "【收件箱】你有尚未处理的未读消息（RDC/F2F）。本拍应优先回复对方；"
            "可用 speak_to_local 或 send_message，不要拖延到下一拍。"
        )

    pending: Dict[int, int] = dict(getattr(agent, "_pending_rdc_out", {}) or {})
    if db is not None:
        still_pending: Dict[int, int] = {}
        for target, sent_t in pending.items():
            if _has_rdc_reply_from(
                db,
                agent_id=aid,
                sender_id=int(target),
                since_t=int(sent_t),
                t_now=tick,
            ):
                continue
            still_pending[int(target)] = int(sent_t)
            if tick - int(sent_t) >= 1:
                lines.append(
                    f"【待发跟进】你已在 t={sent_t} 向 Agent{target} 发过 RDC，对方尚未回复。"
                    "本拍勿用相同内容重复催促；可选 do_nothing、update_state，"
                    "或等对方回信后再行动。"
                )
        if still_pending != pending:
            agent._pending_rdc_out = still_pending  # noqa: SLF001

    mem = getattr(agent, "player_memory", None)
    if mem:
        lines.append(
            "【玩家 inject】本批对话你尚未完成首次回应；回应玩家后不必每拍重复相同简报。"
        )
    elif getattr(agent, "_inject_responded", False) and not has_unread_inbound(
        aid, agent, world, tick
    ):
        lines.append(
            "【本批已回应】你已处理过本轮玩家 inject 且无新未读消息。"
            "不必重复相同 F2F/RDC；若玩家仍在场或场景有变化，可 update_state 或短句跟进；"
            "确无新信息时再 do_nothing。"
        )

    if not lines:
        return ""
    return "\n".join(lines)


__all__ = [
    "build_conversation_hints",
    "has_unread_inbound",
    "inject_response_ticks",
    "mark_communication_action",
    "primary_notify_ticks",
    "resolve_world_db",
]
