"""F07 — soft conversation pacing (no L5 tool hard block).

Stimulus-driven tick gating + prompt hints:
- Agents with unread inbound are always eligible to tick (reply promptly).
- Inject agents tick while ``player_memory`` is pending, then drop off.
- After outbound RDC with no reply, discourage repeat spam via prompt hints.

This module owns the public API + the orchestrator ``build_conversation_hints``;
the per-rule hint builders live in ``f2f_rules`` / ``batch_rules`` and the
world.db query helpers in ``queries`` (this file imports from them, not vice
versa — keeping the dependency acyclic: queries ← batch_rules ← f2f_rules ←
control).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent_world.hbm_demo.features.f07_agent_control.config import load_turn_control
from agent_world.hbm_demo.features.f07_agent_control.conversation.batch_rules import (
    _node_a_progress_hints,
)
from agent_world.hbm_demo.features.f07_agent_control.conversation.f2f_rules import (
    _jensen_reception_spam_hints,
    _jensen_vp_link_hints,
    _move_and_location_hints,
    _negotiation_room_hints,
    _rdc_reply_obligation_hints,
    _reception_jensen_spam_hints,
)
from agent_world.hbm_demo.features.f07_agent_control.conversation.queries import (
    _has_rdc_reply_from,
    _recent_rdc_count,
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


def _agent_place(world: Any, agent_id: int) -> str:
    places = getattr(world, "places", None)
    if places is None:
        return ""
    return str(places.L_t(int(agent_id)) or "")


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
    phase = ""
    ctx = getattr(agent, "_batch_turn_context", None)
    if isinstance(ctx, dict):
        phase = str(ctx.get("phase") or "")

    place = _agent_place(world, aid)
    mem = getattr(agent, "player_memory", None)
    lines.extend(_move_and_location_hints(aid, phase, place))
    lines.extend(_negotiation_room_hints(aid, agent, world, tick, phase, place))
    if db is not None:
        lines.extend(_node_a_progress_hints(aid, agent, phase, db, tick, mem=mem))
        lines.extend(_rdc_reply_obligation_hints(aid, agent, world, tick, phase, db))
        lines.extend(_jensen_reception_spam_hints(aid, agent, world, tick, phase, db))
        lines.extend(_jensen_vp_link_hints(aid, agent, phase, world, tick, db))
        lines.extend(_reception_jensen_spam_hints(aid, phase, tick, db))

    if has_unread_inbound(aid, agent, world, tick):
        lines.append(
            "【收件箱】未读消息须本拍处理：RDC 用 send_message 回复发件人，"
            "同室 F2F 用 speak_to_local；不要空过。"
        )
        if aid == 3 and has_unread_inbound(aid, agent, world, tick, rdc_from=2):
            lines.append(
                "【Jensen 求证】send_message→2，1–3 句技术评估；"
                "正面含「可行/核武器/理论上成立」。"
            )
        elif aid == 1 and has_unread_inbound(aid, agent, world, tick, rdc_from=2):
            lines.append(
                "【Jensen 回信】send_message→2 确认收到，并 speak_to_local 转告玩家。"
            )
        else:
            for sid in _unread_rdc_sender_ids(aid, agent, world, tick, db) if db else []:
                if sid in (1, 2, 3) and (
                    (aid == 2 and sid == 1)
                    or (aid == 3 and sid == 2)
                    or (aid == 1 and sid == 2)
                ):
                    continue
                lines.append(
                    f"【私信回复】Agent{sid} 的 RDC 等待回复——本拍 send_message→{sid}。"
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

    if mem:
        lines.append(
            "【玩家 inject】本批对话你尚未完成首次回应；回应玩家后不必每拍重复相同简报。"
        )
        if aid == 1 and phase == "Phase 1" and db is not None:
            since_t = max(0, tick - 50)
            if (
                _recent_rdc_count(
                    db, sender_id=1, recipient_id=2, since_t=since_t, t_now=tick
                )
                == 0
            ):
                lines.append(
                    "【节点 A·同批 RDC】F2F 回应玩家后，本批仍须 send_message→2 简报 Jensen，"
                    "不可 speak_to_local 后就 do_nothing。"
                )
    elif getattr(agent, "_inject_responded", False) and not has_unread_inbound(
        aid, agent, world, tick
    ):
        if (
            aid == 1
            and phase == "Phase 1"
            and db is not None
            and _recent_rdc_count(
                db, sender_id=1, recipient_id=2, since_t=max(0, tick - 20), t_now=tick
            )
            == 0
        ):
            lines.append(
                "【节点 A·补 RDC】你已 F2F 回应玩家但尚未 send_message→2 简报 Jensen——"
                "本拍须 RDC→2（一句即可），然后再 do_nothing。"
            )
        else:
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
