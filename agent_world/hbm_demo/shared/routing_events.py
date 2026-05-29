"""Routing world-event shapes for F05 watcher and F12 delta (no F05→F12 dependency)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

ROUTING_WORLD_EVENT_CONTENT: dict[str, str] = {
    "A": "前台带你穿过走廊，进入私密会议室。Jensen 推门而入。Phase 2 开始。",
    "B": "Jensen 带你回到主谈判室，气氛为之一变。Phase 3 开始。",
    "C": "三位 CEO 被请离谈判室，终局只剩你与 Jensen（Tech VP 旁听）。Phase 4 开始。",
}

PLACE_MUTATION_HINT = "死一般的寂静，所有人都被 Jensen 带来的底牌震撼了…"


def format_routing_world_events(
    routing_info: Optional[Dict[str, Any]],
    *,
    at_tick: int,
    task_id: str,
) -> List[Dict[str, Any]]:
    _ = task_id
    if not routing_info:
        return []
    nodes = list(routing_info.get("nodes") or [])
    out: List[Dict[str, Any]] = []
    for node in nodes:
        content = ROUTING_WORLD_EVENT_CONTENT.get(str(node))
        if not content:
            continue
        out.append(
            {
                "id": f"route_node_{node}",
                "at_tick": int(at_tick),
                "kind": "phase_route",
                "title": f"路由节点 {node}",
                "content": content,
                "place_id": routing_info.get("place_id"),
            }
        )
    if routing_info.get("place_mutation"):
        out.append(
            {
                "id": "place_mutation_negotiation_room",
                "at_tick": int(at_tick),
                "kind": "place_mutation",
                "title": "谈判室氛围变化",
                "content": PLACE_MUTATION_HINT,
                "place_id": "negotiation_room",
            }
        )
    return out
