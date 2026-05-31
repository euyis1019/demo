"""F05 玩家台词注入装配（把玩家这句话发给当前剧情节点的在场 NPC）。

剧情推进与结局判断已交由 LLM 导演（f05/director.py）按对话理解判断——本模块**不含任何
关键词 / 相位 / 信号等硬规则**，只负责数据驱动地把玩家台词组装成 DialogueInjection 事件、
注入给「当前节点的 inject_agents」。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("agent_world.hbm_demo.routing")


def node_inject_ids(session: Any) -> List[int]:
    """玩家这句话注入给当前剧情节点的 inject_agents（无节点/查无即空，不做相位兜底）。"""
    node_id = getattr(session, "current_node_id", None)
    if not node_id:
        return []
    from agent_world.hbm_demo.shared import story_config

    if story_config.node_exists(node_id):
        return story_config.node_inject_agents(node_id)
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
    from agent_world.hbm_demo.features.f07_agent_control.turn_context import (
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
