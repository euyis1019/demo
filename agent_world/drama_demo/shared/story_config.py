"""活跃故事的运行期配置门面(运行期数据驱动化)。

把"当前在玩哪个故事 + 该故事的地点/NPC/属性"从写死的 HBM phase 表，统一改成读活跃
Story Pack。剧情结构已改由 berts.yaml（条件→反应链）承载，story_graph 退役、节点门面函数
已删（图恒空），本门面只剩玩家起点/属性/地点/NPC 等世界原语读取。活跃故事默认 canglan_sword，
运行期可由 active_game / WorldManager（大厅选/建故事后）切换——active_story_id() 委托
active_game.get_active_story()，不再只读 env。纯读 shared/story_pack(D3：不依赖 features)，L1/L2 都可用。
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


def player_start_place(story_id: Optional[str] = None) -> str:
    """玩家起始地点：读 meta.player.start_place（story_graph 退役后图恒空，无节点 place_focus 可取）。"""
    pack = active_pack(story_id)
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


def current_clues(fired: Any, story_id: Optional[str] = None) -> List[str]:
    """当前玩家向「线索」：已上膛未触发非结局 bert 的 hint；**全空时兜底回开场钩子 onboarding.hook**，
    保证前端线索栏永不空白、玩家任何时候都看得到「我该朝哪使劲」（删幕后线索是唯一进度指引）。

    f01 开局快照 / f14 每回合 delta / session_start 三处统一走这里，避免「线索为空玩家两眼一抹黑」。
    """
    pack = active_pack(story_id)
    try:
        clues = list(pack.berts.current_hints(set(fired or [])))
    except Exception:  # noqa: BLE001
        clues = []
    if clues:
        return clues
    hook = ((pack.meta or {}).get("onboarding") or {}).get("hook")
    return [str(hook)] if hook else []
