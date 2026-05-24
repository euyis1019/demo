"""L4 TurnContext assembly for ABCS (Flask → Runner via IPC inject)."""

from __future__ import annotations

from typing import Any, Dict

from agent_world.hbm_demo.features.f07_agent_control.config import is_abcs_enabled
from agent_world.hbm_demo.features.f07_agent_control.matrix import (
    build_allowed_tools_map,
    forbidden_actions_text,
    narrative_for,
    resolve_active_agent_ids,
    resolve_llm_params,
    resolve_passive_agent_ids,
)

# Turn → hint excerpts from dev_logs/19 (1–2 sentences, not full script).
_TURN_HINTS: Dict[int, str] = {
    1: "开场强调 Vision + Execution：稀疏注意力 / KV Cache / kernel 已 repro。",
    2: "加深技术细节，施压促前台 RDC 通报 Jensen。",
    3: "具体数字 demo + 竞品语境，继续拉高 Vision/Execution。",
    4: "Turn 4 决断：须 vision+execution≥15，否则 Bad End。",
    12: "Phase 2 末：Tech VP 正面 RDC 关键词「可行」「核武器」「理论上成立」。",
    16: "Sam 搅局 RDC：OpenAI 对稀疏注意力感兴趣，暗示截胡。",
    20: "节点 C：burnout<80 且 vision≥30。",
    25: "终局意图：加入 NVIDIA / 种子融资 / 冷淡成交。",
}


def reference_hint_for_turn(turn: int, phase: str) -> str:
    if turn in _TURN_HINTS:
        return _TURN_HINTS[turn]
    if phase == "Phase 1":
        return "前台礼貌接待；重大技术突破则 RDC 汇报 Jensen。"
    if phase == "Phase 2":
        return "私密审查：Jensen 求证 Tech VP，Tech VP 逻辑推演后 RDC 回复。"
    if phase == "Phase 3":
        return "谈判室舌战；CEO 用产能/利润率攻击，Samsung 留意背刺时机。"
    if phase == "Phase 4":
        return "终局：Jensen 与 Tech VP 定调，CEO 已离场。"
    return ""


def build_turn_context(session: Any) -> Dict[str, Any]:
    """Build TurnContext snapshot for one player-turn inject batch."""
    if not is_abcs_enabled():
        return {"enabled": False}

    phase = str(getattr(session, "phase", "Phase 1"))
    player_turn = int(getattr(session, "player_turn", 1))
    place_id = str(getattr(session, "place_id", "nvidia_reception"))
    llm = resolve_llm_params(phase)

    return {
        "enabled": True,
        "phase": phase,
        "player_turn": player_turn,
        "place_id": place_id,
        "active_agent_ids": resolve_active_agent_ids(phase, player_turn),
        "passive_agent_ids": resolve_passive_agent_ids(phase),
        "allowed_tools_by_agent": build_allowed_tools_map(phase, player_turn),
        "temperature_override": llm["temperature"],
        "max_tokens_override": llm["max_tokens"],
        "narrative": narrative_for(phase, player_turn),
        "reference_hint": reference_hint_for_turn(player_turn, phase),
        "forbidden_actions": forbidden_actions_text(phase, player_turn),
    }


def format_constraint_prefix(ctx: Dict[str, Any]) -> str:
    """L4 system constraint text prepended to player dialogue inject."""
    if not ctx.get("enabled", True):
        return ""

    active = ctx.get("active_agent_ids") or []
    allowed_sample = ctx.get("allowed_tools_by_agent") or {}
    agent1_tools = allowed_sample.get("1") or allowed_sample.get(1) or []

    lines = [
        f"【系统约束·{ctx['phase']} Turn {ctx['player_turn']}】",
        f"地点：{ctx['place_id']}。",
        f"本批 tick 活跃 Agent：{active}。",
    ]
    if agent1_tools and 1 in active:
        lines.append(f"允许工具（Agent 1）：{', '.join(agent1_tools)}。")
    forbidden = ctx.get("forbidden_actions") or ""
    if forbidden:
        lines.append(f"禁止：{forbidden}。")
    narrative = ctx.get("narrative") or ""
    if narrative:
        lines.append(narrative)
    hint = ctx.get("reference_hint") or ""
    if hint:
        lines.append(f"参考：{hint}")
    return "\n".join(lines)
