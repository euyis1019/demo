"""好感度相关的全部软引导文本（原 affinity/manager.py 内嵌，W6 集中至 prompts）。

包含：5 档等级文案、adjust_affinity 私有工具 schema、第 6 段提示词的
标题/收尾/条件自省提醒。取数与拼装逻辑仍在 affinity/manager.py。
"""

from __future__ import annotations

from typing import Any, Dict

# 5 档阈值与行为指引（集中一处，调档只改这里）——guide 文本会被
# manager._render_suffix 直接拼进第 6 段提示词
LEVELS = [
    (80, "挚友", "无话不谈，可以交心、可以托付事情"),
    (60, "亲密", "很信任对方，主动关心，愿意分享心里话"),
    (40, "友好", "当朋友处，主动攀谈，愿意帮些小忙"),
    (20, "熟悉", "脸熟了，正常来往，话比对陌生人多些"),
    (0,  "陌生", "还不熟，客气但保持距离，不交浅言深"),
]

# 私有工具 schema（追加进 NPC 的 tools；引擎不认识它，必须前置拦截——
# 见 agents/npc.py private_tool_names 协议）
ADJUST_AFFINITY_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "adjust_affinity",
        "description": (
            "（内心活动，别人看不见）你对每个人的观感**只有你自己会更新**——"
            "系统不会替你变心。每拍留意：刚才的对话/举动有没有让你对谁的看法"
            "起变化？哪怕一点点（愉快的寒暄 +1、被照顾 +2、被冒犯 -2、"
            "真正暖心或伤人的事 ±3 以上），就顺手调用本工具记一笔；"
            "毫无波澜则不调。可以和说话等动作同拍使用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target": {"type": "integer", "description": "对方 agent_id"},
                "delta": {"type": "integer", "description": "好感变化，-3 到 +5"},
                "reason": {"type": "string", "description": "一句话原因（内心记一笔）"},
            },
            "required": ["target", "delta"],
            "additionalProperties": False,
        },
    },
}

# ---- 第 6 段提示词文本件（manager._render_suffix 拼装）---------------------

SUFFIX_HEADER = "# 我对在场各人的态度（依此把握语气与主动程度，别直接念数字）"

SUFFIX_FOOTER = (
    "这些态度只会因你自己调用 adjust_affinity 而变化——系统不会替你变心。"
)

# 条件化自省提醒：仅在 NPC 真的收到话时渲染（W3 审计：无条件每拍渲染
# 属空泛诱导，禁止改成常驻）
REFLECT_REMINDER = (
    "⚖ 你这一拍收到了别人的话——回应之前先自问：这话有没有让你"
    "对说话人的观感起变化（暖心/冒犯/可靠/失望…）？**有就先调用"
    " adjust_affinity 记一笔（可与说话等动作同拍并用），再回应**；"
    "真的毫无波澜才略过。同一件事只记一次——往拍已记过分的旧话，"
    "别因为还看得见就反复计。"
)


def render_attitude_line(who: str, is_player: bool, level: str, score: int, guide: str) -> str:
    """第 6 段逐人行：『- 名字（玩家）：等级 score/100 —— 指引』"""
    tag = "（玩家）" if is_player else ""
    return f"- {who}{tag}：{level} {score}/100 —— {guide}"
