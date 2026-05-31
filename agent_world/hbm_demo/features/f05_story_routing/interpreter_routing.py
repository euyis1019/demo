"""解释器→运行期副作用桥（G0-Slice4，dev_logs/45 §6）。

把 StoryInterpreter 的纯决策（detect_edge / plan_actions）落到 watcher 现有的运行期副作用上
（IPC 移动 agent、place_mutation 入队、玩家随路由换位/换 phase），产出与
`routing.apply_routing` **结构完全一致**的 routing_info。复用同一批 ipc_helper 与
sync_player_place_on_routing，不重复实现移动语义。

开关式：仅当 `is_story_pack_routing_enabled()` 时 watcher 走本路径；默认仍走旧 routing.py。
等价性由 scripts/tests/test_story_interpreter_routing_equiv.py 离线证明（同一假 db/session/ipc，
逐场景断言 IPC 调用 + session 变更 + routing_info 与旧 apply_routing 完全一致）。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Dict, List, Optional

from agent_world.hbm_demo.features.f05_story_routing.interpreter import StoryInterpreter
from agent_world.hbm_demo.shared.story_pack.model import StoryEdge

log = logging.getLogger("agent_world.hbm_demo.f05.interp")


@lru_cache(maxsize=8)
def get_interpreter(story_id: str) -> StoryInterpreter:
    """按 story_id 缓存解释器（Story Pack 加载一次）。"""
    return StoryInterpreter.for_story(story_id)


def _current_node_id(interp: StoryInterpreter, phase: str) -> Optional[str]:
    """由 session.phase（beats_label）定位当前节点 id。"""
    for nid, node in interp.graph.nodes.items():
        if node.beats_label == phase:
            return nid
    return None


def _transition_edges(interp: StoryInterpreter, node_id: str) -> List[StoryEdge]:
    """从 node_id 出发、指向另一个节点（非结局）的转移边——对应旧节点 A/B/C。"""
    return [e for e, dst in interp.graph.get_children(node_id) if interp.graph.is_node(dst)]


def detect_bad_end_via_interpreter(interp: StoryInterpreter, hbm: Any, db: Any, tick: int) -> bool:
    """坏结局检测（等价 agent_signals.detect_bad_end 的布尔部分）。

    仅 Phase 1 有效；找 phase1 节点指向 bad 结局的边并评估其 trigger。
    """
    node_id = _current_node_id(interp, getattr(hbm, "phase", ""))
    if node_id is None:
        return False
    for edge, dst in interp.graph.get_children(node_id):
        ending = interp.graph.endings.get(dst)
        if ending is not None and ending.kind == "bad":
            return interp.detect_edge(edge, db, hbm, tick)
    return False


def apply_routing_via_interpreter(
    interp: StoryInterpreter,
    hbm: Any,
    *,
    ipc_client: Any,
    db: Any,
    task_id: str,
    current_tick: int,
    ipc_timeout: float,
) -> Dict[str, Any]:
    """解释器驱动的 apply_routing，结构等价 routing.apply_routing。"""
    from agent_world.hbm_demo.features.f17_virtual_player.player_entity import (
        sync_player_place_on_routing,
    )
    from agent_world.hbm_demo.http.ipc_helper import (
        send_enqueue_script_event,
        send_move_agent,
    )

    applied: Dict[str, Any] = {"nodes": []}

    # 级联：与旧 apply_routing 的 A→B→C 顺序 if 块一致——一次转移改了 phase 后，
    # 立刻按新当前节点再检下一条转移（实践中下一节点时间窗为空，通常只触发一条）。
    guard = 0
    while guard <= len(interp.graph.nodes):
        guard += 1
        node_id = _current_node_id(interp, getattr(hbm, "phase", ""))
        if node_id is None:
            break
        fired = next(
            (e for e in _transition_edges(interp, node_id)
             if interp.detect_edge(e, db, hbm, int(current_tick))),
            None,
        )
        if fired is None:
            break
        edge = fired
        label = str(edge.raw.get("legacy_label") or edge.id)
        planned = interp.plan_actions(edge, current_tick=int(current_tick))

        # 规范执行顺序（与 routing.apply_routing 一致）：移动 → 地点变异 → 玩家换位/换phase → set_session
        for eff in [p for p in planned if p["type"] == "move_agent"]:
            send_move_agent(
                ipc_client,
                agent_id=int(eff["agent"]),
                place_id=str(eff["to"]),
                timeout=ipc_timeout,
            )

        has_mutation = False
        for eff in [p for p in planned if p["type"] == "place_mutation"]:
            mutation_event = {
                "id": f"route_{label.lower()}_mutate_{task_id}",
                "trigger": {"type": "at_condition", "expr": "True"},
                "effect": {
                    "type": "place_mutation",
                    "place_id": str(eff["place"]),
                    "attrs_patch": {"behavior_hint": str(eff["behavior_hint"])},
                },
            }
            send_enqueue_script_event(ipc_client, events=[mutation_event], timeout=ipc_timeout)
            has_mutation = True

        new_phase = next(
            (str(p["new_phase"]) for p in planned if p["type"] == "advance_player_place"),
            None,
        )
        if new_phase is not None:
            sync_player_place_on_routing(
                hbm,
                ipc_client=ipc_client,
                new_phase=new_phase,
                node=label,
                ipc_timeout=ipc_timeout,
            )

        tick_fields: Dict[str, int] = {}
        for eff in [p for p in planned if p["type"] == "set_session"]:
            setattr(hbm, str(eff["field"]), eff["value"])
            tick_fields[str(eff["field"])] = eff["value"]

        applied["nodes"].append(label)
        applied["phase"] = hbm.phase
        applied["place_id"] = hbm.place_id
        if has_mutation:
            applied["place_mutation"] = True
        applied.update(tick_fields)
        log.info("interpreter routing node %s at tick=%s", label, current_tick)

    return applied
