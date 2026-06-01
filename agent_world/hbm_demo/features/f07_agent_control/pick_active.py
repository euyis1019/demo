"""F07 L3 — 每拍激活哪些 agent（数据驱动，无随机、无单故事写死）。

谁本拍可跑 LLM 全由「有没有理由」决定：玩家刚说话→本幕在场 NPC 回应；有未读私信→回复(有上限)；
空拍→在本幕在场 NPC(由管理 agent 经 Story Pack 的 node.inject_agents 决定)里确定性轮转一个自主活动。
引擎不随机挑人、不强制移动、不写死任何故事的角色编号/幕名/地点（换 Story Pack 即换游戏）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Set

from agent_world.hbm_demo.features.f07_agent_control.config import is_f07_enabled
from agent_world.hbm_demo.features.f07_agent_control.conversation_control import (
    has_unread_inbound,
)

from agent_world.hbm_demo.features.f17_virtual_player.player_entity import (
    is_virtual_player_agent,
)

log = logging.getLogger("agent_world.hbm_demo.f07.pick_active")

RESPOND_TICKS = 2  # 玩家说话后只回应 ~2 拍，避免一句话被反复回好几拍
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
    passive_ticks_so_far: int = 0,
    batch_tick_index: int = 0,
) -> List[int]:
    """Return agent ids allowed to run LLM this tick.

    全程数据驱动、无随机激活——只在有明确理由时选 agent，是否真开口由 actor 自己反思（可 do_nothing）：
      1) 玩家刚开口 → 本幕在场 NPC(inject_agents) 在最初 ~2 拍回应（不刷屏）；
      2) inject agent 还没把玩家这句回完 → 继续给一拍；
      3) 任何 agent 有未读私信(RDC/群) → 回复，但每拍至多 MAX_REPLIERS 个，防止并发过载；
      4) 没有玩家输入的空拍 → 按**确定性轮转**让本幕在场 NPC 里轮到的那一个自主活动。
         谁在场、由谁推进，全由管理 agent 经 Story Pack 的 node.inject_agents 决定，引擎不随机挑人、不强制移动。
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
    # 4) 空拍场景活性：无玩家输入时，按确定性轮转给本幕在场 NPC 里轮到的那一个一拍，由它自主决定是否行动。
    #    无随机；每批至多放一个；低频（每 3 拍一次）保持节奏，且不与玩家回应窗口叠加。
    if not in_respond_window and passive_ticks_so_far < 1 and int(t) % 3 == 0:
        ambient = [aid for aid in inject_ids if aid not in seen]
        if ambient:
            add(ambient[(int(t) // 3) % len(ambient)])

    log.debug("F07 pick_active t=%s batch=%s inject_live=%s active=%s",
              t, batch_tick_index, inject_live, active)
    return active


def primary_active_ids(turn_context: Dict[str, Any]) -> List[int]:
    """本幕在场/主激活集 = Story Pack 当前 node 的 inject_agents（数据驱动，供通知目标与被动计数用）。"""
    return [int(x) for x in (turn_context.get("inject_agent_ids") or [])]
