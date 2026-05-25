"""F02 inject payload assembly (delegates to F05 routing)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from agent_world.hbm_demo.features.f01_session.models import HbmSession
from agent_world.hbm_demo.features.f05_story_routing import routing


def build_inject_events(
    session: HbmSession,
    player_text: str,
    *,
    task_id: str,
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    return routing.build_inject_payload(session, player_text, task_id=task_id)


def check_turn4_bad_end(
    session: HbmSession,
    db: Any = None,
    current_tick: Optional[int] = None,
) -> bool:
    """Legacy Stats Turn4 gate; agent_driven defers to RoutingWatcher."""
    from agent_world.hbm_demo.features.f05_story_routing.routing_config import (
        is_agent_driven,
    )

    if is_agent_driven():
        return False
    return (
        session.player_turn == 4
        and session.stats["vision"] + session.stats["execution"] < 15
    )


BAD_END_PUBLIC_MESSAGES = [
    {
        "sender": "接待前台",
        "content": "保安，请这位先生离开。",
        "type": "F2F",
    }
]
