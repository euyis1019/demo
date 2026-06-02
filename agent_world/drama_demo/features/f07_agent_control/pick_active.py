"""F07 L3 — 每拍激活哪些 agent（数据驱动，无随机、无单故事写死）。

谁本拍可跑 LLM 全由「有没有理由」决定：玩家刚说话→本幕在场 NPC 回应；有未读私信→回复(有上限)；
空拍→默认静默等玩家（回合制；ambient 默认关，需 Story Pack 显式开才轮转在场 NPC 自主活动）。
引擎不随机挑人、不强制移动、不写死任何故事的角色编号/幕名/地点（换 Story Pack 即换游戏）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Set

from agent_world.drama_demo.features.f07_agent_control.config import is_f07_enabled
from agent_world.drama_demo.features.f07_agent_control.conversation_control import (
    has_unread_inbound,
)

from agent_world.drama_demo.features.f17_virtual_player.player_entity import (
    is_virtual_player_agent,
)

log = logging.getLogger("agent_world.drama_demo.f07.pick_active")

RESPOND_TICKS = 1  # 玩家说话后给在场 NPC 1 拍回应机会即可——「还没回完」由规则2(player_memory 未清)兜着继续，
# 回完(mark_communication_action 清 player_memory)就立刻收手。设 2 会在 NPC 已回完后再白跑一拍 do_nothing，
# 而每拍都阻塞等一次 LLM(数秒)，白白拖慢玩家下一句的处理——故收到 1，让 actor 回应更跟手。
MAX_REPLIERS = 2   # 每拍最多让 2 个有未读私信的 agent 回复，防止并发 LLM 压垮 Runner→玩家指令 IPC 超时


def _inject_live(turn_context: Dict[str, Any]) -> bool:
    """Player turn was enqueued — inject batch / notify windows apply."""
    return turn_context.get("player_inject_tick") is not None


def _resolve_agent(agents: Any, agent_id: int) -> Any:
    if hasattr(agents, "get"):
        return agents.get(agent_id)
    for a in agents:
        if int(getattr(a, "agent_id", -1)) == int(agent_id):
            return a
    return None


def _all_active_agent_ids(agents: Any) -> List[int]:
    out: List[int] = []
    if hasattr(agents, "items"):
        for key, agent in agents.items():
            try:
                aid = int(key)
            except (TypeError, ValueError):
                aid = getattr(agent, "agent_id", None)
                if aid is None:
                    continue
                aid = int(aid)
            if is_virtual_player_agent(aid):
                continue
            out.append(aid)
        return sorted(out)
    for agent in agents:
        aid = getattr(agent, "agent_id", None)
        if aid is not None and not is_virtual_player_agent(int(aid)):
            out.append(int(aid))
    return sorted(out)


def pick_active_ids(
    turn_context: Dict[str, Any],
    world: Any,
    t: int,
    *,
    batch_tick_index: int = 0,
) -> List[int]:
    """Return agent ids allowed to run LLM this tick.

    全程数据驱动、无随机激活、无强制开口——只在有明确理由时**给 agent 出手机会**，是否真开口由 actor
    自己反思（可 do_nothing）：
      1) 玩家刚开口 → 本幕在场 NPC(inject_agents) 在最初 ~2 拍获得回应机会（回完即止，之后静默等玩家）；
      2) inject agent 还没把玩家这句回完 → 继续给一拍机会；
      3) 任何 agent 有未读私信(RDC/群) → 给回复机会，但每拍至多 MAX_REPLIERS 个，防止并发过载；
      4) 空拍（无玩家输入）默认**静默等玩家**（回合制）；仅当 Story Pack 显式开 ambient_enabled 才把出手机会
         平等交给在场 NPC 自主决定行动——引擎不再「每 N 拍轮一个强制开口」，活的世界来自 agent 自己决定。
    """
    if not is_f07_enabled():
        agents = getattr(world, "agents", None) or {}
        return _all_active_agent_ids(agents)

    agents = getattr(world, "agents", None) or {}
    active: List[int] = []
    seen: Set[int] = set()

    def add(aid: int) -> None:
        if is_virtual_player_agent(int(aid)) or int(aid) in seen:
            return
        active.append(int(aid))
        seen.add(int(aid))

    inject_ids = [int(x) for x in (turn_context.get("inject_agent_ids") or [])]
    inject_live = _inject_live(turn_context)
    in_respond_window = inject_live and batch_tick_index < RESPOND_TICKS

    # 1) 玩家刚开口：本幕在场 NPC 在最初 ~2 拍回应
    if in_respond_window:
        for aid in inject_ids:
            add(aid)
    # 2) inject agent 还没把玩家这句回完
    for aid in inject_ids:
        agent = _resolve_agent(agents, aid)
        if agent is not None and getattr(agent, "player_memory", None):
            add(aid)
    # 3) 有未读私信就回——任何 agent，但每拍至多 MAX_REPLIERS 个（防 Runner 并发过载→玩家指令 IPC 超时）
    repliers = 0
    for aid in _all_active_agent_ids(agents):
        if repliers >= MAX_REPLIERS:
            break
        if aid in seen:
            continue
        agent = _resolve_agent(agents, aid)
        if agent is not None and has_unread_inbound(aid, agent, world, t):
            add(aid)
            repliers += 1
    # 4) 空拍场景活性（默认关闭——回合制：玩家不开口时本幕 NPC 默认静默地等他）。
    #    需要「活的世界」的故事可经 turn_context 置 ambient_enabled=True 打开；打开后引擎**不再**用
    #    「每 N 拍轮一个 NPC 强制开口」这种死规则，而是把出手机会平等交给本幕在场 NPC，由每个 actor
    #    自己反思这一拍要不要行动（可 do_nothing）——活的世界来自 agent 自主决定行动，不是引擎逼谁开口。
    #    仅保留 MAX_REPLIERS 并发上限（纯基础设施：防一拍并发太多 LLM 压垮 Runner→玩家指令 IPC 超时）。
    if turn_context.get("ambient_enabled") and not in_respond_window:
        offered = 0
        for aid in inject_ids:
            if offered >= MAX_REPLIERS:
                break
            if aid in seen:
                continue
            add(aid)
            offered += 1

    log.debug("F07 pick_active t=%s batch=%s inject_live=%s active=%s",
              t, batch_tick_index, inject_live, active)
    return active


def primary_active_ids(turn_context: Dict[str, Any]) -> List[int]:
    """本幕在场/主激活集 = Story Pack 当前 node 的 inject_agents（数据驱动，供通知目标与被动计数用）。"""
    return [int(x) for x in (turn_context.get("inject_agent_ids") or [])]
