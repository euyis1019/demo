"""F07 conversation — per-agent F2F / RDC-reply / anti-spam / location hints.

Reads world.db through ``conversation.queries`` and reuses the node-A urgency
hint from ``conversation.batch_rules``; returns prompt lines.
"""

from __future__ import annotations

from typing import Any, List

from agent_world.hbm_demo.features.f07_agent_control.conversation.batch_rules import (
    _jensen_approve_urgency_hints,
)
from agent_world.hbm_demo.features.f07_agent_control.conversation.queries import (
    _has_approve_rdc_to_reception,
    _has_rdc_reply_from,
    _jensen_should_issue_approve,
    _recent_rdc_count,
    _unread_rdc_sender_ids,
)


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
