"""F07 L3 — tick active agent whitelist + passive tick rules."""

from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, Optional, Set

from agent_world.hbm_demo.features.f07_agent_control.config import (
    inject_exclusive_ticks_for,
    is_f07_enabled,
    load_turn_control,
    passive_tick_probability,
    resolve_inject_tick_count,
)
from agent_world.hbm_demo.features.f07_agent_control.conversation_control import (
    has_unread_inbound,
    inject_response_ticks,
    primary_notify_ticks,
)

from agent_world.hbm_demo.features.f08_virtual_player.player_entity import (
    is_virtual_player_agent,
)

log = logging.getLogger("agent_world.hbm_demo.f07.pick_active")

SAM_ID = 7
RECEPTION_AGENT_ID = 1


def _inject_live(turn_context: Dict[str, Any]) -> bool:
    """Player turn was enqueued — inject batch / notify windows apply."""
    return turn_context.get("player_inject_tick") is not None


def _phase_cfg(phase: str) -> Dict[str, Any]:
    phases = load_turn_control().get("phases") or {}
    return dict(phases.get(phase) or {})


def _primary_ids(phase: str, player_turn: int) -> List[int]:
    cfg = _phase_cfg(phase)
    primary = [int(x) for x in (cfg.get("primary_active") or [])]
    if phase == "Phase 3":
        sam_from = int(cfg.get("sam_rdc_from_turn", 16))
        if player_turn >= sam_from and SAM_ID not in primary:
            primary = list(primary) + [SAM_ID]
    return primary


def _frozen_ids(phase: str) -> Set[int]:
    cfg = _phase_cfg(phase)
    frozen = set(int(x) for x in (cfg.get("frozen") or []))
    present = set(int(x) for x in (cfg.get("present_silent") or []))
    return frozen | present


def _passive_candidates(
    phase: str,
    player_turn: int,
    world: Any,
    t: int,
    agents: Any,
) -> List[int]:
    cfg = _phase_cfg(phase)
    out: List[int] = []

    passive_rdc = [int(x) for x in (cfg.get("passive_rdc_reply") or [])]
    for aid in passive_rdc:
        agent = _resolve_agent(agents, aid)
        if agent is None:
            continue
        if has_unread_inbound(aid, agent, world, t, rdc_from=2):
            out.append(aid)

    passive_low = [int(x) for x in (cfg.get("passive_low_freq") or [])]
    for aid in passive_low:
        if aid in out:
            continue
        agent = _resolve_agent(agents, aid)
        if agent is None:
            continue
        if has_unread_inbound(aid, agent, world, t):
            out.append(aid)
            continue

    if phase == "Phase 3" and player_turn >= int(cfg.get("sam_rdc_from_turn", 16)):
        if SAM_ID not in out and SAM_ID not in _primary_ids(phase, player_turn):
            agent = _resolve_agent(agents, SAM_ID)
            if agent is not None and getattr(agent, "player_memory", None):
                if agent.player_memory:
                    out.append(SAM_ID)

    return out


def _resolve_agent(agents: Any, agent_id: int) -> Any:
    if hasattr(agents, "get"):
        return agents.get(agent_id)
    for a in agents:
        if int(getattr(a, "agent_id", -1)) == int(agent_id):
            return a
    return None


def _reception_already_welcomed(world: Any, since_t: int) -> bool:
    db = getattr(world, "world_db", None)
    if db is None:
        return False
    try:
        rows = db.fetch_f2f_history_at(
            "nvidia_reception",
            t_now=10**9,
            since_t=max(0, int(since_t)),
            limit=8,
        )
    except Exception:  # noqa: BLE001
        return False
    for _attempted_at, sender_id, _mid, _content in rows:
        if int(sender_id) == RECEPTION_AGENT_ID:
            return True
    return False


def _reception_opening_pending(
    turn_context: Dict[str, Any],
    world: Any,
    t: int,
    batch_tick_index: int,
) -> bool:
    if batch_tick_index != 0:
        return False
    start_tick = int(turn_context.get("start_tick", 0) or 0)
    if _reception_already_welcomed(world, start_tick):
        return False
    db = getattr(world, "world_db", None)
    if db is None:
        return int(t) <= start_tick + 1
    return int(t) >= start_tick


