"""Flask session → Runner turn_context mirror (dev_logs/31 §17.2)."""

from __future__ import annotations

from typing import Any, Dict

from agent_world.hbm_demo.features.f01_session.constants import (
    DEFAULT_PHASE,
    DEFAULT_PLACE_ID,
    INITIAL_STATS,
)
from agent_world.hbm_demo.features.f07_agent_control.llm_params import (
    resolve_llm_params,
)
from agent_world.hbm_demo.features.f07_agent_control.turn_context import (
    build_turn_context,
)


def bootstrap_mirror() -> Dict[str, Any]:
    """Startup default when Flask has not pushed a mirror yet."""
    from agent_world.hbm_demo.features.f05_story_routing.routing import (
        inject_agent_ids_for_phase,
    )

    phase = DEFAULT_PHASE
    player_turn = 1
    return {
        "enabled": True,
        "phase": phase,
        "player_turn": player_turn,
        "start_tick": 0,
        "place_id": DEFAULT_PLACE_ID,
        "stats": dict(INITIAL_STATS),
        "inject_agent_ids": list(inject_agent_ids_for_phase(phase)),
        "player_text": "",
        "llm_params": resolve_llm_params(phase, player_turn),
        "player_inject_tick": None,
    }


def mirror_from_session(session: Any, *, player_text: str = "") -> Dict[str, Any]:
    """Build IPC mirror payload from ``HbmSession`` or session-like dict."""
    ctx = build_turn_context(session, player_text)
    if isinstance(session, dict):
        inject_tick = session.get("player_inject_tick")
    else:
        inject_tick = getattr(session, "player_inject_tick", None)
    if inject_tick is not None:
        ctx["player_inject_tick"] = int(inject_tick)
    else:
        ctx["player_inject_tick"] = None
    return ctx


def merge_mirror_update(current: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """Apply partial mirror update from IPC payload."""
    out = dict(current)
    for key in (
        "phase",
        "player_turn",
        "start_tick",
        "place_id",
        "stats",
        "inject_agent_ids",
        "player_text",
        "llm_params",
        "player_inject_tick",
        "phase2_start_tick",
        "enabled",
    ):
        if key in patch and patch[key] is not None:
            out[key] = patch[key]
    if "stats" in patch and isinstance(patch["stats"], dict):
        out["stats"] = dict(patch["stats"])
    if "inject_agent_ids" in patch:
        out["inject_agent_ids"] = [int(x) for x in (patch["inject_agent_ids"] or [])]
    phase = str(out.get("phase", DEFAULT_PHASE))
    player_turn = int(out.get("player_turn", 1))
    if "llm_params" not in patch or not patch.get("llm_params"):
        out["llm_params"] = resolve_llm_params(phase, player_turn)
    return out


def mirror_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Build mirror from explicit IPC ``UPDATE_SESSION_MIRROR`` payload."""
    base = bootstrap_mirror()
    if payload.get("turn_context"):
        return merge_mirror_update(base, dict(payload["turn_context"]))
    return merge_mirror_update(base, payload)


__all__ = [
    "bootstrap_mirror",
    "merge_mirror_update",
    "mirror_from_payload",
    "mirror_from_session",
]
