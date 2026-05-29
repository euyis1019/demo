"""F07 conversation — node-A / approve-batch prompt hints (Phase 1 chain).

Reads world.db only through ``conversation.queries``; returns prompt lines.
"""

from __future__ import annotations

from typing import Any, List

from agent_world.hbm_demo.features.f07_agent_control.conversation.queries import (
    _content_has_keywords,
    _has_approve_rdc_to_reception,
    _jensen_should_issue_approve,
    _player_f2f_count_at_reception,
    _recent_rdc_count,
    _vp_positive_rdc_to_jensen,
)


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
