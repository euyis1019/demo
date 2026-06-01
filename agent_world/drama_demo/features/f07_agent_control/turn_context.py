"""F07 turn context assembly and inject dialogue formatting."""

from __future__ import annotations

from typing import Any, Dict, List

from agent_world.drama_demo.features.f05_story_routing.routing import (
    node_inject_ids,
)
from agent_world.drama_demo.features.f07_agent_control.config import is_f07_enabled
from agent_world.drama_demo.features.f07_agent_control.knowledge import (
    build_agent_knowledge,
)
from agent_world.drama_demo.features.f07_agent_control.llm_params import (
    resolve_llm_params,
)


def build_turn_context(session: Any, player_text: str) -> Dict[str, Any]:
    """Build IPC turn_context payload (Flask-side)."""
    phase = str(getattr(session, "phase", "Phase 1"))
    player_turn = int(getattr(session, "player_turn", 1))
    stats = getattr(session, "stats", None) or {}
    inject_ids = node_inject_ids(session)
    return {
        "enabled": True,
        "phase": phase,
        "player_turn": player_turn,
        "start_tick": int(getattr(session, "start_tick", 0) or 0),
        "place_id": str(getattr(session, "place_id", "")),
        "inject_agent_ids": list(inject_ids),
        "player_text": player_text.strip(),
        "stats": dict(stats) if isinstance(stats, dict) else {},
        "llm_params": resolve_llm_params(phase, player_turn),
    }


def format_inject_dialogue(
    session: Any,
    agent_id: int,
    player_text: str,
    turn_context: Dict[str, Any] | None = None,
) -> str:
    """Full L4+L6 inject prefix for one inject-target agent."""
    _ = turn_context
    return build_agent_knowledge(
        session,
        agent_id,
        player_text,
        channel="inject",
    )


def extract_inject_agent_ids(events: List[Dict[str, Any]]) -> List[int]:
    ids: List[int] = []
    for ev in events:
        eff = ev.get("effect") or {}
        if eff.get("type") != "dialogue_injection":
            continue
        try:
            aid = int(eff["agent_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if aid not in ids:
            ids.append(aid)
    return ids


def clear_player_memory_for_agents(agents: Any, agent_ids: List[int]) -> None:
    """A6 — scoped player_memory clear before each inject batch."""
    for aid in agent_ids:
        agent = agents.get(aid) if hasattr(agents, "get") else None
        if agent is None:
            continue
        mem = getattr(agent, "player_memory", None)
        if mem is not None and hasattr(mem, "clear"):
            mem.clear()
        if hasattr(agent, "_inject_responded"):
            agent._inject_responded = False  # noqa: SLF001
        if hasattr(agent, "_pending_rdc_out"):
            agent._pending_rdc_out = {}  # noqa: SLF001


__all__ = [
    "build_turn_context",
    "clear_player_memory_for_agents",
    "extract_inject_agent_ids",
    "format_inject_dialogue",
]
