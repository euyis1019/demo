"""Phase routing nodes A/B/C/D and inject payload assembly for dark SBTI clinic."""

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
CAT_ID = 3
ANOMALY_IDS = (4, 5, 6)
SAM_ID = 7

PHASE_INJECT_AGENTS: Dict[str, List[int]] = {
    "Phase 1": [1],
    "Phase 2": [2],
    "Phase 3": [2, 3, 4, 5, 6],
    "Phase 4": [2, 3],
}

POSITIVE_RDC_KEYWORDS: Tuple[str, ...] = (
    "档案命中",
    "记忆成立",
    "可疑但好笑",
    "测试完成",
    "透明化预览",
)

TURN16_BROADCAST_MESSAGE = (
    "嗞——社死任务播报：请给最近联系人发送「你欠我五块钱」。"
)
TURN16_SAM_TEXT = (
    "系统指令：你是玩家的最近联系人。请立刻 RDC 私信 Morgen，"
    "提醒他：玩家是否敢发「你欠我五块钱」会影响完整版剧情。"
)
NODE_B_BEHAVIOR_HINT = (
    "死一般的安静，像刚发完朋友圈没人点赞。身份反转和透明化预览即将开始。"
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
    """Node B: black cat(3)→Morgen(2) positive RDC since phase2_start_tick."""
    rows = db.fetch_rdc_messages(
        sender_id=CAT_ID,
        recipient_id=JENSEN_ID,
        since_t=since_tick,
        t_now=t_now,
    )
    for row in rows:
        content = str(row["content"] or "")
        if any(kw in content for kw in POSITIVE_RDC_KEYWORDS):
            return True
    return False


def _legacy_node_a_applies(session: Any) -> bool:
    return (
        session.player_turn == 4
        and session.stats["vision"] + session.stats["execution"] >= 15
    )


def node_a_applies(
    session: Any,
    db: Any = None,
    current_tick: Optional[int] = None,
) -> bool:
    from agent_world.hbm_demo.features.f05_story_routing.agent_signals import detect_node_a
    from agent_world.hbm_demo.features.f05_story_routing.routing_config import is_agent_driven

    if is_agent_driven():
        if db is None or current_tick is None or session.phase != "Phase 1":
            return False
        since_t = max(0, int(getattr(session, "start_tick", 0) or 0))
        return detect_node_a(db, since_t=since_t, t_now=int(current_tick))
    return _legacy_node_a_applies(session)


def _legacy_node_b_applies(session: Any, db: Any, current_tick: int) -> bool:
    if session.player_turn != 12 or session.phase != "Phase 2":
        return False
    if session.stats["execution"] < 20:
        return False
    since = session.phase2_start_tick
    if since is None:
        return False
    return has_positive_tech_vp_rdc(db, since_tick=int(since), t_now=current_tick)


def node_b_applies(
    session: Any,
    db: Any,
    current_tick: int,
) -> bool:
    from agent_world.hbm_demo.features.f05_story_routing.agent_signals import detect_node_b
    from agent_world.hbm_demo.features.f05_story_routing.routing_config import is_agent_driven

    if is_agent_driven():
        if session.phase != "Phase 2":
            return False
        since = session.phase2_start_tick
        if since is None:
            since = max(0, int(getattr(session, "start_tick", 0) or 0))
        return detect_node_b(db, since_t=int(since), t_now=int(current_tick))
    return _legacy_node_b_applies(session, db, current_tick)


def _legacy_node_c_applies(session: Any) -> bool:
    return (
        session.player_turn == 20
        and session.phase == "Phase 3"
        and session.stats["burnout"] < 80
        and session.stats["vision"] >= 30
    )


def node_c_applies(
    session: Any,
    db: Any = None,
    current_tick: Optional[int] = None,
) -> bool:
    from agent_world.hbm_demo.features.f05_story_routing.agent_signals import detect_node_c
    from agent_world.hbm_demo.features.f05_story_routing.routing_config import is_agent_driven

    if is_agent_driven():
        if db is None or current_tick is None or session.phase != "Phase 3":
            return False
        since_t = max(0, int(getattr(session, "start_tick", 0) or 0))
        return detect_node_c(db, since_t=since_t, t_now=int(current_tick))
    return _legacy_node_c_applies(session)


def _llm_client() -> OpenAI:
    scenario = load_scenario(DEFAULT_CONFIG)
    llm_cfg = scenario.get("llm", {}) or {}
    return OpenAI(
        api_key=resolve_api_key(llm_cfg),
        base_url=llm_cfg.get("base_url", "https://api.deepseek.com"),
    )


def _heuristic_turn25_intent(player_text: str) -> str:
    text = player_text.lower()
    join_kw = ("死者", "透明", "接受", "承认", "社交幽灵", "归档", "摆烂", "不回", "逃避")
    seed_kw = ("吗喽", "反抗", "重测", "打电话", "会发", "发五块", "发5块", "勇敢", "整活")
    if any(k in player_text or k in text for k in join_kw):
        return "dead_type"
    if any(k in player_text or k in text for k in seed_kw):
        return "monkey_type"
    return "ambiguous"


def classify_turn25_intent(player_text: str) -> str:
    """DeepSeek intent classification for node D (§4.3)."""
    scenario = load_scenario(DEFAULT_CONFIG)
    llm_cfg = scenario.get("llm", {}) or {}
    model = llm_cfg.get("model", "deepseek-chat")
    system = (
        "你是《暗黑心理诊所》SBTI 结局裁判。"
        "根据玩家最后一轮发言，判断其倾向："
        "dead_type=接受自己是死者/社交幽灵/透明人/稳定逃避；"
        "monkey_type=反抗诊断/选择吗喽式整活/愿意社死发消息；"
        "ambiguous=嘴硬、回避、混乱或握草人倾向。"
        "只输出 JSON：{\"intent\": \"dead_type\"|\"monkey_type\"|\"ambiguous\"}"
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
        if intent in ("dead_type", "monkey_type", "ambiguous"):
            return intent
    except Exception as exc:  # noqa: BLE001
        log.warning("classify_turn25_intent LLM failed, heuristic: %s", exc)
    return _heuristic_turn25_intent(player_text)


def resolve_ending_id(intent: str, trust: int) -> str:
    del trust
    if intent == "dead_type":
        return "ending_dead_type"
    if intent == "monkey_type":
        return "ending_monkey_type"
    return "ending_scarecrow_type"


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
        if has_story_signal(db, "ending_dead", since_t=since_t, t_now=t_now):
            return "ending_dead_type"
        if has_story_signal(db, "ending_monkey", since_t=since_t, t_now=t_now):
            return "ending_monkey_type"
    return resolve_ending_id(intent, trust)


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

    from agent_world.hbm_demo.features.f08_virtual_player.player_entity import (
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
            "routing node A: Morgen→%s phase2_start_tick=%s",
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
        applied["nodes"].append("B")
        applied["phase"] = session.phase
        applied["place_id"] = session.place_id
        applied["place_mutation"] = True
        log.info("routing node B: Morgen→%s + PlaceMutation", PLACE_NEGOTIATION)

    if node_c_applies(session, db=db, current_tick=current_tick):
        for anomaly_id in ANOMALY_IDS:
            send_move_agent(
                ipc_client,
                agent_id=anomaly_id,
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
        log.info("routing node C: anomaly agents 4/5/6→%s", PLACE_RECEPTION)

    return applied
