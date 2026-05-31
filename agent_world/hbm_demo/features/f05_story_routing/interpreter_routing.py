"""导演驱动的剧情路由（LLM 推进世界，无任何硬规则）。

按 session.current_node_id 定位当前幕，把本幕的真实对话喂给 LLM 导演（director.judge_transition）
判断是否推进、推进到哪条出边的 dst；指向结局则交还 watcher 收尾。完全数据驱动 + LLM 判断，
无关键词 / 信号 / 超时等硬检测。换任意 Story Pack 即换游戏。

导演每「幕」只在玩家有**新发言**后判一次（且推进至多一节点/拍），既省 LLM 调用，又保证
NPC 有时间在场回应、剧情不会被一句话瞬间连环击穿。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Dict, List

from agent_world.hbm_demo.features.f05_story_routing.interpreter import StoryInterpreter

log = logging.getLogger("agent_world.hbm_demo.f05.interp")


@lru_cache(maxsize=8)
def get_interpreter(story_id: str) -> StoryInterpreter:
    """按 story_id 缓存解释器（Story Pack 加载一次，提供图访问）。"""
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
    name_map: Dict[int, str],
) -> Dict[str, Any]:
    """导演驱动路由：玩家有新发言 → LLM 读本幕对话判断是否推进 → 推进一节点或返回结局。"""
    from agent_world.hbm_demo.features.f05_story_routing import director

    g = interp.graph
    applied: Dict[str, Any] = {"nodes": [], "ending": None, "events": []}
    node_id = getattr(hbm, "current_node_id", None) or g.initial_node
    node = g.nodes.get(node_id)
    if node is None:
        return applied

    since_t = int(getattr(hbm, "node_entered_tick", None) or getattr(hbm, "start_tick", 0) or 0)
    place = node.place_focus or getattr(hbm, "place_id", "")

    # 只在玩家有「新发言」时才惊动导演（省 LLM；也避免对同一句反复判）。
    lp = director.latest_player_tick(db, place, since_t, int(current_tick))
    if lp is None or lp <= int(getattr(hbm, "last_judged_player_tick", -1) or -1):
        return applied
    hbm.last_judged_player_tick = lp

    transcript = director.scene_transcript(db, place, since_t, int(current_tick), name_map)
    decision = director.judge_transition(g, node_id, transcript, name_map)
    if decision is None:
        return applied  # 导演判定：留在本幕

    dst = str(decision["target"])
    if g.is_ending(dst):
        applied["ending"] = dst
        return applied

    nxt = g.nodes.get(dst)
    if nxt is None:  # 悬空 dst（未经 validate 的脏包）——停止推进而非 KeyError
        log.warning("route_story: dst=%s 既非结局也非已知节点，停止推进", dst)
        return applied

    # 推进到下一幕：布好新场景（玩家 + 该节点 inject_agents 聚到新地点），重置导演窗口
    new_place = nxt.place_focus or getattr(hbm, "place_id", "")
    _gather_scene(ipc_client, new_place, [0, *nxt.inject_agents], ipc_timeout)
    hbm.current_node_id = dst
    hbm.phase = nxt.beats_label or hbm.phase
    hbm.place_id = new_place
    hbm.node_entered_tick = int(current_tick)
    hbm.last_judged_player_tick = None
    applied["nodes"].append(dst)
    applied["events"].append({
        "id": f"node_{dst}_{task_id}",
        "at_tick": int(current_tick),
        "kind": "phase_route",
        "title": nxt.beats_label or dst,
        "content": nxt.summary or "",
        "place_id": new_place,
    })
    log.info("story node → %s (%s): %s", dst, nxt.beats_label, decision.get("reason"))
    return applied
