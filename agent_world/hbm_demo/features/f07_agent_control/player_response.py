"""F07 L6 — player-centric response constraint templates."""

from __future__ import annotations

from typing import Optional

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
    lines: list[str] = [
        "★ 收到其他 Agent 的 RDC 私信时，本拍须 send_message 回复对方（1–3 句），"
        "优先于 do_nothing / update_state；同一话题勿重复刷屏。"
    ]

    if aid == 1 and phase == "Phase 1":
        lines.append(
            "★ 在前台必须用 speak_to_local 先回应玩家，再 send_message RDC→Jensen。"
        )
        lines.append(
            "★ F2F 回应后同批或下一拍须 RDC→2 简报（节点 A 第1步）；禁止只 F2F 不 RDC。"
        )
        lines.append(
            "★ 每句玩家 inject 必须由你自己 speak_to_local 回应；禁止沉默或只发 RDC 不 F2F。"
        )
        lines.append(
            "★ 开局（玩家尚未 inject）仅允许一句欢迎 F2F，说完 do_nothing 等玩家开口；"
            "禁止无输入时赶客或 RDC→Jensen。"
        )
        lines.append(
            "★ 收到 Jensen 批准 RDC 后须 F2F 转告玩家去私人会议室（请跟我来），"
            "叙事上在 Jensen story_advance 之前完成。"
        )
        lines.append(
            "★ Jensen 的「稍等/评估中」RDC 只需 speak_to_local 转告玩家，"
            "禁止 send_message→2 回执（会触发黄总复读）。"
        )

    if phase == "Phase 1" and aid == 2:
        lines.append(
            "★ Phase 1 节点 A 链：前台 RDC→你 send_message→1 回执→send_message→3 请 VP→"
            "send_message→1 批准语（私人会议室/这边请）→ story_advance(approve_visitor)。"
            "禁止对玩家 speak_to_local。"
        )
        lines.append(
            "★ 对前台访客通报只 RDC→1 回执一次（稍等/评估）；VP 回评估后须批准 RDC + story_advance。"
        )

    if phase == "Phase 2" and aid == 2:
        lines.append(
            "★ 私密审查：每轮先 speak_to_local 用大白话回应玩家（从同室 F2F 读原话），"
            "再 update_state 或 RDC→Tech VP(3) 求证；外面 CEO 在等，勿长篇。"
        )
        lines.append(
            "★ 认可方案后：先 F2F 告知玩家「回谈判室/进谈判室/方案可行」，"
            "同批或下一拍 story_advance(return_to_negotiation)。"
            "禁止未 F2F 玩家就直接 signal；禁止只说「走」却不 signal。"
        )

    if phase == "Phase 2" and aid == 3:
        lines.append(
            "★ 被动回复 Jensen RDC：仅 send_message→2，1–3 句评估；用 Jensen 听得懂的话，"
            "正面须含「可行」「核武器」「理论上成立」之一以助节点 B。"
        )

    if aid in (2, 3, 4, 5, 6, 7):
        lines.append(
            "★ 通俗表达：对玩家 F2F 用大白话，禁止论文腔和英文缩写堆砌；"
            "技术词最多 1 个且须紧跟白话解释。"
        )

    if phase == "Phase 3" and aid in _NVIDIA_IDS:
        lines.append(
            "★ NVIDIA 阵营：帮玩家圆场、压 CEO 价；必须用大白话引用玩家 F2F 中的"
            "数字/说法，不可自说自话或帮 CEO 攻击玩家。"
        )
        if aid == 2:
            lines.append(
                "★ Jensen 清场：F2F/RDC 驱逐 CEO（请离场/请出去/谈完了/你们先出去）后，"
                "同批或下一拍 story_advance(expel_ceos)。"
            )

    if phase == "Phase 3" and aid in _CEO_IDS:
        lines.append(
            "★ CEO 进攻方：用涨价/交货慢/有钱买不到货等大白话攻击玩家方案；"
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


def format_opening_directive(
    *,
    agent_id: int,
    phase: str,
    player_turn: int,
) -> str:
    """L6-style header for pre-player opening beat (no inject yet)."""
    role = agent_display_name(agent_id)
    if int(agent_id) == 1 and phase == "Phase 1":
        return (
            f"【开场·{phase} Turn {player_turn}】\n"
            f"★ 角色扮演：你是{role}。玩家尚未开口（本世界尚无 inject）。\n"
            f"★ 本拍唯一任务：speak_to_local **仅一句**简短欢迎"
            f"（如「欢迎来到 NVIDIA，有什么可以帮您？」）。\n"
            f"★ 禁止：第二句追问、预约登记、赶客、打发、RDC→Jensen、update_state。\n"
            f"★ 说完欢迎后静默等玩家——勿假设玩家已说话或已拒绝。\n"
        )
    return ""


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
        f"★ 收到他人 RDC 私信时须 send_message 回复对方，优先于 do_nothing。\n"
        f"★ 你【说出口】的内容：{output_hint}，大白话、禁止演讲腔；上下文详 ≠ 你可以长篇大论。\n"
        f"{extra}"
        f"★ 禁止：替其他角色做决定、无关议题、本阶段禁止的 MOVE/GRP。\n"
        f"\n玩家说：「{player_text.strip()}」"
    )


