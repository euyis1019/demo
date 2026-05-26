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


def _has_rdc_reply_from(
    world_db: Any,
    *,
    agent_id: int,
    sender_id: int,
    since_t: int,
    t_now: int,
) -> bool:
    """True when ``sender_id`` replied via delivered RDC or executive GRP."""
    try:
        rows = world_db.fetch_arrived_for(int(agent_id), int(t_now), int(since_t) - 1)
    except Exception:  # noqa: BLE001
        return False
    sid = int(sender_id)
    for row in rows:
        if int(getattr(row, "sender_id", -1)) != sid:
            continue
        channel = str(getattr(row, "channel_type", "RDC") or "RDC").upper()
        if channel == "RDC":
            return True
        if channel == "GRP" and int(getattr(row, "group_id", 0) or 0) == 100:
            return True
    return False


def _agent_place(world: Any, agent_id: int) -> str:
    places = getattr(world, "places", None)
    if places is None:
        return ""
    return str(places.L_t(int(agent_id)) or "")


def _move_and_location_hints(agent_id: int, phase: str, place: str) -> List[str]:
    """Discourage verbal 'going to X room' — agent MOVE is IPC-only and ignored."""
    if phase not in ("Phase 1", "Phase 2", "Phase 3"):
        return []
    lines: List[str] = [
        "【位置约束】request_move 被引擎忽略，说了「去某室/会议室」也不会换房间；"
        "你始终待在系统记录的位置，用 RDC/speak_to_local 交流，勿编造移动。"
    ]
    if agent_id == 3 and place == "negotiation_room":
        lines.append(
            "【Tech VP】你在 negotiation_room 验逻辑/回 Jensen 请用 send_message→2，"
            "禁止说「我去私人会议室验代码」——你不会离开谈判室。"
        )
    if agent_id == 1 and phase == "Phase 1" and place == "nvidia_reception":
        lines.append(
            "【前台·转场】收到 Jensen 批准 RDC 后，F2F 说「请跟我来/这边请/私人会议室」"
            "即可；场景切换由系统 routing 处理，勿向玩家解释「系统限制无法移动」。"
        )
    return lines


def _recent_rdc_count(
    world_db: Any,
    *,
    sender_id: int,
    recipient_id: int,
    since_t: int,
    t_now: int,
) -> int:
    try:
        rows = world_db.fetch_rdc_messages(
            sender_id=int(sender_id),
            recipient_id=int(recipient_id),
            since_t=int(since_t),
            t_now=int(t_now),
        )
    except Exception:  # noqa: BLE001
        return 0
    return len(rows)


def _unread_rdc_sender_ids(
    agent_id: int,
    agent: Any,
    world: Any,
    t: int,
    db: Any,
) -> List[int]:
    """Senders with delivered RDC not yet covered by this agent's outbound reply."""
    last = getattr(agent, "last_message_seen_at", None)
    last_seen = -1 if last is None else int(last)
    try:
        rows = db.fetch_arrived_for(int(agent_id), int(t), last_seen)
    except Exception:  # noqa: BLE001
        return []

    senders: List[int] = []
    seen: set[int] = set()
    for row in rows:
        channel = str(getattr(row, "channel_type", "RDC") or "RDC").upper()
        if channel != "RDC":
            continue
        sid = int(getattr(row, "sender_id", -1))
        if sid < 0 or sid in seen:
            continue
        seen.add(sid)
        senders.append(sid)
    return senders


