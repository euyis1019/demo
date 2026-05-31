"""Phase routing nodes A/B/C/D and inject payload assembly for HBM demo."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from agent_world.hbm_demo.features.f01_session.constants import DEFAULT_CONFIG
from agent_world.hbm_demo.shared.config_loader import load_scenario
from agent_world.hbm_demo.core.runner.kernel import llm_request_extras, resolve_api_key

log = logging.getLogger("agent_world.hbm_demo.routing")

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
    from agent_world.hbm_demo.features.f07_agent_control.config import is_f07_enabled

    if phase == "Phase 4" and is_f07_enabled():
        return [JENSEN_ID]
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
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Build DialogueInjection events, optional Turn 16 broadcast, optional turn_context."""
    from agent_world.hbm_demo.features.f07_agent_control.turn_context import (
        build_turn_context,
        format_inject_dialogue,
        is_f07_enabled,
    )

    # 节点驱动：玩家这句话注入给「当前节点的 inject_agents」；无节点时回退 HBM 相位表。
    node_id = getattr(session, "current_node_id", None)
    if node_id:
        from agent_world.hbm_demo.shared import story_config

        agent_ids = story_config.node_inject_agents(node_id) or inject_agent_ids_for_phase(session.phase)
    else:
        agent_ids = inject_agent_ids_for_phase(session.phase)
    turn_context: Optional[Dict[str, Any]] = None

    if is_f07_enabled():
        turn_context = build_turn_context(session, player_text)
        events = [
            build_dialogue_event(
                task_id=task_id,
                agent_id=aid,
                text=format_inject_dialogue(session, aid, player_text, turn_context),
            )
            for aid in agent_ids
        ]
    else:
        dialogue = format_player_dialogue(player_text)
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

    return events, broadcast, turn_context


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


def node_a_applies(
    session: Any,
    db: Any = None,
    current_tick: Optional[int] = None,
) -> bool:
    from agent_world.hbm_demo.features.f05_story_routing.agent_signals import detect_node_a

    if db is None or current_tick is None or session.phase != "Phase 1":
        return False
    since_t = max(0, int(getattr(session, "start_tick", 0) or 0))
    return detect_node_a(db, since_t=since_t, t_now=int(current_tick))


def node_b_applies(
    session: Any,
    db: Any,
    current_tick: int,
) -> bool:
    from agent_world.hbm_demo.features.f05_story_routing.agent_signals import detect_node_b

    if session.phase != "Phase 2":
        return False
    since = session.phase2_start_tick
    if since is None:
        since = max(0, int(getattr(session, "start_tick", 0) or 0))
    return detect_node_b(db, since_t=int(since), t_now=int(current_tick))


def node_c_applies(
    session: Any,
    db: Any = None,
    current_tick: Optional[int] = None,
) -> bool:
    from agent_world.hbm_demo.features.f05_story_routing.agent_signals import detect_node_c

    if db is None or current_tick is None or session.phase != "Phase 3":
        return False
    since = getattr(session, "phase3_start_tick", None)
    if since is None:
        since = max(0, int(getattr(session, "start_tick", 0) or 0))
    return detect_node_c(db, since_t=int(since), t_now=int(current_tick))


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
            **llm_request_extras(llm_cfg),
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
    if intent == "join_nvidia" and trust >= 25:
        return "ending_join_nvidia"
    if intent == "seed_round" and trust >= 15:
        return "ending_seed_round"
    return "ending_cold_deal"


def resolve_turn25_ending(
    intent: str,
    trust: int,
    db: Any,
    *,
    since_t: int,
    t_now: int,
) -> str:
    """Node D — story_advance offer_* overrides intent/trust heuristics."""
    from agent_world.hbm_demo.features.f05_story_routing.routing_config import (
        is_story_advance_enabled,
    )
    from agent_world.hbm_demo.features.f05_story_routing.story_signals import (
        has_story_signal,
    )

    if is_story_advance_enabled():
        if has_story_signal(db, "offer_join", since_t=since_t, t_now=t_now):
            return "ending_join_nvidia"
        if has_story_signal(db, "offer_seed", since_t=since_t, t_now=t_now):
            return "ending_seed_round"
    return resolve_ending_id(intent, trust)


