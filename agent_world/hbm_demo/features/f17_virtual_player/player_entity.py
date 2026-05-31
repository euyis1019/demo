"""F17 — agent 0（虚拟玩家）注册判定。

剧情推进/玩家换位已由 LLM 导演按节点的 place_focus 数据驱动负责，旧的「相位→地点」MOVE
同步(sync_player_place_on_routing/target_place_for_phase 等)已退役删除。
"""

from __future__ import annotations

from agent_world.hbm_demo.features.f17_virtual_player.config import (
    is_f08_enabled,
    player_agent_id,
)

PLAYER_AGENT_ID = 0


def is_virtual_player_agent(agent_id: int) -> bool:
    return is_f08_enabled() and int(agent_id) == int(player_agent_id())


__all__ = ["PLAYER_AGENT_ID", "is_virtual_player_agent"]