def _rdc_reply_obligation_hints(
    agent_id: int,
    agent: Any,
    world: Any,
    t: int,
    phase: str,
    db: Any,
) -> List[str]:
    """All agents: reply to peer RDC promptly; avoid do_nothing while inbox hot."""
    if db is None or phase == "Phase 4" and int(agent_id) == 3:
        return []

    aid = int(agent_id)
    senders = _unread_rdc_sender_ids(aid, agent, world, int(t), db)
    if not senders:
        return []

    peer_list = "、".join(f"Agent{sid}" for sid in senders)
    lines = [
        "【RDC 必回】你有来自 "
        f"{peer_list} 的未读私信；本拍须 send_message 回复对应 sender，"
        "1–3 句口语。优先于 update_state / do_nothing，勿拖延到下一拍。"
        "同一话题已回过一句后勿复读相同内容。"
    ]

    if aid == 2 and 1 in senders:
        chain_since = max(0, int(t) - 50)
        if _jensen_should_issue_approve(db, since_t=chain_since, t_now=int(t)):
            lines.append(
                "【Jensen·批准】Tech VP 已正面评估——本拍 send_message→1 须含"
                "「私人会议室/这边请/可以见」，并 story_advance(approve_visitor)；"
                "禁止再写「稍等/十分钟」。"
            )
        else:
            lines.append(
                "【Jensen·前台】Agent1 访客通报须 send_message→1 一句回执（稍等/评估），"
                "同一话题只回一次；前台「收到」类消息无需再 RDC。"
            )

    if aid == 1 and 2 in senders:
        lines.append(
            "【前台·Jensen】批准语（私人会议室/这边请）→ send_message→2 确认 + "
            "speak_to_local 请跟我来；「稍等/评估中」→ 只 speak_to_local 转告玩家，"
            "勿 send_message→2 回执。"
        )

    if aid == 3 and 2 in senders:
        lines.append(
            "【VP】Jensen RDC 求证时 send_message→2，含「可行/核武器/理论上成立」之一。"
        )

    if aid == 2 and 3 in senders:
        lines.append("【Jensen】VP 来信时 send_message→3 短句回应技术判断。")

    return lines


def _jensen_reception_spam_hints(
    agent_id: int,
    agent: Any,
    world: Any,
    t: int,
    phase: str,
    db: Any,
) -> List[str]:
    if phase != "Phase 1" or int(agent_id) != 2 or db is None:
        return []

    chain_since = max(0, int(t) - 50)
    approve_hints = _jensen_approve_urgency_hints(
        agent, db, since_t=chain_since, t_now=int(t)
    )
    if approve_hints:
        return approve_hints

    window_start = max(0, int(t) - 12)
    to_reception = _recent_rdc_count(
        db, sender_id=2, recipient_id=1, since_t=window_start, t_now=int(t)
    )
    if to_reception < 1:
        return []

    lines = [
        "【止复读·前台】已向 Agent1 发过「稍等/再等」类 RDC 时，禁止再次 send_message→1 "
        "复读相同催促；改 speak_to_local 与 VP/CEO 谈 HBM，或 send_message→3，或 do_nothing。"
        "（尚未批准访客时，VP 正面评估后仍须 send_message→1 含「私人会议室/这边请」+ story_advance。）"
    ]
    if to_reception >= 2:
        lines.append(
            "【强制】你已多次私信前台「稍等」——本拍禁止再 send_message→1 催等，"
            "须 speak_to_local 或 send_message→3；若 VP 已认可方案则改发批准语 + story_advance。"
        )
    pending = dict(getattr(agent, "_pending_rdc_out", {}) or {})
    if 1 in pending and not _has_rdc_reply_from(
        db, agent_id=2, sender_id=1, since_t=int(pending[1]), t_now=int(t)
    ):
        last_text = str((getattr(agent, "_last_rdc_out_content", {}) or {}).get(1, ""))
        if "私人" in last_text or "会议室" in last_text:
            lines.append(
                "【已下令】前台尚未 RDC 回执时勿重复催；谈判室里先跟 VP 对齐方案。"
            )
    return lines


