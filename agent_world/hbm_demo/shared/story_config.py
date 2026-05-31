"""活跃故事的运行期配置门面(运行期数据驱动化)。

把"当前在玩哪个故事 + 该故事的节点/地点/注入对象"从写死的 HBM phase 表，统一改成读
活跃 Story Pack。活跃故事由 env `HBM_STORY_ID` 决定(默认 hbm_memory_war)。纯读 shared/story_pack
(D3：不依赖 features)，L1/L2 都可用。
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

from agent_world.hbm_demo.shared.story_pack import StoryPack, load_story_pack


def active_story_id() -> str:
    return (os.environ.get("HBM_STORY_ID") or "hbm_memory_war").strip() or "hbm_memory_war"


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
