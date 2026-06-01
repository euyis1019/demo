"""F01 full demo reset (Flask session + Runner world)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from agent_world.drama_demo.features.f01_session.constants import DEFAULT_SIM_ID
from agent_world.drama_demo.features.f01_session.lifecycle import create_session, save_session
from agent_world.drama_demo.features.f01_session.logging import log_turn_event
from agent_world.drama_demo.features.f01_session.paths import get_sim_dir
from agent_world.drama_demo.features.f11_live_turn_sync.task_state import clear_async_state
from agent_world.drama_demo.shared.env_status import is_runner_ready, read_env_status
from agent_world.drama_demo.shared.errors import RunnerNotReadyError


def reset_demo(
    flask_session: Any,
    *,
    sim_id: str = DEFAULT_SIM_ID,
    sim_dir: Path | None = None,
) -> Dict[str, Any]:
    sim = sim_dir or get_sim_dir()
    if not is_runner_ready(sim):
        raise RunnerNotReadyError(f"runner not ready: {sim}")

    from agent_world.drama_demo.http.ipc_helper import (
        get_ipc_client,
        push_session_mirror,
        send_reset_world,
    )

    client = get_ipc_client(str(sim))
    send_reset_world(client)

    clear_async_state(sim)
    flask_session.clear()
    hbm = create_session(sim)
    save_session(flask_session, hbm, sim_id)
    push_session_mirror(client, hbm)
    env = read_env_status(sim) or {}

    log_turn_event(
        event="demo_reset",
        task_id=hbm.task_id,
        phase=hbm.phase,
        player_turn=hbm.player_turn,
        start_tick=hbm.start_tick,
        end_tick=int(env.get("current_tick", 0)),
    )

    return {
        "task_id": hbm.task_id,
        "start_tick": hbm.start_tick,
        "place_id": hbm.place_id,
        "phase": hbm.phase,
        "player_turn": hbm.player_turn,
        "stats": dict(hbm.stats),
        "env_status": env,
    }
