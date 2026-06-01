"""bert 驱动的剧情路由（LLM 判触发 → 注入反应，无任何硬规则）。

剧情由一组 bert（条件→反应）规则驱动：玩家做到某条 bert 的 trigger，Bert 导演就把该 bert 的
reaction 注入到 target NPC 的下一拍 prompt（经 knowledge.py 读 hbm.bert_reactions）；触发后按
once/requires/arms 更新「上膛」集合（反应链）；命中「结局 bert」则交还 watcher 收尾。
完全数据驱动 + LLM 判断——无关键词 / 信号 / 超时 / 幕 / 节点等任何硬结构。换 berts.yaml 即换剧情。

导演只在玩家有**新发言**后判一次，既省 LLM，又保证 NPC 有时间在场回应、剧情不被一句话连环击穿。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Dict, List

from agent_world.drama_demo.features.f05_story_routing.interpreter import StoryInterpreter

log = logging.getLogger("agent_world.drama_demo.f05.interp")


@lru_cache(maxsize=8)
def get_interpreter(story_id: str) -> StoryInterpreter:
    """按 story_id 缓存解释器（Story Pack 加载一次，提供 bert 规则集访问）。"""
    return StoryInterpreter.for_story(story_id)


def _gather_scene(ipc_client: Any, place: str, agent_ids: List[int], ipc_timeout: float) -> None:
    """把指定 **NPC** 聚到某地点，让反应同场可见。★绝不移动玩家(agent 0)——玩家位置完全由玩家自己主导。"""
    from agent_world.drama_demo.http.ipc_helper import send_move_agent

    if not place:
        return
    for aid in agent_ids:
        if int(aid) == 0:  # 兜底：永不搬玩家
            continue
        try:
            send_move_agent(ipc_client, agent_id=int(aid), place_id=str(place), timeout=ipc_timeout)
        except Exception as exc:  # noqa: BLE001
            log.warning("gather_scene move %s→%s failed: %s", aid, place, exc)


def setup_scene_for_node(interp: StoryInterpreter, hbm: Any, *, ipc_client: Any, ipc_timeout: float) -> None:
    """开局聚场（bert 化）：把「开局就上膛」的 bert 的 target NPC 聚到玩家所在地，
    让玩家一上来就有相关角色可面对面互动（开场戏），而不是独自空房。其余 NPC 仍各就各位。
    后续某条 bert 触发时，route_story 再把那条的 target 聚到玩家面前。"""
    berts = getattr(interp, "berts", None)
    place = str(getattr(hbm, "place_id", "") or "")
    if not berts or not berts.berts or not place:
        return
    fired = set(getattr(hbm, "fired_berts", None) or [])
    # 只把「第一条开局上膛的非结局 bert」的 target 聚到玩家面前当开场对手戏——只聚 1 人，
    # 避免把全部 NPC 塞进一个房间触发容量上限被拒；其余 NPC 各就各位，玩家可自行走去找。
    targets = [
        int(berts.berts[bid].target)
        for bid in berts.armed_ids(fired)
        if not berts.berts[bid].is_ending and berts.berts[bid].target
    ]
    if targets:
        _gather_scene(ipc_client, place, targets[:1], ipc_timeout)


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
    """bert 驱动路由：玩家有新发言 → LLM 判哪条上膛的 bert 命中 → 注入反应/收场。"""
    from agent_world.drama_demo.features.f05_story_routing import director

    applied: Dict[str, Any] = {"nodes": [], "ending": None, "events": []}
    berts = getattr(interp, "berts", None)
    if not berts or not berts.berts:
        return applied  # 旧任务包或空包：无 bert，不路由

    fired = set(hbm.fired_berts or [])
    armed = [berts.berts[bid] for bid in berts.armed_ids(fired)]
    if not armed:
        return applied  # 全部触发完/无上膛：剧情已走完可触发部分

    # 只在玩家有「新发言」时才惊动导演（省 LLM；也避免对同一句反复判）。读玩家所在地的近期对话。
    place = str(getattr(hbm, "place_id", "") or "")
    since_t = int(getattr(hbm, "start_tick", 0) or 0)
    lp = director.latest_player_tick(db, place, since_t, int(current_tick))
    if lp is None or lp <= int(getattr(hbm, "last_judged_player_tick", -1) or -1):
        return applied
    hbm.last_judged_player_tick = lp
    # 消费即清：上一轮写进的 reaction，到「玩家又开了新口」这一刻，已经由两次发言之间的 inject 注入并被 target 演过。
    # 此处清掉旧 reaction，避免它常驻 NPC 的 prompt 让其反复复读同一反应（reaction 是一次性剧情节拍，不是常态设定）。
    if getattr(hbm, "bert_reactions", None):
        hbm.bert_reactions = {}

    transcript = director.scene_transcript(db, place, since_t, int(current_tick), name_map)
    decision = director.judge_bert_triggers(armed, transcript, name_map)
    if decision is None:
        return applied  # 本拍没有 bert 被触发

    bid = decision["triggered"]
    b = berts.berts[bid]
    if bid not in fired:
        hbm.fired_berts = [*hbm.fired_berts, bid]
    applied["nodes"].append(bid)  # 复用既有「有推进」信号通道（持久化用；前端无任务横幅）

    if b.is_ending:
        # 结局 bert：写收场信息（kind/summary 落到 hbm，供 watcher/前端读），交还 watcher 收尾。
        hbm.ending_id = bid
        hbm.ending_summary = str((b.ending or {}).get("summary") or "")
        hbm.ending_kind = str((b.ending or {}).get("kind") or "neutral")
        applied["ending"] = bid
        log.info("bert 结局 %s（%s）触发", bid, hbm.ending_kind)
        return applied

    # 普通 bert：把 reaction 注入 target NPC 的下一拍 prompt（knowledge.py 读 hbm.bert_reactions）。
    target = int(b.target or 0)
    if target and b.reaction:
        reactions = dict(getattr(hbm, "bert_reactions", None) or {})
        reactions[str(target)] = b.reaction
        hbm.bert_reactions = reactions
        # 把 target 聚到反应该发生的地点（bert 指定 place，否则玩家所在地），让反应当面可见。
        _gather_scene(ipc_client, b.place or place, [target], ipc_timeout)
        log.info("bert %s 触发：注入反应给 agent %s", bid, target)
    return applied
