"""群聊门控判定（需求三）：玩家须先 F2F 见过某群成员、且该成员 F2F 同意，才能加入该群。

纯**只读**判定，不写库——F2F 历史读 f06 只读库；「是否同意」交 f05 LLM 导演按对话语义判定
（无关键词硬规则，跨 feature 经对方公共出口，遵 D2）。执行入群在别处（f17 + L1 桥），本模块只回答"能不能"。
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


PLAYER_AGENT_ID = 0

# 入群同意判定缓存：键 (agent_id, place_id) → (该 agent 已说的台词条数, 上次 LLM 判定)。
# joinable-groups 会被前端轮询、且每个群成员要判一次——只要该 NPC 没说出新话(条数不变)就复用判定，
# 不重复调 LLM；他说了新话(条数变化)才重判。避免「每成员每轮询一次同步 LLM」的开销。
_consent_cache: Dict[Tuple[int, str], Tuple[int, bool]] = {}


def _agent_name(agent_id: int) -> str:
    try:
        from agent_world.drama_demo.shared import story_config

        for a in story_config.active_pack().agents.get("agents") or []:
            if int(a.get("agent_id", -1)) == int(agent_id):
                return str(a.get("name") or f"Agent{agent_id}")
    except Exception:  # noqa: BLE001
        pass
    return f"Agent{agent_id}"


def _player_met_agent(db: Any, agent_id: int, place_id: str, *, since_t: int, t_now: int, player_id: int) -> bool:
    """玩家与该 agent 在 place_id 有过双向 F2F（都在场说过话）= 见过面。"""
    npc_f2f = db.fetch_f2f_from_sender_at(place_id, int(agent_id), int(t_now), int(since_t))
    if not npc_f2f:
        return False
    player_f2f = db.fetch_f2f_from_sender_at(place_id, int(player_id), int(t_now), int(since_t))
    return bool(player_f2f)


def _agent_consented(db: Any, agent_id: int, place_id: str, *, since_t: int, t_now: int) -> bool:
    """该 agent 是否同意玩家入群——由 LLM 导演读他对玩家说过的话语义判定（无关键词硬规则）。

    按该 NPC 的台词条数缓存：他没说新话就复用上次判定，避免轮询/多成员时重复同步调 LLM。
    """
    rows = db.fetch_f2f_from_sender_at(place_id, int(agent_id), int(t_now), int(since_t))
    lines = [str(content) for _at_t, _sender, _mid, content in rows if str(content or "").strip()]
    if not lines:
        return False

    key = (int(agent_id), str(place_id))
    cached = _consent_cache.get(key)
    if cached is not None and cached[0] == len(lines):
        return cached[1]  # 台词条数没变 → NPC 没说新话 → 复用判定，省一次 LLM

    from agent_world.drama_demo.features.f05_story_routing.director import judge_group_consent

    verdict = judge_group_consent(_agent_name(agent_id), lines)
    if len(_consent_cache) > 256:  # 轻量上限，避免长跑膨胀
        _consent_cache.clear()
    _consent_cache[key] = (len(lines), verdict)
    return verdict


def can_player_join_group(
    db: Any,
    group_id: int,
    *,
    player_place: str,
    since_t: int,
    t_now: int,
    player_id: int = PLAYER_AGENT_ID,
) -> bool:
    """玩家能否加入 group_id：群里存在某成员，玩家已 F2F 见过他、且他 F2F 同意。

    db 为 f06 只读 world_db（需有 fetch_group_members / fetch_f2f_from_sender_at）。
    """
    members = db.fetch_group_members().get(int(group_id), [])
    for member in members:
        m = int(member)
        if m == int(player_id):
            continue
        if _player_met_agent(db, m, player_place, since_t=since_t, t_now=t_now, player_id=player_id) and \
           _agent_consented(db, m, player_place, since_t=since_t, t_now=t_now):
            return True
    return False


def joinable_groups_for_player(
    db: Any, *, player_place: str, since_t: int, t_now: int, player_id: int = PLAYER_AGENT_ID
) -> List[int]:
    """返回玩家当前可加入的全部 group_id（供前端只显示可加群）。"""
    out: List[int] = []
    for gid in db.fetch_group_members().keys():
        if can_player_join_group(
            db, int(gid), player_place=player_place, since_t=since_t, t_now=t_now, player_id=player_id
        ):
            out.append(int(gid))
    return out
