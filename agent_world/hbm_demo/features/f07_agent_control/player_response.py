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

_PHASE_OUTPUT_HINTS = {
    "Phase 1": "1–3 句口语",
    "Phase 2": "2–4 句口语",
    "Phase 3": "2–5 句，可略长但须引用玩家观点",
    "Phase 4": "1–3 句，一句一句来",
}


def agent_display_name(agent_id: int) -> str:
    return _AGENT_NAMES.get(int(agent_id), f"Agent {agent_id}")


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
    extra = ""
    if agent_id == 1 and phase == "Phase 1":
        extra = "★ 在前台必须用 speak_to_local 先回应玩家，再考虑 send_message 向 Jensen 汇报。\n"
    return (
        f"【系统约束·{phase} Turn {player_turn}】\n"
        f"★ 角色扮演：你是{role}。下面【世界态】【剧情】【你的目标】务必读完再行动。\n"
        f"★ 本拍必须先直接回应玩家下面这句话（复述或引用关键词），再考虑 RDC/其他动作。\n"
        f"★ 你【说出口】的内容：{output_hint}，禁止演讲腔；上下文详 ≠ 你可以长篇大论。\n"
        f"{extra}"
        f"★ 禁止：替其他角色做决定、无关议题、本阶段禁止的 MOVE/GRP。\n"
        f"\n玩家说：「{player_text.strip()}」"
    )


def format_notification_directive(*, phase: str, player_turn: int) -> str:
    """Shorter header for scripted_notification (no player verbatim)."""
    return (
        f"【剧本通知·{phase} Turn {player_turn}】\n"
        "以下是世界态与你的角色目标摘要。你看不到玩家原话；"
        "若需了解玩家说了什么，请等待同阵营同事 RDC 转发。\n"
    )
