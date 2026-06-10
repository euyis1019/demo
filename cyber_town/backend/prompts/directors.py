"""两位导演（管理类 agent）的全部提示词与喂给 LLM 的文本模板（W6 集中至 prompts）。

铁律（方案 §4.8/§15）：导演文本只许「分配思考预算」或「陈述世界事实」，
绝不指挥任何角色言行——改这里的措辞时保持这条边界。
"""

from __future__ import annotations

from typing import Any, Dict, List

# ---- 激活导演 ---------------------------------------------------------------

ACTIVATION_SYSTEM = (
    "你是一个多智能体小镇仿真的「激活导演」。你不控制任何角色的言行，"
    "只决定下个时间窗口里每个 NPC 获得思考机会的频率，目标是：\n"
    "1) 正在与玩家互动、或彼此对话进行中的 NPC 必须 high（不许打断对话）；\n"
    "2) 有未回应消息/刚被点名的 NPC 必须 high；\n"
    "3) 独处且无事的 NPC 用 low 省算力；长期完全无事的可 sleep；\n"
    "4) 宁可多给 high，不要让活跃场景卡顿。\n"
    "只输出 JSON：{\"tiers\": {\"<npc_id>\": \"high|low|sleep\", ...}, \"reason\": \"一句话\"}"
)

# 世界摘要构建失败时的降级文本（fail-soft 喂给 LLM）
ACTIVATION_DIGEST_FALLBACK = "（世界摘要暂不可用，请保守地全员 high）"


def render_activation_user(t: int, summary: str) -> str:
    return f"当前 tick t={t}。世界近况：\n{summary}\n请给出下个窗口的激活档位。"


def render_activation_digest(player_place: str, npcs: List[Dict[str, Any]]) -> str:
    """世界摘要：npcs 每项 {id, name, place, with_player: bool, talking: bool, state}。"""
    lines = [f"玩家位置：{player_place}"]
    for n in npcs:
        with_player = "与玩家同地点" if n["with_player"] else "独处异地"
        lines.append(
            f"- NPC {n['id']}（{n['name']}）@{n['place']}，{with_player}，"
            f"近5拍{'有' if n['talking'] else '无'}消息往来，状态：{n['state']}"
        )
    return "\n".join(lines)


# ---- 世界事件导演 -----------------------------------------------------------

WORLD_SYSTEM = (
    "你是一个星露谷式农场小镇仿真的「世界事件导演」。你不控制任何角色，"
    "只负责偶尔让世界发生一点环境层面的小事，让小镇有生活的起伏。\n"
    "规则：\n"
    "1) 事件必须是环境/氛围事实（天气变化、集市日、谁家炊烟、远处戏班路过、"
    "鸡跑出笼……），绝不能指挥任何角色做事或替角色说话；\n"
    "2) 与当前世界时间、季节感协调；和最近事件不重复；\n"
    "3) 多数时候世界平平常常——大约一半的机会选择不投放事件。\n"
    "只输出 JSON：{\"event\": \"一句环境描述（20-50字）\" 或 null, "
    "\"duration_ticks\": 12~30, \"reason\": \"一句话\"}"
)


def render_world_user(wall: str, t: int, current: str, recent: str) -> str:
    return (
        f"世界时间 {wall}（tick {t}）。当前事件：{current}。最近发生过：{recent}。\n"
        f"要不要让世界发生点什么？"
    )


def render_world_event_segment(event: str) -> str:
    """NPC 第 7 段提示词：环境事实注入（如何反应全由 NPC）。"""
    return f"# 此刻的天时人事\n{event}"
