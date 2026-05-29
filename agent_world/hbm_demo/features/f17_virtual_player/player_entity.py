"""F17 — agent 0 (virtual player) registration helpers and Phase-driven MOVE sync."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml

from agent_world.hbm_demo.features.f17_virtual_player.config import (
    is_f08_enabled,
    player_agent_id,
)

log = logging.getLogger("agent_world.hbm_demo.f17.player_entity")

from agent_world.hbm_demo.shared.prompt_paths import virtual_player_phase_places_path

_PHASE_PLACES_PATH = virtual_player_phase_places_path()

PLAYER_AGENT_ID = 0


@lru_cache(maxsize=1)
def _phase_places_data() -> tuple[Dict[str, str], str]:
    if not _PHASE_PLACES_PATH.is_file():
        return (
            {
                "Phase 1": "nvidia_reception",
                "Phase 2": "jensen_private_room",
                "Phase 3": "negotiation_room",
                "Phase 4": "negotiation_room",
            },
            "nvidia_reception",
        )
    with _PHASE_PLACES_PATH.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    phases = dict(data.get("phases") or {})
    default_place = str(data.get("default_place") or "nvidia_reception")
    return phases, default_place


def phase_player_places() -> Dict[str, str]:
    return dict(_phase_places_data()[0])


def default_player_place() -> str:
    return str(_phase_places_data()[1])


def target_place_for_phase(phase: str) -> str:
    places = phase_player_places()
    return str(places.get(str(phase), default_player_place()))


def is_virtual_player_agent(agent_id: int) -> bool:
    return is_f08_enabled() and int(agent_id) == int(player_agent_id())


def sync_player_place_on_routing(
    session: Any,
    *,
    ipc_client: Any,
    new_phase: str,
    node: str,
    ipc_timeout: float,
) -> Dict[str, Any]:
    """Update session phase/place_id and IPC MOVE agent 0 when place changes."""
    from agent_world.hbm_demo.http.ipc_helper import send_move_agent

    if not is_f08_enabled():
        session.phase = str(new_phase)
        target = target_place_for_phase(new_phase)
        if node in ("A", "B"):
            session.place_id = target
        return {"node": node, "moved": False, "skipped": "f08_disabled"}

    target = target_place_for_phase(new_phase)
    node_key = str(node).upper()
    moved = False

    if node_key in ("A", "B"):
        send_move_agent(
            ipc_client,
            agent_id=int(player_agent_id()),
            place_id=target,
            timeout=ipc_timeout,
        )
        session.phase = str(new_phase)
        session.place_id = target
        moved = True
        log.info(
            "F08 routing node %s: player agent %s → %s phase=%s",
            node_key,
            player_agent_id(),
            target,
            new_phase,
        )
    elif node_key == "C":
        session.phase = str(new_phase)
        log.info(
            "F08 routing node C: player stays @ %s phase=%s",
            session.place_id,
            new_phase,
        )
    else:
        session.phase = str(new_phase)
        session.place_id = target

    return {
        "node": node_key,
        "moved": moved,
        "place_id": str(getattr(session, "place_id", target)),
        "phase": str(getattr(session, "phase", new_phase)),
    }


__all__ = [
    "PLAYER_AGENT_ID",
    "default_player_place",
    "is_virtual_player_agent",
    "phase_player_places",
    "sync_player_place_on_routing",
    "target_place_for_phase",
]
