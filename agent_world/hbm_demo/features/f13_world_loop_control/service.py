"""F13 — world loop pause/resume control (dev_logs/31 §8.3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from agent_world.hbm_demo.features.f07_agent_control.config import (
    is_manual_pause_allowed,
    is_world_loop_enabled,
    world_loop_tick_interval,
)
from agent_world.hbm_demo.http.ipc_helper import (
    get_ipc_client,
    send_get_loop_status,
    send_pause_loop,
    send_resume_loop,
)
from agent_world.hbm_demo.shared.env_status import is_runner_ready, read_env_status
from agent_world.hbm_demo.shared.errors import RunnerNotReadyError, WorldLoopDisabledError


def _require_runner(sim: Path) -> None:
    if not is_runner_ready(sim):
        raise RunnerNotReadyError(
            "Runner not ready: start run_hbm first and wait for env_status.status=running"
        )


def _require_world_loop() -> None:
    if not is_world_loop_enabled():
        raise WorldLoopDisabledError("world loop is disabled in turn_control.yaml")


def _format_status(raw: Dict[str, Any], *, env: Dict[str, Any] | None = None) -> Dict[str, Any]:
    env = env or {}
    tick = int(raw.get("current_tick", raw.get("world_t", env.get("current_tick", 0))))
    loop_state = str(raw.get("loop_state") or env.get("loop_state") or "unknown")
    return {
        "loop_state": loop_state,
        "loop_running": bool(raw.get("loop_running", loop_state == "running")),
        "current_tick": tick,
        "world_t": int(raw.get("world_t", tick)),
        "tick_interval_sec": float(
            raw.get("tick_interval_sec", env.get("tick_interval_sec", world_loop_tick_interval()))
        ),
        "paused_at_tick": raw.get("paused_at_tick", env.get("paused_at_tick")),
        "paused_at_iso": raw.get("paused_at_iso", env.get("paused_at_iso")),
        "queue_depth": int(raw.get("queue_depth", env.get("queue_depth", 0))),
        "last_activity_t": raw.get("last_activity_t", env.get("last_activity_t")),
    }


def get_world_loop_status(*, sim_dir: Path | None = None) -> Dict[str, Any]:
    """Return Runner loop status via IPC (falls back to env_status when loop disabled)."""
    from agent_world.hbm_demo.features.f01_session.paths import get_sim_dir

    sim = sim_dir or get_sim_dir()
    _require_runner(sim)
    env = read_env_status(sim) or {}

    if not is_world_loop_enabled():
        return _format_status(
            {"loop_state": "disabled", "loop_running": False, "current_tick": env.get("current_tick", 0)},
            env=env,
        )

    client = get_ipc_client(str(sim))
    resp = send_get_loop_status(client)
    return _format_status(dict(resp.result or {}), env=env)


def pause_world_loop(*, sim_dir: Path | None = None) -> Dict[str, Any]:
    """Pause resident world tick loop (idempotent)."""
    from agent_world.hbm_demo.features.f01_session.paths import get_sim_dir

    sim = sim_dir or get_sim_dir()
    _require_runner(sim)
    _require_world_loop()
    if not is_manual_pause_allowed():
        raise WorldLoopDisabledError("manual pause is disabled in turn_control.yaml")

    client = get_ipc_client(str(sim))
    resp = send_pause_loop(client)
    result = dict(resp.result or {})
    status = _format_status(result, env=read_env_status(sim) or {})
    status["already_paused"] = bool(result.get("already_paused"))
    return status


def resume_world_loop(*, sim_dir: Path | None = None) -> Dict[str, Any]:
    """Resume resident world tick loop (idempotent)."""
    from agent_world.hbm_demo.features.f01_session.paths import get_sim_dir

    sim = sim_dir or get_sim_dir()
    _require_runner(sim)
    _require_world_loop()

    client = get_ipc_client(str(sim))
    resp = send_resume_loop(client)
    result = dict(resp.result or {})
    status = _format_status(result, env=read_env_status(sim) or {})
    status["already_running"] = bool(result.get("already_running"))
    return status


def resume_if_paused(*, sim_dir: Path | None = None) -> Dict[str, Any] | None:
    """Auto-unpause on a fresh session: if the resident loop is enabled and
    currently paused, resume it. Returns refreshed env_status when a resume
    happened, else None (no-op). Encapsulates the loop policy so L3
    (session/start) stays a thin route.
    """
    from agent_world.hbm_demo.features.f01_session.paths import get_sim_dir

    sim = sim_dir or get_sim_dir()
    if not is_world_loop_enabled():
        return None
    env = read_env_status(sim) or {}
    if env.get("loop_state") != "paused":
        return None
    try:
        resume_world_loop(sim_dir=sim)
    except Exception:  # noqa: BLE001
        return None
    return read_env_status(sim) or env


__all__ = [
    "get_world_loop_status",
    "pause_world_loop",
    "resume_world_loop",
    "resume_if_paused",
]
