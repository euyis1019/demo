"""F11 orchestration entry — start async turn pipeline from F02."""

from __future__ import annotations

import threading
from pathlib import Path

from agent_world.drama_demo.features.f01_session.models import DramaSession
from agent_world.drama_demo.features.f11_live_turn_sync.async_inject import run_background_turn


def start_background_turn(
    *,
    sim_dir: Path,
    sim_id: str,
    task_id: str,
    hbm: DramaSession,
    player_text: str,
    start_tick: int,
    task_place_id: str,
    task_player_turn: int,
    tick_count: int,
    ipc_timeout: float,
) -> None:
    """Spawn a daemon thread: F04 score → inject → routing."""
    session_copy = DramaSession.from_dict(hbm.to_dict())
    thread = threading.Thread(
        target=run_background_turn,
        kwargs={
            "sim_dir": sim_dir,
            "sim_id": sim_id,
            "task_id": task_id,
            "hbm": session_copy,
            "player_text": player_text,
            "start_tick": start_tick,
            "task_place_id": task_place_id,
            "task_player_turn": task_player_turn,
            "tick_count": tick_count,
            "ipc_timeout": ipc_timeout,
        },
        name=f"f11-turn-{task_id}",
        daemon=True,
    )
    thread.start()
