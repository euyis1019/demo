"""活跃故事的运行期配置门面(运行期数据驱动化)。

把"当前在玩哪个故事 + 该故事的节点/地点/注入对象"从写死的 HBM phase 表，统一改成读
活跃 Story Pack。活跃故事默认 canglan_sword，运行期可由 active_game / WorldManager（大厅选/建
故事后）切换——active_story_id() 委托 active_game.get_active_story()，不再只读 env。纯读
shared/story_pack(D3：不依赖 features)，L1/L2 都可用。
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

from agent_world.drama_demo.shared.story_pack import StoryPack, load_story_pack


def active_story_id() -> str:
    from agent_world.drama_demo.shared import active_game

    return active_game.get_active_story()


@lru_cache(maxsize=8)
def _pack(story_id: str) -> StoryPack:
    return load_story_pack(story_id)


def clear_pack_cache() -> None:
    """清空活跃 Story Pack 的 lru 缓存。切故事后由 WorldManager 调，确保读到新故事的包，
    而不是上一个故事的残留缓存（公共出口，避免外部 reach-in 私有 _pack）。"""
    _pack.cache_clear()


def active_pack(story_id: Optional[str] = None) -> StoryPack:
    return _pack(story_id or active_story_id())


def initial_node_id(story_id: Optional[str] = None) -> str:
    return active_pack(story_id).graph.initial_node


def node_place(node_id: str, story_id: Optional[str] = None) -> str:
    node = active_pack(story_id).graph.nodes.get(node_id)
    return node.place_focus if node and node.place_focus else ""


def node_exists(node_id: str, story_id: Optional[str] = None) -> bool:
    """该 node_id 是否为活跃包里的已知节点（区分『查无此节点』与『节点存在但 inject 为空』）。"""
    return node_id in active_pack(story_id).graph.nodes


def node_inject_agents(node_id: str, story_id: Optional[str] = None) -> List[int]:
    node = active_pack(story_id).graph.nodes.get(node_id)
    return list(node.inject_agents) if node else []


def node_beats_label(node_id: str, story_id: Optional[str] = None) -> str:
    node = active_pack(story_id).graph.nodes.get(node_id)
    return node.beats_label if node else ""


def player_start_place(story_id: Optional[str] = None) -> str:
    """玩家起始地点：优先初始节点的 place_focus，回退 meta.player.start_place。"""
    pack = active_pack(story_id)
    init = pack.graph.initial_node
    node = pack.graph.nodes.get(init)
    if node and node.place_focus:
        return node.place_focus
    return str((pack.meta.get("player") or {}).get("start_place") or "")


def stats_design(story_id: Optional[str] = None) -> Dict[str, Any]:
    """活跃故事的属性面板设计：{judge_persona, dimensions:[{key,label,initial,description}]}（管理 agent 生成）。无则空。"""
    s = (active_pack(story_id).meta or {}).get("stats")
    return dict(s) if isinstance(s, dict) else {}


def stats_dimensions(story_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """属性维度列表（数据驱动；无则空——前端据此渲染 HUD、引擎据此泛化打分）。"""
    dims = stats_design(story_id).get("dimensions")
    return [dict(d) for d in dims] if isinstance(dims, list) else []


def initial_stats(story_id: Optional[str] = None) -> Dict[str, int]:
    """各维度初始值 {key: initial}（数据驱动；无 meta.stats 时空 dict）。"""
    return {
        str(d["key"]): int(d.get("initial", 0) or 0)
        for d in stats_dimensions(story_id) if d.get("key")
    }


def active_place_ids(story_id: Optional[str] = None) -> List[str]:
    """活跃故事的全部地点 id（喂玩家可见场景视图：room_f2f 按这些地点取 F2F）。"""
    places = active_pack(story_id).places.get("places") or []
    return [str(p.get("place_id")) for p in places if p.get("place_id")]


def active_npc_ids(story_id: Optional[str] = None) -> List[int]:
    """活跃故事的全部 NPC agent id（不含玩家 0；喂玩家可见的 agent 名册/位置/消息）。"""
    agents = active_pack(story_id).agents.get("agents") or []
    return [int(a["agent_id"]) for a in agents if int(a.get("agent_id", -1)) > 0]