def _jensen_vp_link_hints(
    agent_id: int,
    agent: Any,
    phase: str,
    world: Any,
    t: int,
    db: Any,
) -> List[str]:
    if phase != "Phase 1" or db is None:
        return []

    aid = int(agent_id)
    window_start = max(0, int(t) - 10)
    jensen_to_vp = _recent_rdc_count(
        db, sender_id=2, recipient_id=3, since_t=window_start, t_now=int(t)
    )
    vp_to_jensen = _recent_rdc_count(
        db, sender_id=3, recipient_id=2, since_t=window_start, t_now=int(t)
    )

    if aid == 2:
        if jensen_to_vp == 0 and _recent_rdc_count(
            db, sender_id=1, recipient_id=2, since_t=window_start, t_now=int(t)
        ) >= 1:
            if _recent_rdc_count(
                db, sender_id=2, recipient_id=1, since_t=window_start, t_now=int(t)
            ) == 0:
                return [
                    "【Jensen 顺序】前台已报访客：本拍须 send_message→1 一句回执，"
                    "再 send_message→3 请 VP 评估（或下一拍 →3）。"
                ]
            return [
                "【Jensen→VP】前台已报访客/技术突破，本拍 send_message→3 请 VP 评估，"
                "并 speak_to_local 与 CEO 谈。"
            ]
        if jensen_to_vp >= 1 and vp_to_jensen == 0:
            return [
                "【等 VP】已向 Tech VP 求证，本拍 speak_to_local 与 CEO 互怼 HBM 或 do_nothing；"
                "禁止再 send_message→1 催前台「稍等」。"
            ]
        if jensen_to_vp == 0 and vp_to_jensen == 0:
            return [
                "【联动 VP】谈判室须与 Tech VP 保持 RDC：可 send_message→3 同步访客/涨价压力，"
                "并 speak_to_local 让 CEO 听到你们在谈。"
            ]
    if aid == 3:
        if vp_to_jensen == 0 and jensen_to_vp >= 1:
            return [
                "【VP 回复】Jensen 已 RDC 求证，本拍须 send_message→2 给技术判断"
                "（可行/核武器/理论上成立），并可 speak_to_local 对同室同事一句。"
            ]
        if jensen_to_vp == 0 and vp_to_jensen == 0:
            return [
                "【联动 Jensen】可 speak_to_local 短句插话 HBM/算力，"
                "或主动 send_message→2 问 Jensen 要不要见访客。"
            ]
    return []


def _reception_jensen_spam_hints(
    agent_id: int,
    phase: str,
    t: int,
    db: Any,
) -> List[str]:
    if phase != "Phase 1" or int(agent_id) != 1 or db is None:
        return []

    chain_since = max(0, int(t) - 50)
    if _has_approve_rdc_to_reception(db, since_t=chain_since, t_now=int(t)):
        return [
            "【已批准·escort】Jensen 已 RDC 批准——本拍 speak_to_local 须含"
            "「请跟我来/这边请/私人会议室」，带玩家去见黄总；"
            "禁止再安抚「稍等/系统限制无法移动」。"
        ]

    window_start = max(0, int(t) - 12)
    to_jensen = _recent_rdc_count(
        db, sender_id=1, recipient_id=2, since_t=window_start, t_now=int(t)
    )
    if to_jensen < 1:
        return []

    return [
        "【已通报】已向 Jensen RDC 汇报访客，本拍 speak_to_local 安抚玩家或 do_nothing，"
        "禁止再 send_message→2 重复催黄总。"
    ]


def _negotiation_room_hints(
    agent_id: int,
    agent: Any,
    world: Any,
    t: int,
    phase: str,
    place: str,
) -> List[str]:
    if phase != "Phase 1" or place != "negotiation_room":
        return []
    if getattr(agent, "player_memory", None):
        return []

    aid = int(agent_id)
    if aid == 2:
        return [
            "【谈判室·Jensen】与 VP、CEO 同室——本拍须 speak_to_local 1–3 句"
            "（HBM 涨价/CEO 串标/访客方案择一），形成可见讨论；"
            "收到前台 RDC 后须先 send_message→1 一句回执，→3 求证；"
            "VP 正面评估后须 send_message→1 含「私人会议室/这边请」并 story_advance(approve_visitor)。"
        ]
    if aid == 3:
        return [
            "【谈判室·VP】与 Jensen/CEO 同室——本拍 speak_to_local 或 send_message→2；"
            "接 Jensen 求证时 1–3 句技术评估，并偶尔 F2F 插话让谈判室有声音。"
        ]
    if aid in (4, 5, 6):
        return [
            "【谈判室·CEO】speak_to_local 1–2 句：涨价/产能/市占，"
            "可点名 Jensen 或 VP，也可与其他 CEO 互呛；勿 RDC 玩家。"
        ]
    return []


