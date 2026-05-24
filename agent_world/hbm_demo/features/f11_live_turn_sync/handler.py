"""F11 orchestration entry — start async inject from F02."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_world.hbm_demo.features.f01_session.models import HbmSession
from agent_world.hbm_demo.features.f11_live_turn_sync.async_inject import (
    run_background_inject,
)


def start_background_turn(
    *,
    sim_dir: Path,
    sim_id: str,
    task_id: str,
    hbm: HbmSession,
    events: List[Dict[str, Any]],
    broadcast: Optional[Dict[str, Any]],
    start_tick: int,
    task_place_id: str,
    task_phase: str,
    task_player_turn: int,
    tick_count: int,
    ipc_timeout: float,
) -> None:
    """Spawn a daemon thread to run inject + routing after player-turn returns."""
    session_copy = HbmSession.from_dict(hbm.to_dict())
    thread = threading.Thread(
        target=run_background_inject,
        kwargs={
            "sim_dir": sim_dir,
            "sim_id": sim_id,
            "task_id": task_id,
            "hbm": session_copy,
            "events": events,
            "broadcast": broadcast,
            "start_tick": start_tick,
            "task_place_id": task_place_id,
            "task_phase": task_phase,
            "task_player_turn": task_player_turn,
            "tick_count": tick_count,
            "ipc_timeout": ipc_timeout,
        },
        name=f"f11-inject-{task_id}",
        daemon=True,
    )
    thread.start()
