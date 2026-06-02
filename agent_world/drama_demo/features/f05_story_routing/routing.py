"""F05 玩家台词注入装配（把玩家这句话发给当前剧情节点的在场 NPC）。

剧情推进与结局判断已交由 LLM 导演（f05/director.py）按对话理解判断——本模块**不含任何
关键词 / 相位 / 信号等硬规则**，只负责数据驱动地把玩家台词组装成 DialogueInjection 事件、
注入给「当前节点的 inject_agents」。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("agent_world.drama_demo.routing")


def node_inject_ids(session: Any) -> List[int]:
    """玩家这句话注入给：与玩家同处一地的所有 NPC **＋ 当前有待演反应(bert_reaction)的 target**。

    剧情已无「幕/节点」白名单——玩家可自由找在场的任意角色搭话，谁在场谁就听得见。
    剧情反应由 bert（条件→反应）导演按对话理解触发：命中后 reaction 写进 hbm.bert_reactions[target]，
    经本批 inject 注入 target 的下一拍 prompt（knowledge.py 读 bert_reactions）由其演出。**target 若此刻不
    与玩家同地**（自己走开了 / 本就在别处），仅靠「在场」过滤会把它漏掉——reaction 注入了却没人演、剧情
    节拍静默丢失。故这里把「有待演反应的 target」无条件并入注入集，保证管理 agent 设计的反应一定落地。
    """
    present = _present_npc_ids(session)
    pending = _pending_reaction_ids(session)
    if not pending:
        return present
    seen = set(present)
    return present + [aid for aid in pending if aid not in seen]


def _pending_reaction_ids(session: Any) -> List[int]:
    """当前 hbm.bert_reactions 里有待演反应的 target agent id（int，排除玩家 0）；无则空，绝不抛。"""
    try:
        reactions = getattr(session, "bert_reactions", None) or {}
        out: List[int] = []
        for k in reactions:
            try:
                aid = int(k)
            except (TypeError, ValueError):
                continue
            if aid != 0:
                out.append(aid)
        return out
    except Exception:  # noqa: BLE001
        return []


def _present_npc_ids(session: Any) -> List[int]:
    """与玩家同处一地的 NPC（读只读世界库）；查不到/出错则空，绝不抛。"""
    place = str(getattr(session, "place_id", "") or "")
    if not place:
        return []
    try:
        from agent_world.drama_demo.features.f01_session.paths import get_sim_dir
        from agent_world.drama_demo.features.f06_read_model.world_db import make_readonly_db

        present = make_readonly_db(get_sim_dir()).agents_at(place)
        return [int(a) for a in present if int(a) != 0]
    except Exception as exc:  # noqa: BLE001
        log.debug("present_npc lookup failed: %s", exc)
        return []


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
    """把玩家台词组装成 DialogueInjection 事件（发给当前节点在场 NPC）+ 可选 turn_context。"""
    from agent_world.drama_demo.features.f07_agent_control.turn_context import (
        build_turn_context,
        format_inject_dialogue,
        is_f07_enabled,
    )

    agent_ids = node_inject_ids(session)
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

    return events, None, turn_context
