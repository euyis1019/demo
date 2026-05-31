"""活跃故事的运行期配置门面(运行期数据驱动化)。

把"当前在玩哪个故事 + 该故事的节点/地点/注入对象"从写死的 HBM phase 表，统一改成读
活跃 Story Pack。活跃故事由 env `HBM_STORY_ID` 决定(默认 canglan_sword)。纯读 shared/story_pack
(D3：不依赖 features)，L1/L2 都可用。
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

from agent_world.hbm_demo.shared.story_pack import StoryPack, load_story_pack


def active_story_id() -> str:
    return (os.environ.get("HBM_STORY_ID") or "canglan_sword").strip() or "canglan_sword"


@lru_cache(maxsize=8)
def _pack(story_id: str) -> StoryPack:
    return load_story_pack(story_id)


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
    return str((pack.meta.get("player") or {}).get("start_place") or "nvidia_reception")


def active_place_ids(story_id: Optional[str] = None) -> List[str]:
    """活跃故事的全部地点 id（喂玩家可见场景视图：room_f2f 按这些地点取 F2F）。"""
    places = active_pack(story_id).places.get("places") or []
    return [str(p.get("place_id")) for p in places if p.get("place_id")]


def active_npc_ids(story_id: Optional[str] = None) -> List[int]:
    """活跃故事的全部 NPC agent id（不含玩家 0；喂玩家可见的 agent 名册/位置/消息）。"""
    agents = active_pack(story_id).agents.get("agents") or []
    return [int(a["agent_id"]) for a in agents if int(a.get("agent_id", -1)) > 0]
