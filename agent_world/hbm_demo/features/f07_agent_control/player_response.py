"""F07 L6 — player-centric response constraint templates for the SBTI clinic."""

from __future__ import annotations

from typing import Optional

_AGENT_NAMES = {
    1: "诊所前台",
    2: "Dr. Morgen",
    3: "黑猫",
    4: "老式收音机",
    5: "倒计时钟",
    6: "SUBJECT-0",
    7: "最近联系人",
}

_PHASE_OUTPUT_HINTS = {
    "Phase 1": "1–3 句口语",
    "Phase 2": "1–3 句，必须回收玩家选择",
    "Phase 3": "1–4 句，悬疑和黑色幽默并行",
    "Phase 4": "1–3 句，一句一句做最终诊断",
}


def agent_display_name(agent_id: int) -> str:
    return _AGENT_NAMES.get(int(agent_id), f"Agent {agent_id}")


def _phase_agent_extra(*, agent_id: int, phase: str, player_turn: int) -> str:
    aid = int(agent_id)
    lines: list[str] = [
        "★ 若玩家本拍同室发言，先 speak_to_local 回应玩家；未读 RDC 只能在不抢玩家回复时处理。",
        "★ 不解释底层框架；让玩家通过台词感到「我的选择真的被记住了」。",
    ]

    if aid == 1 and phase == "Phase 1":
        lines.extend(
            [
                "★ 前台先用 speak_to_local 回应玩家，再 send_message→2 汇报 Morgen。",
                "★ 收到 Morgen 批准后，F2F 须含「这边请 / Morgen医生等你 / 别盯着倒计时钟」。",
                "★ 玩家尚未发言时，只能一句欢迎，禁止 RDC、禁止赶客。",
            ]
        )

    if aid == 2 and phase == "Phase 1":
        lines.append(
            "★ 收到前台汇报后，send_message→3 请黑猫记录样本，再 send_message→1 批准，随后 story_advance(approve_visitor)。"
        )

    if aid == 2 and phase == "Phase 2":
        lines.append(
            "★ 主持 SBTI 四题：派对、在吗、团建、透明药水；每题都要引用前面至少一次选择。"
        )
        lines.append(
            "★ 四题完成后，F2F 说「去测评间，看你的透明化预览」，再 story_advance(return_to_negotiation)。"
        )

    if aid == 3:
        lines.append("★ 你是黑猫，只吐槽，不科普；越短越准。")

    if phase == "Phase 3":
        if aid == 2:
            lines.append(
                "★ 身份反转、透明化预览、社死任务后，让异常角色退到候诊区并 story_advance(expel_ceos)。"
            )
        if aid == 4:
            lines.append("★ 你负责播报「你欠我五块钱」社死任务，语气像信号不好的老电台。")
        if aid == 6:
            lines.append("★ 用碎片化闪回制造 SUBJECT-0 悬念，不完整解释真相。")
        if aid == 7 and player_turn >= 16:
            lines.append("★ 你是最近联系人，只用微信弹窗式短句给 Morgen 施压。")

    if phase == "Phase 4" and aid == 2:
        lines.append("★ 终局只做 SBTI 归档和结尾钩子，禁止替玩家做选择。")

    return "\n".join(lines)


def format_opening_directive(
    *,
    agent_id: int,
    phase: str,
    player_turn: int,
) -> str:
    role = agent_display_name(agent_id)
    if int(agent_id) == 1 and phase == "Phase 1":
        return (
            f"【开场·{phase} Turn {player_turn}】\n"
            f"★ 角色扮演：你是{role}。玩家尚未开口。\n"
            "★ 本拍唯一任务：speak_to_local 仅一句欢迎，例如「欢迎来到暗黑心理诊所，你还有23小时47分。」\n"
            "★ 禁止：第二句追问、赶客、RDC、update_state、解释机制。\n"
        )
    return ""


def format_l6_player_directive(
    *,
    agent_id: int,
    phase: str,
    player_turn: int,
    player_text: str,
) -> str:
    role = agent_display_name(agent_id)
    output_hint = _PHASE_OUTPUT_HINTS.get(phase, "1–3 句口语")
    extra = _phase_agent_extra(agent_id=agent_id, phase=phase, player_turn=player_turn)
    return (
        f"【系统约束·{phase} Turn {player_turn}】\n"
        f"★ 角色扮演：你是{role}。下面【世界态】【剧情】【你的目标】务必读完再行动。\n"
        "★ 本拍必须先直接回应玩家下面这句话，复述或引用关键词。\n"
        "★ 台词风格：黑色幽默、短句、大白话；不要科普系统，不要讲旧剧情。\n"
        f"★ 你【说出口】的内容：{output_hint}；上下文详 ≠ 可以长篇大论。\n"
        f"{extra}\n"
        "★ 禁止：替其他角色做决定、无关议题、本阶段禁止的 MOVE/GRP。\n"
        f"\n玩家说：「{player_text.strip()}」"
    )


def inject_channel_uses_player_f2f(phase: str) -> bool:
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
    role = agent_display_name(agent_id)
    output_hint = _PHASE_OUTPUT_HINTS.get(phase, "1–3 句口语")
    extra = _phase_agent_extra(agent_id=agent_id, phase=phase, player_turn=player_turn)
    return (
        f"【系统约束·F2F 通道·{phase} Turn {player_turn}】\n"
        f"★ 角色扮演：你是{role}。玩家已在同室 F2F 发言，请从近期对话摘要读取并回应。\n"
        "★ 必须引用玩家最新发言或此前选择，体现诊所记忆。\n"
        "★ 台词风格：黑色幽默、短句、大白话；不要科普系统，不要讲旧剧情。\n"
        f"★ 你【说出口】的内容：{output_hint}。\n"
        f"{extra}\n"
        "★ 禁止：替其他角色做决定、无关议题、本阶段禁止的 MOVE/GRP。\n"
    )


def format_notification_directive(
    *,
    phase: str,
    player_turn: int,
    agent_id: Optional[int] = None,
) -> str:
    aid = int(agent_id) if agent_id is not None else 0
    role = agent_display_name(aid)
    return (
        f"【剧本通知·{phase} Turn {player_turn}】\n"
        f"你是{role}。以下是世界态与你的角色目标摘要；你可能看不到玩家原话。\n"
        "收到其他 Agent 的 RDC 私信时须 send_message 回复（1–3 句）；同室可用 speak_to_local。\n"
        "保持《暗黑心理诊所》SBTI 黑色幽默，不要回到旧剧情。\n"
    )