def classify_phase4_conclusion(dialogue: str) -> Optional[str]:
    """LLM judge for Phase 4 early-end: is the deal concluded yet?

    Reads the negotiation-room transcript (Jensen + player) and decides whether
    the player has clearly accepted one of Jensen's offers AND Jensen confirmed
    it. Returns the matching ending id, or None when not yet concluded (still
    presenting options / player hasn't accepted / still haggling). Robust to
    phrasing where brittle keyword lists fail. On any LLM error returns None —
    never ends the game on uncertainty (the Turn-25 gate is the fallback).
    """
    text = str(dialogue or "").strip()
    if not text:
        return None
    scenario = load_scenario(DEFAULT_CONFIG)
    llm_cfg = scenario.get("llm", {}) or {}
    model = llm_cfg.get("model", "deepseek-chat")
    system = (
        "你是《HBM 显存价格保卫战》终局裁判。下面是 NVIDIA 终局谈判室里 "
        "Jensen 与玩家的对话。判断双方是否【已经谈成】：玩家已明确接受 Jensen 给出的"
        "某个 offer，且 Jensen 已确认成交（如给 offer/合同、说同意/敲定/这么定了）。"
        "若 Jensen 还在介绍选项、玩家尚未明确接受、或还在还价犹豫 → 视为未谈成。"
        "只输出 JSON：{\"concluded\": true|false, \"ending\": "
        "\"join_nvidia\"|\"seed_round\"|\"none\"}。"
        "join_nvidia=玩家加入 NVIDIA（入职/当员工）；"
        "seed_round=玩家拿 NVIDIA 投资独立创业/种子轮。"
    )
    try:
        resp = _llm_client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
            temperature=0.1,
            max_tokens=60,
            **llm_request_extras(llm_cfg),
        )
        raw = (resp.choices[0].message.content or "").strip()
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            raw = match.group(0)
        data = json.loads(raw)
        if not bool(data.get("concluded")):
            return None
        ending = str(data.get("ending", "none")).strip().lower()
        if ending == "join_nvidia":
            return "ending_join_nvidia"
        if ending == "seed_round":
            return "ending_seed_round"
    except Exception as exc:  # noqa: BLE001
        log.warning("classify_phase4_conclusion LLM failed: %s", exc)
    return None


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
    from agent_world.hbm_demo.http.ipc_helper import (
        send_enqueue_script_event,
        send_move_agent,
    )

    applied: Dict[str, Any] = {"nodes": []}

    from agent_world.hbm_demo.features.f17_virtual_player.player_entity import (
        sync_player_place_on_routing,
    )

    if node_a_applies(session, db=db, current_tick=current_tick):
        send_move_agent(
            ipc_client,
            agent_id=JENSEN_ID,
            place_id=PLACE_JENSEN_ROOM,
            timeout=ipc_timeout,
        )
        sync_player_place_on_routing(
            session,
            ipc_client=ipc_client,
            new_phase="Phase 2",
            node="A",
            ipc_timeout=ipc_timeout,
        )
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
        send_enqueue_script_event(
            ipc_client,
            events=[mutation_event],
            timeout=ipc_timeout,
        )

        sync_player_place_on_routing(
            session,
            ipc_client=ipc_client,
            new_phase="Phase 3",
            node="B",
            ipc_timeout=ipc_timeout,
        )
        session.phase3_start_tick = current_tick
        applied["nodes"].append("B")
        applied["phase"] = session.phase
        applied["place_id"] = session.place_id
        applied["place_mutation"] = True
        applied["phase3_start_tick"] = current_tick
        log.info("routing node B: Jensen→%s + PlaceMutation", PLACE_NEGOTIATION)

    if node_c_applies(session, db=db, current_tick=current_tick):
        for ceo_id in CEO_IDS:
            send_move_agent(
                ipc_client,
                agent_id=ceo_id,
                place_id=PLACE_RECEPTION,
                timeout=ipc_timeout,
            )
        sync_player_place_on_routing(
            session,
            ipc_client=ipc_client,
            new_phase="Phase 4",
            node="C",
            ipc_timeout=ipc_timeout,
        )
        applied["nodes"].append("C")
        applied["phase"] = session.phase
        applied["place_id"] = session.place_id
        log.info("routing node C: CEOs 4/5/6→%s", PLACE_RECEPTION)

    return applied
