"""F11 task/session runtime persistence for async inject.

Flask default sessions are signed cookies; background threads cannot update
the client cookie after the early player-turn response.  We mirror task +
session updates under ``{sim_dir}/async_state/runtime.json`` and merge on
each HTTP handler entry (see ``sync_runtime_state``).
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from agent_world.hbm_demo.features.f01_session.constants import (
    DEFAULT_SIM_ID,
    SESSION_KEY,
    TASKS_KEY,
)

log = logging.getLogger("agent_world.hbm_demo.f11")

_LOCKS: Dict[str, threading.Lock] = {}


def _lock_for(sim_dir: Path) -> threading.Lock:
    key = str(sim_dir.resolve())
    if key not in _LOCKS:
        _LOCKS[key] = threading.Lock()
    return _LOCKS[key]


def async_state_path(sim_dir: Path) -> Path:
    return sim_dir / "async_state" / "runtime.json"


def clear_async_state(sim_dir: Path) -> None:
    path = async_state_path(sim_dir)
    if path.exists():
        path.unlink()


def _read_runtime(sim_dir: Path) -> Dict[str, Any]:
    path = async_state_path(sim_dir)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("failed to read async runtime %s: %s", path, exc)
        return {}


def _write_runtime(sim_dir: Path, payload: Dict[str, Any]) -> None:
    path = async_state_path(sim_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def sync_runtime_state(
    flask_session: Any,
    sim_id: str = DEFAULT_SIM_ID,
    *,
    sim_dir: Path,
) -> None:
    """Merge disk runtime overlay into the Flask cookie session."""
    runtime = _read_runtime(sim_dir)
    if not runtime:
        return

    session_overlay = runtime.get("session")
    if session_overlay:
        store = flask_session.setdefault(SESSION_KEY, {})
        store[sim_id] = session_overlay

    tasks_overlay = runtime.get("tasks") or {}
    if tasks_overlay:
        task_store = flask_session.setdefault(TASKS_KEY, {})
        sim_tasks = task_store.setdefault(sim_id, {})
        for task_id, task_data in tasks_overlay.items():
            if task_id == "__latest__":
                continue
            sim_tasks[task_id] = task_data
        latest = runtime.get("latest_task_id")
        if latest:
            sim_tasks["__latest__"] = latest

    flask_session.modified = True


def save_task_runtime(
    sim_dir: Path,
    task_dict: Dict[str, Any],
    *,
    session_dict: Optional[Dict[str, Any]] = None,
) -> None:
    """Persist task (and optional session) updates from the background thread."""
    task_id = str(task_dict["task_id"])
    with _lock_for(sim_dir):
        runtime = _read_runtime(sim_dir)
        tasks = dict(runtime.get("tasks") or {})
        tasks[task_id] = task_dict
        runtime["tasks"] = tasks
        runtime["latest_task_id"] = task_id
        if session_dict is not None:
            runtime["session"] = session_dict
        _write_runtime(sim_dir, runtime)


def load_task_resolved(
    flask_session: Any,
    task_id: str,
    sim_id: str = DEFAULT_SIM_ID,
    *,
    sim_dir: Path,
):
    """Load task from Flask session after merging any disk overlay."""
    from agent_world.hbm_demo.features.f02_player_turn.task import PendingTask

    sync_runtime_state(flask_session, sim_id, sim_dir=sim_dir)
    store = flask_session.get(TASKS_KEY) or {}
    raw = (store.get(sim_id) or {}).get(task_id)
    if not raw:
        return None
    return PendingTask.from_dict(raw)
