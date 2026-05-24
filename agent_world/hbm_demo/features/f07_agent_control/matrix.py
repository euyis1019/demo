"""L3/L5 turn control matrix — active agents, tools, MOVE rules."""

from __future__ import annotations

from typing import Any, Dict, List, Set

from agent_world.hbm_demo.features.f07_agent_control.config import load_turn_control

SAM_ID = 7
JENSEN_ID = 2
RECEPTION_ID = 1
CEO_IDS = frozenset({4, 5, 6})

ALL_AGENT_TOOLS: Set[str] = {
    "speak_to_local",
    "send_message",
    "do_nothing",
    "update_state",
    "request_move",
    "send_to_group",
    "relation_change",
}

_PHASE1_AGENT1_TOOLS = frozenset(
    {"speak_to_local", "send_message", "do_nothing", "update_state"}
)
_PHASE1_IDLE = frozenset({"do_nothing"})
_PHASE2_JENSEN_TOOLS = frozenset(
    {"speak_to_local", "send_message", "do_nothing", "update_state"}
)
_PHASE2_TECH_VP_TOOLS = frozenset({"send_message", "do_nothing"})
_SAM_TURN16_TOOLS = frozenset({"send_message", "do_nothing", "request_move"})


def _phase_map(key: str) -> Dict[str, List[int]]:
    cfg = load_turn_control()
    raw = cfg.get(key) or {}
    return {str(phase): [int(x) for x in ids] for phase, ids in raw.items()}


def resolve_active_agent_ids(phase: str, player_turn: int) -> List[int]:
    """L3 whitelist for the current player-turn inject batch."""
    by_phase = _phase_map("active_agents_by_phase")
    active = list(by_phase.get(phase, by_phase.get("Phase 1", [1])))
    if phase == "Phase 3" and player_turn >= 16 and SAM_ID not in active:
        active.append(SAM_ID)
    return active


def resolve_passive_agent_ids(phase: str) -> List[int]:
    """Agents that may tick when they have pending RDC / inject memory."""
    by_phase = _phase_map("passive_agents_by_phase")
    return list(by_phase.get(phase, []))


def resolve_llm_params(phase: str) -> Dict[str, float | int]:
    cfg = load_turn_control()
    defaults = cfg.get("llm_defaults") or {}
    by_phase = cfg.get("llm_by_phase") or {}
    phase_cfg = by_phase.get(phase) or {}
    return {
        "temperature": float(
            phase_cfg.get("temperature", defaults.get("temperature", 0.65))
        ),
        "max_tokens": int(phase_cfg.get("max_tokens", defaults.get("max_tokens", 500))),
    }


def allowed_tools_for(agent_id: int, phase: str, player_turn: int) -> Set[str]:
    """L5 tool whitelist per agent / phase / turn."""
    aid = int(agent_id)

    if phase == "Phase 1":
        if aid == RECEPTION_ID:
            return set(_PHASE1_AGENT1_TOOLS)
        return set(_PHASE1_IDLE)

    if phase == "Phase 2":
        if aid == JENSEN_ID:
            return set(_PHASE2_JENSEN_TOOLS)
        if aid == 3:
            return set(_PHASE2_TECH_VP_TOOLS)
        return set(_PHASE1_IDLE)

    if phase == "Phase 3":
        if aid == SAM_ID:
            if player_turn >= 16:
                return set(_SAM_TURN16_TOOLS)
            return set(_PHASE1_IDLE)
        if aid in {2, 3, 4, 5, 6}:
            return set(ALL_AGENT_TOOLS)
        return set(_PHASE1_IDLE)

    if phase == "Phase 4":
        if aid in {JENSEN_ID, 3}:
            return set(ALL_AGENT_TOOLS)
        return set(_PHASE1_IDLE)

    return set(_PHASE1_IDLE)


def is_move_allowed(agent_id: int, phase: str, player_turn: int) -> bool:
    """L5 MOVE hard rules (dev_logs/24 §4.2)."""
    aid = int(agent_id)
    if aid == RECEPTION_ID:
        return False
    if aid == SAM_ID and player_turn < 16:
        return False
    if aid in CEO_IDS and phase != "Phase 3":
        return False
    if aid == JENSEN_ID and phase == "Phase 1":
        return False
    return True


def narrative_for(phase: str, player_turn: int) -> str:
    if phase == "Phase 1":
        return (
            "玩家在前台 nvidia_reception；Jensen 与三大 CEO 在谈判室，尚未出场。"
            "禁止替 Jensen 做决定或描写 Jensen 已见玩家。"
        )
    if phase == "Phase 2":
        return "玩家在 Jensen 私密会议室；谈判室 CEO 不应在本阶段抢戏。"
    if phase == "Phase 3" and player_turn >= 16:
        return "Turn 16+：Sam Altman 可 RDC 搅局；谈判室群聊允许但须符合阶段。"
    if phase == "Phase 3":
        return "多方谈判进行中；Sam 仍在 openai_hq，Turn 16 前不得 MOVE。"
    if phase == "Phase 4":
        return "终局谈判：仅 Jensen 与 Tech VP 活跃 tick。"
    return ""


def forbidden_actions_text(phase: str, player_turn: int) -> str:
    if phase == "Phase 1":
        return "request_move、群聊 send_to_group、relation_change、替 Jensen 出场"
    if phase == "Phase 2":
        return "request_move、群聊（Tech VP 仅 RDC 回复 Jensen）"
    if phase == "Phase 3" and player_turn < 16:
        return "Sam request_move（Turn 16 前）"
    return ""


def build_allowed_tools_map(phase: str, player_turn: int) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for aid in range(1, 8):
        out[str(aid)] = sorted(allowed_tools_for(aid, phase, player_turn))
    return out