def _content_has_keywords(content: str, keywords: tuple[str, ...]) -> bool:
    text = str(content or "")
    return any(kw in text for kw in keywords)


_VP_POSITIVE_RDC_KEYWORDS: Tuple[str, ...] = (
    "可行",
    "核武器",
    "理论上成立",
    "数学上成立",
    "放他进来",
    "值得见",
    "靠谱",
)


def _rdc_row_content(row: Any) -> str:
    if isinstance(row, dict):
        return str(row.get("content") or "")
    try:
        return str(row["content"] or "")
    except (KeyError, TypeError):
        pass
    return str(getattr(row, "content", "") or "")


def _has_approve_rdc_to_reception(db: Any, *, since_t: int, t_now: int) -> bool:
    from agent_world.hbm_demo.features.f05_story_routing.routing_config import (
        approve_keywords,
    )

    try:
        rows = db.fetch_rdc_messages(
            sender_id=2, recipient_id=1, since_t=int(since_t), t_now=int(t_now)
        )
    except Exception:  # noqa: BLE001
        return False
    for row in rows:
        if _content_has_keywords(_rdc_row_content(row), approve_keywords()):
            return True
    return False


def _vp_positive_rdc_to_jensen(db: Any, *, since_t: int, t_now: int) -> bool:
    try:
        rows = db.fetch_rdc_messages(
            sender_id=3, recipient_id=2, since_t=int(since_t), t_now=int(t_now)
        )
    except Exception:  # noqa: BLE001
        return False
    for row in rows:
        if _content_has_keywords(_rdc_row_content(row), _VP_POSITIVE_RDC_KEYWORDS):
            return True
    return False


def _player_f2f_count_at_reception(db: Any, *, since_t: int, t_now: int) -> int:
    try:
        history = db.fetch_f2f_history_at(
            "nvidia_reception", int(t_now), int(since_t)
        )
    except Exception:  # noqa: BLE001
        return 0
    return sum(1 for _at_t, sender_id, _mid, _content in history if int(sender_id) == 0)


def _jensen_node_a_chain_ready(db: Any, *, since_t: int, t_now: int) -> bool:
    return (
        _recent_rdc_count(db, sender_id=1, recipient_id=2, since_t=since_t, t_now=t_now)
        > 0
        and _recent_rdc_count(db, sender_id=2, recipient_id=3, since_t=since_t, t_now=t_now)
        > 0
        and _recent_rdc_count(db, sender_id=3, recipient_id=2, since_t=since_t, t_now=t_now)
        > 0
    )


def _jensen_should_issue_approve(db: Any, *, since_t: int, t_now: int) -> bool:
    if _has_approve_rdc_to_reception(db, since_t=since_t, t_now=t_now):
        return False
    if not _jensen_node_a_chain_ready(db, since_t=since_t, t_now=t_now):
        return False
    return _vp_positive_rdc_to_jensen(db, since_t=since_t, t_now=t_now)


def _jensen_approve_urgency_hints(
    agent: Any,
    db: Any,
    *,
    since_t: int,
    t_now: int,
) -> List[str]:
    if not _jensen_should_issue_approve(db, since_t=since_t, t_now=t_now):
        return []
    ctx = getattr(agent, "_batch_turn_context", None) or {}
    player_turn = int(ctx.get("player_turn", 1))
    player_msgs = _player_f2f_count_at_reception(db, since_t=since_t, t_now=t_now)
    urgency = ""
    if player_turn >= 3 or player_msgs >= 2:
        urgency = "玩家已在前台多次发言等候——"
    return [
        f"【节点 A·必须批准】{urgency}Tech VP 已正面评估访客方案，RDC 链已齐。"
        "本拍须 send_message→1，正文含「私人会议室/这边请/可以见」之一，"
        "并同批调用 story_advance(approve_visitor)。"
        "禁止再写「稍等/十分钟/还在谈」；禁止本拍只 speak_to_local 拖延。"
    ]


