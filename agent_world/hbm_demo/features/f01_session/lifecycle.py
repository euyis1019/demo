"""F01 Flask session lifecycle."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from agent_world.hbm_demo.features.f01_session.constants import (
    DEFAULT_PHASE,
    DEFAULT_PLACE_ID,
    DEFAULT_SIM_ID,
    SESSION_KEY,
)
from agent_world.hbm_demo.features.f01_session.models import HbmSession
from agent_world.hbm_demo.features.f01_session.paths import get_sim_dir
from agent_world.hbm_demo.features.f04_stats.deltas import initial_stats
from agent_world.hbm_demo.shared.env_status import is_runner_ready, read_env_status


def create_session(sim_dir: Path | None = None) -> HbmSession:
    sim = sim_dir or get_sim_dir()
    env = read_env_status(sim) or {}
    start_tick = int(env.get("current_tick", 0))
    return HbmSession(
        task_id=f"task_{uuid.uuid4().hex[:12]}",
        start_tick=start_tick,
        place_id=DEFAULT_PLACE_ID,
        phase=DEFAULT_PHASE,
        player_turn=1,
        stats=initial_stats(),
    )


def save_session(flask_session: Any, hbm: HbmSession, sim_id: str = DEFAULT_SIM_ID) -> None:
    store = flask_session.setdefault(SESSION_KEY, {})
    store[sim_id] = hbm.to_dict()
    flask_session.modified = True


def load_session(
    flask_session: Any,
    sim_id: str = DEFAULT_SIM_ID,
) -> Optional[HbmSession]:
    store = flask_session.get(SESSION_KEY) or {}
    raw = store.get(sim_id)
    if not raw:
        return None
    return HbmSession.from_dict(raw)


def get_or_create_session(
    flask_session: Any,
    sim_id: str = DEFAULT_SIM_ID,
    *,
    sim_dir: Path | None = None,
) -> HbmSession:
    existing = load_session(flask_session, sim_id)
    if existing is not None:
        return existing
    hbm = create_session(sim_dir)
    save_session(flask_session, hbm, sim_id)
    return hbm


def get_session_snapshot(
    flask_session: Any,
    sim_id: str = DEFAULT_SIM_ID,
    *,
    sim_dir: Path | None = None,
) -> Dict[str, Any]:
    sim = sim_dir or get_sim_dir()
    env = read_env_status(sim) or {}
    runner_ready = is_runner_ready(sim)
    hbm = load_session(flask_session, sim_id)
    if hbm is None:
        return {
            "initialized": False,
            "sim_id": sim_id,
            "runner_ready": runner_ready,
            "env_status": env,
        }
    return {
        "initialized": True,
        "sim_id": sim_id,
        "task_id": hbm.task_id,
        "start_tick": hbm.start_tick,
        "place_id": hbm.place_id,
        "phase": hbm.phase,
        "current_phase": hbm.phase,
        "player_turn": hbm.player_turn,
        "stats": dict(hbm.stats),
        "stats_update": dict(hbm.stats),
        "phase2_start_tick": hbm.phase2_start_tick,
        "runner_ready": runner_ready,
        "env_status": env,
    }
