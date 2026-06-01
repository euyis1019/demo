"""F07 inject-batch hooks — notifications + session view from turn_context."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

from agent_world.drama_demo.features.f07_agent_control.config import is_f07_enabled
from agent_world.drama_demo.features.f07_agent_control.knowledge import (
    build_notification_snippet,
)
from agent_world.drama_demo.features.f07_agent_control.pick_active import (
    primary_active_ids,
)


def session_view_from_turn_context(turn_context: Dict[str, Any]) -> Any:
    stats = turn_context.get("stats") or {}
    return SimpleNamespace(
        phase=str(turn_context.get("phase", "")),
        player_turn=int(turn_context.get("player_turn", 1)),
        place_id=str(turn_context.get("place_id", "")),
        stats=dict(stats),
    )


def notify_non_inject_active_agents(
    script_engine: Any,
    turn_context: Dict[str, Any],
    inject_ids: List[int],
) -> None:
    """§19.7 — L3 primary agents (non inject) receive shared world snippet."""
    if not is_f07_enabled() or not turn_context:
        return
    session = session_view_from_turn_context(turn_context)
    inject_set = {int(x) for x in inject_ids}
    for aid in primary_active_ids(turn_context):
        if aid in inject_set:
            continue
        snippet = build_notification_snippet(session, aid)
        if snippet and hasattr(script_engine, "notify_agent"):
            script_engine.notify_agent(aid, snippet)
