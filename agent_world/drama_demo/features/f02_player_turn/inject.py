"""F02 inject payload assembly (delegates to F05 routing)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from agent_world.drama_demo.features.f01_session.models import DramaSession
from agent_world.drama_demo.features.f05_story_routing import routing


def build_inject_events(
    session: DramaSession,
    player_text: str,
    *,
    task_id: str,
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    return routing.build_inject_payload(session, player_text, task_id=task_id)


def check_turn4_bad_end(
    session: DramaSession,
    db: Any = None,
    current_tick: Optional[int] = None,
) -> bool:
    """Legacy 数值结局门——当前一律交给 RoutingWatcher 的 LLM 导演按对话判结局，此门不触发。"""
    return False


BAD_END_PUBLIC_MESSAGES = [
    {
        "sender": "接待前台",
        "content": "保安，请这位先生离开。",
        "type": "F2F",
    }
]