def inject_channel_uses_player_f2f(phase: str) -> bool:
    """Phase 2+ with F08: player text is in world.db F2F (sender=0), not inject verbatim."""
    from agent_world.hbm_demo.features.f08_virtual_player.config import is_f08_enabled

    if not is_f08_enabled():
        return False
    return str(phase) in ("Phase 2", "Phase 3", "Phase 4")


def format_f2f_aware_inject_directive(
    *,
    agent_id: int,
    phase: str,
    player_turn: int,
) -> str:
    """L6 for Phase 2+ — no duplicate「玩家说」; NPC reads co-located F2F thread."""
    role = agent_display_name(agent_id)
    output_hint = _PHASE_OUTPUT_HINTS.get(phase, "1–3 句口语")
    extra = _phase_agent_extra(
        agent_id=agent_id, phase=phase, player_turn=player_turn
    )
    if extra:
        extra = extra + "\n"
    return (
        f"【系统约束·F2F 通道·{phase} Turn {player_turn}】\n"
        f"★ 角色扮演：你是{role}。下面【世界态】【剧情】【你的目标】务必读完再行动。\n"
        f"★ 玩家已在同室 F2F 发言（sender=玩家）；本 inject 不含玩家原话。"
        f"请从【近期对话摘要】或 tick 内 F2F 历史读取并回应（复述或引用关键词）。\n"
        f"★ 收到他人 RDC 私信时须 send_message 回复对方，优先于 do_nothing。\n"
        f"★ 你【说出口】的内容：{output_hint}，大白话、禁止演讲腔；上下文详 ≠ 你可以长篇大论。\n"
        f"{extra}"
        f"★ 禁止：替其他角色做决定、无关议题、本阶段禁止的 MOVE/GRP。\n"
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
    if phase == "Phase 1" and aid == 2:
        return (
            header
            + "节点 A：前台 RDC→你回执→你 RDC→VP 评估→批准 RDC→前台 escort→"
            "story_advance(approve_visitor)。收到前台 RDC 后本批须 send_message→1 与 →3。\n"
        )
    if phase == "Phase 1" and aid == 3:
        return (
            header
            + "节点 A：Jensen RDC 求证时 send_message→2，1–3 句技术评估"
            "（可行/核武器/理论上成立）；否则 speak_to_local 插话。\n"
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
            "不帮 NVIDIA 阵营说话。收到 RDC 私信须 send_message 回复。\n"
        )
    if phase == "Phase 4" and aid == 3:
        return header + "本 Phase 旁听 silent_observer，禁止任何输出。\n"
    return (
        header
        + "收到其他 Agent 的 RDC 私信时须 send_message 回复（1–3 句）；"
        "同室可用 speak_to_local。勿对同一话题重复刷屏。\n"
    )