def pick_active_ids(
    turn_context: Dict[str, Any],
    world: Any,
    t: int,
    *,
    passive_ticks_so_far: int = 0,
    batch_tick_index: int = 0,
) -> List[int]:
    """Return agent ids allowed to run LLM this tick."""
    if not is_f07_enabled():
        agents = getattr(world, "agents", None) or {}
        return _all_active_agent_ids(agents)

    phase = str(turn_context.get("phase", "Phase 1"))
    player_turn = int(turn_context.get("player_turn", 1))
    frozen = _frozen_ids(phase)
    inject_ids = [int(x) for x in (turn_context.get("inject_agent_ids") or [])]
    inject_set = set(inject_ids)
    exclusive = inject_exclusive_ticks_for(phase)
    agents = getattr(world, "agents", None) or {}
    inject_live = _inject_live(turn_context)

    # inject_exclusive — first N ticks after player inject: inject targets only.
    if inject_live and exclusive > batch_tick_index and inject_ids:
        primary = _primary_ids(phase, player_turn)
        active = [
            aid for aid in primary if aid in inject_set and aid not in frozen
        ]
        log.debug(
            "F07 inject_exclusive phase=%s batch_tick=%s active=%s",
            phase,
            batch_tick_index,
            active,
        )
        return active

    active: List[int] = []
    seen: Set[int] = set()

    def _add(aid: int) -> None:
        if is_virtual_player_agent(aid):
            return
        if aid in frozen or aid in seen:
            return
        active.append(int(aid))
        seen.add(int(aid))

    primary = _primary_ids(phase, player_turn)

    # 1) Unread inbound — reply promptly.
    for aid in primary:
        agent = _resolve_agent(agents, aid)
        if agent is None:
            continue
        if has_unread_inbound(aid, agent, world, t):
            _add(aid)

    # 2) Inject agent while player_memory pending.
    for aid in inject_set:
        agent = _resolve_agent(agents, aid)
        if agent is None:
            continue
        mem = getattr(agent, "player_memory", None)
        if mem and len(mem) > 0:
            _add(aid)

    # 3) Inject batch window — only after real player inject (not bootstrap mirror).
    inject_batch_len = resolve_inject_tick_count(phase, inject_response_ticks(phase))
    notify_until = exclusive + primary_notify_ticks(phase)
    if inject_live and batch_tick_index < inject_batch_len:
        for aid in inject_set:
            _add(aid)
    elif (
        not inject_live
        and phase == "Phase 1"
        and RECEPTION_AGENT_ID in inject_set
        and _reception_opening_pending(turn_context, world, t, batch_tick_index)
    ):
        # One pre-player opening beat after session/start resets the L3 window.
        _add(RECEPTION_AGENT_ID)
    if inject_live and batch_tick_index < notify_until:
        for aid in primary:
            if aid not in inject_set:
                _add(aid)

    # 4) Passive agents, unread-driven.
    cfg = _phase_cfg(phase)
    max_passive = int(cfg.get("passive_max_per_batch", 1))
    remaining = max(0, max_passive - passive_ticks_so_far)
    if remaining > 0:
        prob = passive_tick_probability(phase)
        rng = random.Random(int(t) * 1000 + player_turn)
        for aid in _passive_candidates(phase, player_turn, world, t, agents):
            if aid in seen:
                continue
            if rng.random() > prob:
                continue
            _add(aid)
            remaining -= 1
            if remaining <= 0:
                break

    log.debug(
        "F07 pick_active phase=%s turn=%s t=%s batch=%s active=%s",
        phase,
        player_turn,
        t,
        batch_tick_index,
        active,
    )
    return active


def primary_active_ids(turn_context: Dict[str, Any]) -> List[int]:
    """Primary L3 set (for scripted_notification targets)."""
    phase = str(turn_context.get("phase", "Phase 1"))
    player_turn = int(turn_context.get("player_turn", 1))
    frozen = _frozen_ids(phase)
    return [aid for aid in _primary_ids(phase, player_turn) if aid not in frozen]


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
