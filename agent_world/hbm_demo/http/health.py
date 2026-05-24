"""Stack health checks for HBM demo (Phase 6)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from agent_world.hbm_demo.features.f01_session.paths import get_sim_dir
from agent_world.hbm_demo.features.f06_read_model.world_db import make_readonly_db
from agent_world.hbm_demo.shared.env_status import is_runner_ready, read_env_status
from agent_world.hbm_demo.shared.errors import DatabaseReadError


def check_stack_health(sim_dir: Path | None = None) -> Dict[str, Any]:
    """Return Runner + world.db readiness for frontend / ops probes."""
    sim = sim_dir or get_sim_dir()
    env = read_env_status(sim)
    runner_ready = is_runner_ready(sim)

    world_db_readable = False
    db_error: Optional[str] = None
    if runner_ready:
        try:
            db = make_readonly_db(sim)
            db.agents_at("nvidia_reception")
            world_db_readable = True
        except DatabaseReadError as exc:
            db_error = str(exc)

    ready = runner_ready and world_db_readable
    return {
        "sim_dir": str(sim),
        "runner_ready": runner_ready,
        "world_db_readable": world_db_readable,
        "ready": ready,
        "env_status": env,
        "db_error": db_error,
    }
