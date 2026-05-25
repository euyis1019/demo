"""F07 L3 — tick active agent whitelist + passive tick rules."""

from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, Optional, Set

from agent_world.hbm_demo.features.f07_agent_control.config import (
    inject_exclusive_ticks_for,
    is_f07_enabled,
    load_turn_control,
)
from agent_world.hbm_demo.features.f07_agent_control.tool_guard import (
    passive_tick_probability,
)

log = logging.getLogger("agent_world.hbm_demo.f07.pick_active")

SAM_ID = 7


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


def _has_unread_inbound(
    agent_id: int,
    agent: Any,
    world: Any,
    t: int,
    *,
    rdc_from: Optional[int] = None,
) -> bool:
    db = getattr(world, "db", None)
    if db is None:
        return False
    last = getattr(agent, "last_message_seen_at", None)
    last_seen = -1 if last is None else int(last)

    try:
        rows = db.fetch_arrived_for(int(agent_id), int(t), last_seen)
    except Exception:  # noqa: BLE001
        rows = []

    if rdc_from is not None:
        return any(
            int(getattr(r, "sender_id", -1)) == int(rdc_from) for r in rows
        )

    if rows:
        return True

    places = getattr(world, "places", None)
    if places is None:
        return False
    place = places.L_t(agent_id)
    if not place:
        return False
    try:
        f2f = db.fetch_f2f_history_at(str(place), int(t), last_seen, limit=10)
    except Exception:  # noqa: BLE001
        return False
    for at_t, sender_id, _mid, _content in f2f:
        if int(sender_id) != int(agent_id) and int(at_t) > last_seen:
            return True
    return False


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
        if _has_unread_inbound(aid, agent, world, t, rdc_from=2):
            out.append(aid)

    passive_low = [int(x) for x in (cfg.get("passive_low_freq") or [])]
    for aid in passive_low:
        if aid in out:
            continue
        agent = _resolve_agent(agents, aid)
        if agent is None:
            continue
        if _has_unread_inbound(aid, agent, world, t):
            out.append(aid)

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

    # inject_exclusive — first N ticks after player inject: inject targets only.
    exclusive = inject_exclusive_ticks_for(phase)
    inject_ids = turn_context.get("inject_agent_ids") or []
    if exclusive > batch_tick_index and inject_ids:
        inject_set = {int(x) for x in inject_ids}
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

    for aid in _primary_ids(phase, player_turn):
        if aid in frozen:
            continue
        if aid not in seen:
            active.append(aid)
            seen.add(aid)

    cfg = _phase_cfg(phase)
    max_passive = int(cfg.get("passive_max_per_batch", 1))
    remaining = max(0, max_passive - passive_ticks_so_far)
    if remaining > 0:
        prob = passive_tick_probability(phase)
        rng = random.Random(int(t) * 1000 + player_turn)
        agents = getattr(world, "agents", None) or {}
        for aid in _passive_candidates(phase, player_turn, world, t, agents):
            if aid in frozen or aid in seen:
                continue
            if rng.random() > prob:
                continue
            active.append(aid)
            seen.add(aid)
            remaining -= 1
            if remaining <= 0:
                break

    log.debug(
        "F07 pick_active phase=%s turn=%s t=%s active=%s",
        phase,
        player_turn,
        t,
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
                out.append(int(key))
            except (TypeError, ValueError):
                aid = getattr(agent, "agent_id", None)
                if aid is not None:
                    out.append(int(aid))
        return sorted(out)
    for agent in agents:
        aid = getattr(agent, "agent_id", None)
        if aid is not None:
            out.append(int(aid))
    return sorted(out)
