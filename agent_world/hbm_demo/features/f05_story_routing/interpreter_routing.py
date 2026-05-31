"""解释器→运行期副作用桥（节点驱动路由）。

把 StoryInterpreter 的纯决策（detect_edge / plan_actions）落到 watcher 的运行期副作用上：
按 session.current_node_id 定位当前剧情节点，玩家台词触发出边即推进（IPC 移动 agent、
place_mutation 入队、set_session 写时间窗字段、玩家随节点换位/换 phase），指向结局则交还
watcher 收尾。完全数据驱动，无 HBM phase/agent_id 硬编码——换任意 Story Pack 即换游戏。

仅当 `is_story_pack_routing_enabled()`（HBM_STORY_PACK_ROUTING=1）时 watcher 走本路径；
默认仍走 routing.py 旧 HBM if 链。canglan_sword live 试玩已端到端验证本路径玩到结局。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Dict, List

from agent_world.hbm_demo.features.f05_story_routing.interpreter import StoryInterpreter

log = logging.getLogger("agent_world.hbm_demo.f05.interp")


@lru_cache(maxsize=8)
def get_interpreter(story_id: str) -> StoryInterpreter:
    """按 story_id 缓存解释器（Story Pack 加载一次）。"""
    return StoryInterpreter.for_story(story_id)


def _gather_scene(ipc_client: Any, place: str, agent_ids: List[int], ipc_timeout: float) -> None:
    """把这一拍该在场的角色(玩家+本节点 inject_agents)聚到该地点，让对话同场可见。"""
    from agent_world.hbm_demo.http.ipc_helper import send_move_agent

    if not place:
        return
    for aid in agent_ids:
        try:
            send_move_agent(ipc_client, agent_id=int(aid), place_id=str(place), timeout=ipc_timeout)
        except Exception as exc:  # noqa: BLE001
            log.warning("gather_scene move %s→%s failed: %s", aid, place, exc)


def setup_scene_for_node(interp: StoryInterpreter, hbm: Any, *, ipc_client: Any, ipc_timeout: float) -> None:
    """把当前节点的场景布好：玩家 + 该节点 inject_agents 聚到该节点地点。会话开局/换节点各调一次。"""
    node = interp.graph.nodes.get(getattr(hbm, "current_node_id", None) or interp.graph.initial_node)
    if node is None:
        return
    place = node.place_focus or getattr(hbm, "place_id", "")
    _gather_scene(ipc_client, place, [0, *node.inject_agents], ipc_timeout)


def route_story(
    interp: StoryInterpreter,
    hbm: Any,
    *,
    ipc_client: Any,
    db: Any,
    task_id: str,
    current_tick: int,
    ipc_timeout: float,
) -> Dict[str, Any]:
    """节点驱动路由：当前节点的出边被玩家台词触发即推进；指向结局则返回 ending（watcher 收尾）。

    完全数据驱动，无 HBM phase/agent_id 硬编码。换任意 Story Pack 即换游戏。
    """
    from agent_world.hbm_demo.http.ipc_helper import send_enqueue_script_event

    g = interp.graph
    applied: Dict[str, Any] = {"nodes": [], "ending": None, "events": []}
    guard = 0
    while guard <= len(g.nodes):
        guard += 1
        node_id = getattr(hbm, "current_node_id", None) or g.initial_node
        node = g.nodes.get(node_id)
        if node is None:
            break
        fired = next(
            (e for e, _dst in g.get_children(node_id) if interp.detect_edge(e, db, hbm, int(current_tick))),
            None,
        )
        if fired is None:
            break

        # 边的显式副作用（移动指定 agent / 地点变异 / 写会话时间窗字段）
        planned = interp.plan_actions(fired, current_tick=int(current_tick))
        for eff in [p for p in planned if p["type"] == "move_agent"]:
            _gather_scene(ipc_client, str(eff["to"]), [int(eff["agent"])], ipc_timeout)
        for eff in [p for p in planned if p["type"] == "place_mutation"]:
            send_enqueue_script_event(
                ipc_client,
                events=[{
                    "id": f"mutate_{node_id}_{task_id}",
                    "trigger": {"type": "at_condition", "expr": "True"},
                    "effect": {"type": "place_mutation", "place_id": str(eff["place"]),
                               "attrs_patch": {"behavior_hint": str(eff["behavior_hint"])}},
                }],
                timeout=ipc_timeout,
            )
        # set_session：写 phaseN_start_tick 等时间窗字段（value 已由 plan_actions 把 'current_tick'
        # 解析为 int）。漏写会让下游节点的 window_since 回退到开局，使历史信号误触发、剧情一拍内连环
        # 塌缩；写入后下游同拍窗口 (start_tick, current_tick] 为空，天然防级联。
        for eff in [p for p in planned if p["type"] == "set_session"]:
            setattr(hbm, str(eff["field"]), eff["value"])
        # 注：advance_player_place 不单独处理——玩家换位/换 phase 由下面节点原生推进
        # （place=nxt.place_focus + _gather_scene 移动玩家 0 + hbm.phase=nxt.beats_label）统一承担，
        # 避免依赖 HBM 相位耦合的 sync_player_place_on_routing。

        if g.is_ending(fired.dst):
            applied["ending"] = fired.dst
            return applied

        nxt = g.nodes.get(fired.dst)
        if nxt is None:  # 未经 validate 的包可能有悬空 dst——停止推进而非 KeyError
            log.warning("route_story: 边 dst=%s 既非结局也非已知节点，停止推进", fired.dst)
            break

        # 推进到下一节点：布好新场景（玩家 + 该节点 inject_agents 聚到新地点）
        place = nxt.place_focus or hbm.place_id
        _gather_scene(ipc_client, place, [0, *nxt.inject_agents], ipc_timeout)
        hbm.current_node_id = fired.dst
        hbm.phase = nxt.beats_label or hbm.phase
        hbm.place_id = place
        applied["nodes"].append(fired.dst)
        applied["events"].append({
            "id": f"node_{fired.dst}_{task_id}",
            "at_tick": int(current_tick),
            "kind": "phase_route",
            "title": nxt.beats_label or fired.dst,
            "content": nxt.summary or "",
            "place_id": place,
        })
        log.info("story node → %s (%s)", fired.dst, nxt.beats_label)
    return applied
