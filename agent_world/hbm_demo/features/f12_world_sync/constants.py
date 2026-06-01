"""F12 shared constants — 玩家可见地点/NPC 名册（数据驱动：取活跃 Story Pack）。"""

from __future__ import annotations

# 中性空兜底——地点/NPC 名册数据驱动：room_places()/agent_roster() 主路径取活跃 Story Pack；
# 无 pack 时返回空，由上层处理（不再写死任何故事的地点/角色编号）。
HBM_ROOM_PLACES: tuple[str, ...] = ()

HBM_AGENT_IDS: tuple[int, ...] = ()


def room_places() -> tuple[str, ...]:
    """玩家可见场景的地点清单——数据驱动：取活跃 Story Pack 的全部地点；
    无 pack/异常时回退旧 HBM 四室（保证默认 HBM 路径不变）。"""
    try:
        from agent_world.hbm_demo.shared import story_config

        ids = tuple(story_config.active_place_ids())
        return ids or HBM_ROOM_PLACES
    except Exception:  # noqa: BLE001
        return HBM_ROOM_PLACES


def agent_roster() -> tuple[int, ...]:
    """玩家可见的 NPC 名册——数据驱动：取活跃 Story Pack 的全部 NPC id；回退旧 HBM 7 人。"""
    try:
        from agent_world.hbm_demo.shared import story_config

        ids = tuple(story_config.active_npc_ids())
        return ids or HBM_AGENT_IDS
    except Exception:  # noqa: BLE001
        return HBM_AGENT_IDS


__all__ = [
    "HBM_AGENT_IDS",
    "HBM_ROOM_PLACES",
    "agent_roster",
    "room_places",
]
