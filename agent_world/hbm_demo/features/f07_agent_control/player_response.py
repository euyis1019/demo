"""F07 L6 — player-centric response constraint templates."""

from __future__ import annotations

from typing import Optional

from agent_world.hbm_demo.features.f07_agent_control.config import (
    is_experience_hardening,
)

_AGENT_NAMES = {
    1: "接待前台",
    2: "Jensen Hwang",
    3: "Tech VP",
    4: "SK Hynix CEO",
    5: "Micron CEO",
    6: "Samsung CEO",
    7: "Sam Altman",
}

_NVIDIA_IDS = {2, 3}
_CEO_IDS = {4, 5, 6}

_PHASE_OUTPUT_HINTS = {
    "Phase 1": "1–3 句口语",
    "Phase 2": "2–4 句口语",
    "Phase 3": "2–5 句，可略长但须引用玩家观点",
    "Phase 4": "1–3 句，一句一句来",
}


def agent_display_name(agent_id: int) -> str:
    return _AGENT_NAMES.get(int(agent_id), f"Agent {agent_id}")


def _phase_agent_extra(*, agent_id: int, phase: str, player_turn: int) -> str:
    """Phase/agent-specific L6 bullets (§8.2 / F07-C)."""
    aid = int(agent_id)
    lines: list[str] = []

    if aid == 1 and phase == "Phase 1":
        lines.append(
            "★ 在前台必须用 speak_to_local 先回应玩家，再 send_message RDC→Jensen。"
        )
        if is_experience_hardening():
            lines.append(
                "★ 本 Turn 唯一权威输入是下方「玩家说：…」——必须优先回应该句。"
                "禁止复读上一 Turn 或 notification 中的旧话题，除非玩家本句明确延续。"
            )
            lines.append(
                "★ 若玩家明显闲聊/玩梗（无技术/见黄总诉求）：speak_to_local 礼貌回应即可，"
                "勿 send_message→Jensen；可说「您要是想谈技术方案，我可以帮您通报。」"
            )

    if phase == "Phase 2" and aid == 2:
        lines.append(
            "★ 私密审查：每轮先 speak_to_local 回应玩家（质疑/追问/认可），"
            "再 update_state 或 RDC→Tech VP(3) 求证；外面 CEO 在等，勿长篇。"
        )

    if phase == "Phase 2" and aid == 3:
        lines.append(
            "★ 被动回复 Jensen RDC：仅 send_message→2，1–3 句技术评估。"
            "正面须含「可行」「核武器」「理论上成立」之一以助节点 B。"
        )

    if phase == "Phase 3" and aid in _NVIDIA_IDS:
        lines.append(
            "★ NVIDIA 阵营：帮玩家圆场、压 CEO 价；必须引用玩家 inject 中的"
            "技术词/数字/框架，不可自说自话或帮 CEO 攻击玩家。"
        )

    if phase == "Phase 3" and aid in _CEO_IDS:
        lines.append(
            "★ CEO 进攻方：用产能/市占/ fear premium 攻击玩家方案；"
            "可 send_to_group→200 密谋，但不得帮 NVIDIA 说话。"
        )

    if phase == "Phase 3" and player_turn >= 16 and aid == 7:
        lines.append(
            "★ Turn 16+ Sam 搅局：仅 RDC 煽风点火，抬高 HBM/AMD 话题热度，"
            "禁止 MOVE；短句挑衅，不替玩家或 Jensen 做决定。"
        )

    if phase == "Phase 3" and player_turn == 16:
        lines.append(
            "★ Turn 16 彭博 AMD 快讯已广播：谈判节奏被打断，"
            "Jensen/VP 应帮玩家把 AMD 新闻转译为 NVIDIA 需要降 HBM 方案的理由。"
        )

    if phase == "Phase 4" and aid == 2:
        lines.append(
            "★ 终局 1v1：先回应玩家每句（复述或引用关键词），再谈 offer；"
            "禁止开场长篇独白；Tech VP 在室旁听但不出声。"
        )

    return "\n".join(lines)


def format_l6_player_directive(
    *,
    agent_id: int,
    phase: str,
    player_turn: int,
    player_text: str,
) -> str:
    """Build the L6 constraint block (80–120 字目标)."""
    role = agent_display_name(agent_id)
    output_hint = _PHASE_OUTPUT_HINTS.get(phase, "1–3 句口语")
    extra = _phase_agent_extra(
        agent_id=agent_id, phase=phase, player_turn=player_turn
    )
    if extra:
        extra = extra + "\n"
    return (
        f"【系统约束·{phase} Turn {player_turn}】\n"
        f"★ 角色扮演：你是{role}。下面【世界态】【剧情】【你的目标】务必读完再行动。\n"
        f"★ 本拍必须先直接回应玩家下面这句话（复述或引用关键词），再考虑 RDC/其他动作。\n"
        f"★ 你【说出口】的内容：{output_hint}，禁止演讲腔；上下文详 ≠ 你可以长篇大论。\n"
        f"{extra}"
        f"★ 禁止：替其他角色做决定、无关议题、本阶段禁止的 MOVE/GRP。\n"
        f"\n玩家说：「{player_text.strip()}」"
    )


def format_notification_directive(
    *,
    phase: str,
    player_turn: int,
    agent_id: Optional[int] = None,
) -> str:
    """Shorter header for scripted_notification (no player verbatim)."""
    header = (
        f"【剧本通知·{phase} Turn {player_turn}】\n"
        "以下是世界态与你的角色目标摘要。你看不到玩家原话；"
    )
    aid = int(agent_id) if agent_id is not None else 0
    if is_experience_hardening() and phase == "Phase 1" and aid in (2, 3):
        return (
            header
            + "你只能依据「前台 RDC」与「本 Turn 摘要」行动；"
            "禁止编造未在 RDC/摘要中出现的公司名、数据、roadmap。\n"
        )
    if phase == "Phase 2" and aid == 3:
        return (
            header
            + "仅当收到 Jensen(2) 的未读 RDC 时你才被动 tick；"
            "用 send_message 回复 Jensen，1–3 句技术评估，"
            "正面关键词：可行 / 核武器 / 理论上成立。\n"
        )
    if phase == "Phase 3" and aid in _CEO_IDS:
        return (
            header
            + "通过同室 F2F 或 group 200 感知局势；攻击玩家方案，"
            "不帮 NVIDIA 阵营说话。\n"
        )
    return (
        header + "若需了解玩家说了什么，请等待同阵营同事 RDC 转发。\n"
    )
