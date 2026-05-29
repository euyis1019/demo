"""F07 — soft conversation pacing for the SBTI clinic story."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent_world.hbm_demo.features.f07_agent_control.config import load_turn_control


def resolve_world_db(world: Any) -> Any:
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
    return any(int(sender_id) != int(agent_id) for at_tick, sender_id, _mid, _content in f2f if int(at_tick) > last_seen)


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
    if not dispatch_result:
        return
    name = _action_name(action_type)
    recorded_attempt = bool(
        dispatch_result.get("success")
        or dispatch_result.get("message_id") is not None
        or dispatch_result.get("recipients") is not None
    )
    if name in ("speak_to_local", "send_message", "send_to_group") and recorded_attempt:
        mem = getattr(agent, "player_memory", None)
        if mem is not None and hasattr(mem, "clear") and mem:
            mem.clear()
        setattr(agent, "_inject_responded", True)  # noqa: SLF001
        if hasattr(agent, "last_message_seen_at"):
            agent.last_message_seen_at = int(t)
    if name == "send_message" and dispatch_result.get("success"):
        target = action_kwargs.get("target")
        if target is not None:
            pending: Dict[int, int] = dict(getattr(agent, "_pending_rdc_out", {}) or {})
            pending[int(target)] = int(t)
            agent._pending_rdc_out = pending  # noqa: SLF001


def _agent_place(world: Any, agent_id: int) -> str:
    places = getattr(world, "places", None)
    if places is None:
        return ""
    return str(places.L_t(int(agent_id)) or "")


def _unread_rdc_sender_ids(agent_id: int, agent: Any, world: Any, t: int, db: Any) -> List[int]:
    last = getattr(agent, "last_message_seen_at", None)
    last_seen = -1 if last is None else int(last)
    try:
        rows = db.fetch_arrived_for(int(agent_id), int(t), last_seen)
    except Exception:  # noqa: BLE001
        return []
    senders: List[int] = []
    seen: set[int] = set()
    for row in rows:
        if str(getattr(row, "channel_type", "RDC") or "RDC").upper() != "RDC":
            continue
        sid = int(getattr(row, "sender_id", -1))
        if sid >= 0 and sid not in seen:
            seen.add(sid)
            senders.append(sid)
    return senders


def build_conversation_hints(agent_id: int, agent: Any, world: Any, t: int) -> str:
    lines: List[str] = []
    db = resolve_world_db(world)
    aid = int(agent_id)
    ctx = getattr(agent, "_batch_turn_context", None)
    phase = str(ctx.get("phase") or "") if isinstance(ctx, dict) else ""
    place = _agent_place(world, aid)

    lines.append(
        "【世界约束】这是《暗黑心理诊所》SBTI 测试故事；不要出现旧商务剧情、公司、价格、产品推销等内容。"
    )
    lines.append(
        "【位置约束】request_move 被引擎忽略；场景切换由 story_advance/routing 处理，台词里不要编造自己已经换房。"
    )

    if aid == 1 and phase == "Phase 1" and place == "nvidia_reception":
        lines.append(
            "【前台】玩家进入测试主线后，F2F 短回应并 send_message→2 汇报 Morgen；收到批准后说「这边请」。"
        )
    if aid == 2 and phase == "Phase 1":
        lines.append(
            "【Morgen】收到前台汇报后，先向黑猫记录样本，再批准前台带玩家进来，并 story_advance(approve_visitor)。"
        )
    if aid == 2 and phase == "Phase 2":
        lines.append(
            "【四题测试】围绕派对、在吗、团建、透明药水推进；每次回应都要回收玩家此前选择。"
        )
    if aid == 2 and phase == "Phase 3":
        lines.append(
            "【身份反转】完成实验体真相、透明化预览和社死任务后，让异常角色退场并 story_advance(expel_ceos)。"
        )

    has_player_memory = bool(getattr(agent, "player_memory", None))
    if db is not None and has_unread_inbound(aid, agent, world, int(t)):
        lines.append("【收件箱】未读 RDC 本拍须 send_message 回复；同室 F2F 可用 speak_to_local 回应。")
        if has_player_memory:
            lines.append("【玩家优先】本拍有玩家同室发言，先 speak_to_local 回玩家；RDC 不得抢掉玩家回复。")
        for sid in _unread_rdc_sender_ids(aid, agent, world, int(t), db):
            lines.append(f"【私信回复】Agent{sid} 的 RDC 等待回复，本拍 send_message→{sid}。")

    mem = getattr(agent, "player_memory", None)
    if mem:
        lines.append("【玩家选择】本批尚未完成首次回应；回应后不要反复复读同一句。")
    elif getattr(agent, "_inject_responded", False) and not has_unread_inbound(aid, agent, world, int(t)):
        lines.append("【本批已回应】无新消息时不要刷屏，可 do_nothing。")

    return "\n".join(lines)


__all__ = [
    "build_conversation_hints",
    "has_unread_inbound",
    "inject_response_ticks",
    "mark_communication_action",
    "primary_notify_ticks",
    "resolve_world_db",
]
