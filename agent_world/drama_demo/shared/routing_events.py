"""Routing world-event shapes for F05 watcher and F12 delta (no F05→F12 dependency)。

进入新节点时的「剧情推进」横幅**数据驱动**：内容取活跃 Story Pack 该节点的 beats_label+summary，
不再写死任何故事的转场旁白（旧 HBM A/B/C 脚本与 negotiation_room 氛围提示已退役）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# 兼容旧导入名（f12 constants/formatter 仍 re-export）；内容已不再写死，留空占位。
ROUTING_WORLD_EVENT_CONTENT: dict[str, str] = {}
PLACE_MUTATION_HINT = ""


def _node_narration(node_id: str) -> Optional[str]:
    """从活跃 Story Pack 取该节点的转场旁白：beats_label + summary（数据驱动，无写死故事文案）。"""
    try:
        from agent_world.drama_demo.shared import story_config

        node = story_config.active_pack().graph.nodes.get(str(node_id))
        if node is None:
            return None
        label = str(getattr(node, "beats_label", "") or "").strip()   # 任务标题
        summary = str(getattr(node, "summary", "") or "").strip()      # 任务目标
        if not (label or summary):
            return None
        # 任务卡：标题=任务名(label)，正文=任务目标(summary)；缺其一时彼此兜底。
        return (label or "新任务", summary or label)
    except Exception:  # noqa: BLE001 — 无活跃包/解析失败时不出横幅
        return None


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
        task = _node_narration(str(node))
        if not task:
            continue
        title, content = task
        out.append(
            {
                "id": f"route_node_{node}",
                "at_tick": int(at_tick),
                "kind": "phase_route",
                "title": title,      # 任务标题（beats_label）
                "content": content,  # 任务目标（summary）
                "place_id": routing_info.get("place_id"),
            }
        )
    return out
