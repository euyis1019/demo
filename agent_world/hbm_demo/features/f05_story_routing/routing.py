"""Phase routing nodes A/B/C/D and inject payload assembly for HBM demo."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from agent_world.hbm_demo.shared.config_loader import load_scenario
from agent_world.hbm_demo.http.ipc_helper import send_inject_batch, send_move_agent
from agent_world.hbm_demo.core.runner.kernel import resolve_api_key
from agent_world.hbm_demo.features.f07_agent_control.turn_context import (
    build_turn_context,
    format_constraint_prefix,
)

log = logging.getLogger("agent_world.hbm_demo.routing")

_HBM_DEMO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = _HBM_DEMO_ROOT / "hbm_scenario.yaml"

PLACE_RECEPTION = "nvidia_reception"
PLACE_JENSEN_ROOM = "jensen_private_room"
PLACE_NEGOTIATION = "negotiation_room"

JENSEN_ID = 2
TECH_VP_ID = 3
CEO_IDS = (4, 5, 6)
SAM_ID = 7

PHASE_INJECT_AGENTS: Dict[str, List[int]] = {
    "Phase 1": [1],
    "Phase 2": [2],
    "Phase 3": [2, 3, 4, 5, 6],
    "Phase 4": [2, 3],
}

POSITIVE_RDC_KEYWORDS: Tuple[str, ...] = (
    "可行",
    "核武器",
    "理论上成立",
    "理论上可行",
    "成立",
)

TURN16_BROADCAST_MESSAGE = (
    "彭博终端快讯：AMD 宣布下一代 MI400 将采用全新自研显存架构…"
)
TURN16_SAM_TEXT = (
    "系统指令：OpenAI 对稀疏注意力算法极度感兴趣，"
    "请立刻 RDC 私信 Jensen，暗示愿意高价截胡。"
)
NODE_B_BEHAVIOR_HINT = (
    "死一般的寂静，所有人都被 Jensen 带来的底牌震撼了…"
)


def inject_agent_ids_for_phase(phase: str) -> List[int]:
    """Return DialogueInjection targets for the given session phase."""
    return list(PHASE_INJECT_AGENTS.get(phase, PHASE_INJECT_AGENTS["Phase 1"]))


def format_player_dialogue(player_text: str) -> str:
    text = player_text.strip()
    if not text.startswith("玩家"):
        text = f"玩家说：{text}"
    return text


def build_dialogue_event(
    *,
    task_id: str,
    agent_id: int,
    text: str,
    event_suffix: str = "",
) -> Dict[str, Any]:
    suffix = f"_{event_suffix}" if event_suffix else ""
    return {
        "id": f"{task_id}_agent_{agent_id}{suffix}",
        "trigger": {"type": "at_condition", "expr": "True"},
        "effect": {
            "type": "dialogue_injection",
            "agent_id": int(agent_id),
            "text": text,
        },
    }


def build_inject_payload(
    session: Any,
    player_text: str,
    *,
    task_id: str,
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]], Dict[str, Any]]:
    """Build DialogueInjection events, optional Turn 16 broadcast, and TurnContext."""
    turn_ctx = build_turn_context(session)
    prefix = format_constraint_prefix(turn_ctx)
    dialogue_body = format_player_dialogue(player_text)
    dialogue = f"{prefix}\n\n{dialogue_body}" if prefix else dialogue_body
    agent_ids = inject_agent_ids_for_phase(session.phase)
    events = [
        build_dialogue_event(task_id=task_id, agent_id=aid, text=dialogue)
        for aid in agent_ids
    ]

    broadcast: Optional[Dict[str, Any]] = None
    if session.player_turn == 16 and session.phase == "Phase 3":
        broadcast = {
            "place_id": PLACE_NEGOTIATION,
            "message": TURN16_BROADCAST_MESSAGE,
        }
        events.append(
            build_dialogue_event(
                task_id=task_id,
                agent_id=SAM_ID,
                text=TURN16_SAM_TEXT,
                event_suffix="sam_nudge",
            )
        )

    return events, broadcast, turn_ctx


def has_positive_tech_vp_rdc(db: Any, *, since_tick: int, t_now: int) -> bool:
    """Node B: Tech VP(3)→Jensen(2) positive RDC since phase2_start_tick."""
    rows = db.fetch_rdc_messages(
        sender_id=TECH_VP_ID,
        recipient_id=JENSEN_ID,
        since_t=since_tick,
        t_now=t_now,
    )
    for row in rows:
        content = str(row["content"] or "")
        if any(kw in content for kw in POSITIVE_RDC_KEYWORDS):
            return True
    return False


def node_a_applies(session: Any) -> bool:
    return (
        session.player_turn == 4
        and session.stats["vision"] + session.stats["execution"] >= 15
    )


def node_b_applies(session: Any, db: Any, current_tick: int) -> bool:
    if session.player_turn != 12 or session.phase != "Phase 2":
        return False
    if session.stats["execution"] < 20:
        return False
    since = session.phase2_start_tick
    if since is None:
        return False
    return has_positive_tech_vp_rdc(db, since_tick=int(since), t_now=current_tick)


def node_c_applies(session: Any) -> bool:
    return (
        session.player_turn == 20
        and session.phase == "Phase 3"
        and session.stats["burnout"] < 80
        and session.stats["vision"] >= 30
    )


def _llm_client() -> OpenAI:
    scenario = load_scenario(DEFAULT_CONFIG)
    llm_cfg = scenario.get("llm", {}) or {}
    return OpenAI(
        api_key=resolve_api_key(llm_cfg),
        base_url=llm_cfg.get("base_url", "https://api.deepseek.com"),
    )


def _heuristic_turn25_intent(player_text: str) -> str:
    text = player_text.lower()
    join_kw = ("加入", "入职", "nvdia", "nvidia", "黄仁勋", "团队", "全职")
    seed_kw = ("融资", "种子", "投资", "估值", "独立", "创业", "round")
    if any(k in player_text or k in text for k in join_kw):
        return "join_nvidia"
    if any(k in player_text or k in text for k in seed_kw):
        return "seed_round"
    return "ambiguous"


def classify_turn25_intent(player_text: str) -> str:
    """DeepSeek intent classification for node D (§4.3)."""
    scenario = load_scenario(DEFAULT_CONFIG)
    llm_cfg = scenario.get("llm", {}) or {}
    model = llm_cfg.get("model", "deepseek-chat")
    system = (
        "你是《HBM 显存价格保卫战》结局裁判。"
        "根据玩家最后一轮发言，判断其倾向。"
        "只输出 JSON：{\"intent\": \"join_nvidia\"|\"seed_round\"|\"ambiguous\"}"
    )
    try:
        resp = _llm_client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": player_text},
            ],
            temperature=0.2,
            max_tokens=80,
        )
        raw = (resp.choices[0].message.content or "").strip()
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            raw = match.group(0)
        data = json.loads(raw)
        intent = str(data.get("intent", "ambiguous")).strip().lower()
        if intent in ("join_nvidia", "seed_round", "ambiguous"):
            return intent
    except Exception as exc:  # noqa: BLE001
        log.warning("classify_turn25_intent LLM failed, heuristic: %s", exc)
    return _heuristic_turn25_intent(player_text)


def resolve_ending_id(intent: str, trust: int) -> str:
    if intent == "join_nvidia" and trust >= 40:
        return "ending_join_nvidia"
    if intent == "seed_round" and trust >= 25:
        return "ending_seed_round"
    return "ending_cold_deal"


def apply_routing(
    session: Any,
    *,
    ipc_client: Any,
    db: Any,
    task_id: str,
    current_tick: int,
    tick_count: int = 6,
    ipc_timeout: float = 600.0,
) -> Dict[str, Any]:
    """Apply routing side effects after main inject (§4.3 / §6.2.3)."""
    applied: Dict[str, Any] = {"nodes": []}

    if node_a_applies(session):
        send_move_agent(
            ipc_client,
            agent_id=JENSEN_ID,
            place_id=PLACE_JENSEN_ROOM,
            timeout=ipc_timeout,
        )
        session.phase = "Phase 2"
        session.place_id = PLACE_JENSEN_ROOM
        session.phase2_start_tick = current_tick
        applied["nodes"].append("A")
        applied["phase"] = session.phase
        applied["place_id"] = session.place_id
        applied["phase2_start_tick"] = current_tick
        log.info(
            "routing node A: Jensen→%s phase2_start_tick=%s",
            PLACE_JENSEN_ROOM,
            current_tick,
        )

    if node_b_applies(session, db, current_tick):
        send_move_agent(
            ipc_client,
            agent_id=JENSEN_ID,
            place_id=PLACE_NEGOTIATION,
            timeout=ipc_timeout,
        )

        mutation_event = {
            "id": f"route_b_mutate_{task_id}",
            "trigger": {"type": "at_condition", "expr": "True"},
            "effect": {
                "type": "place_mutation",
                "place_id": PLACE_NEGOTIATION,
                "attrs_patch": {"behavior_hint": NODE_B_BEHAVIOR_HINT},
            },
        }
        send_inject_batch(
            ipc_client,
            events=[mutation_event],
            tick_count=tick_count,
            timeout=ipc_timeout,
        )

        session.phase = "Phase 3"
        session.place_id = PLACE_NEGOTIATION
        applied["nodes"].append("B")
        applied["phase"] = session.phase
        applied["place_id"] = session.place_id
        applied["place_mutation"] = True
        log.info("routing node B: Jensen→%s + PlaceMutation", PLACE_NEGOTIATION)

    if node_c_applies(session):
        for ceo_id in CEO_IDS:
            send_move_agent(
                ipc_client,
                agent_id=ceo_id,
                place_id=PLACE_RECEPTION,
                timeout=ipc_timeout,
            )
        session.phase = "Phase 4"
        applied["nodes"].append("C")
        applied["phase"] = session.phase
        log.info("routing node C: CEOs 4/5/6→%s", PLACE_RECEPTION)

    return applied