def _node_a_progress_hints(
    agent_id: int,
    agent: Any,
    phase: str,
    db: Any,
    t: int,
    *,
    mem: Any,
) -> List[str]:
    """Phase 1 soft checklist toward node A (prompt-only, reads world.db)."""
    if phase != "Phase 1" or db is None:
        return []

    from agent_world.hbm_demo.features.f05_story_routing.routing_config import (
        approve_keywords,
        escort_keywords,
        is_story_advance_enabled,
    )
    from agent_world.hbm_demo.features.f05_story_routing.story_signals import (
        has_story_signal,
    )

    since_t = max(0, int(t) - 50)
    tick = int(t)
    aid = int(agent_id)

    if is_story_advance_enabled() and has_story_signal(
        db, "approve_visitor", since_t=since_t, t_now=tick
    ):
        return []

    has_1_2 = (
        _recent_rdc_count(
            db, sender_id=1, recipient_id=2, since_t=since_t, t_now=tick
        )
        > 0
    )
    has_2_3 = (
        _recent_rdc_count(
            db, sender_id=2, recipient_id=3, since_t=since_t, t_now=tick
        )
        > 0
    )
    has_3_2 = (
        _recent_rdc_count(
            db, sender_id=3, recipient_id=2, since_t=since_t, t_now=tick
        )
        > 0
    )

    has_approve_rdc = _has_approve_rdc_to_reception(db, since_t=since_t, t_now=tick)
    vp_positive = _vp_positive_rdc_to_jensen(db, since_t=since_t, t_now=tick)

    has_escort = False
    try:
        history = db.fetch_f2f_history_at("nvidia_reception", tick, since_t)
    except Exception:  # noqa: BLE001
        history = []
    for _at_t, sender_id, _mid, content in history:
        if int(sender_id) != 1:
            continue
        if _content_has_keywords(str(content or ""), escort_keywords()):
            has_escort = True
            break

    lines: List[str] = []

    if aid == 1:
        if mem and not has_1_2:
            lines.append(
                "【节点 A·第1步】已/将 F2F 回应玩家后，本批仍须 send_message→2 向 Jensen "
                "简报访客与 HBM/显存方案（不可只 F2F 不 RDC）。"
            )
        elif has_approve_rdc and not has_escort:
            lines.append(
                "【节点 A·前台 escort】Jensen 已 RDC 批准——本拍 speak_to_local 须含"
                "「请跟我来/这边请/私人会议室」，带玩家去见黄总。"
            )
        elif has_1_2 and not has_approve_rdc:
            lines.append(
                "【节点 A·等候】已向 Jensen 简报——speak_to_local 安抚玩家稍等；"
                "收到批准 RDC 后再 escort，勿重复 RDC→2。"
            )

    if aid == 2:
        if has_1_2 and not has_2_3:
            lines.append(
                "【节点 A·第2步】前台已报访客——本拍 send_message→1 一句回执，"
                "并 send_message→3 请 Tech VP 评估（可同批连发）。"
            )
        elif has_2_3 and has_3_2 and not has_approve_rdc and not vp_positive:
            lines.append(
                "【节点 A·第3步】VP 已回 RDC——若评估正面，本拍 send_message→1 批准语"
                "（须含「私人会议室/这边请/可以见」），然后 story_advance(approve_visitor)。"
            )
        elif has_approve_rdc:
            lines.append(
                "【节点 A·推进 Phase 2】批准 RDC 已发——本拍或下一拍须调用 "
                "story_advance(approve_visitor)；勿再 send_message→1 复读批准。"
            )

    if aid == 3 and has_2_3 and not has_3_2:
        lines.append(
            "【节点 A·VP】Jensen 已 RDC 求证——本拍 send_message→2，1–3 句技术判断"
            "（含「可行/核武器/理论上成立」之一）。"
        )

    return lines


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
