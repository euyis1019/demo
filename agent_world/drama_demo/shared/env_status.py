"""``env_status.json`` writer — merge ``current_tick`` across IPCServer lifecycle."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

# IPCServer (MiroFish legacy) writes ``alive``; drama demo standardizes on ``running``.
_STATUS_NORMALIZE = {"alive": "running"}


def normalize_env_status(status: str) -> str:
    """Map engine IPC status strings to drama demo convention."""
    return _STATUS_NORMALIZE.get(status, status)


def write_env_status(
    sim_dir: str | Path,
    current_tick: int,
    *,
    status: str = "running",
    loop_running: Optional[bool] = None,
    loop_state: Optional[str] = None,
    last_activity_t: Optional[int] = None,
    queue_depth: Optional[int] = None,
    paused_at_tick: Optional[int] = None,
    paused_at_iso: Optional[str] = None,
    tick_interval_sec: Optional[float] = None,
) -> None:
    """Write ``{sim_dir}/env_status.json`` with ``current_tick`` preserved."""
    path = Path(sim_dir) / "env_status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    body: dict[str, Any] = {
        "status": normalize_env_status(status),
        "current_tick": int(current_tick),
        "timestamp": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    if loop_running is not None:
        body["loop_running"] = bool(loop_running)
    if loop_state is not None:
        body["loop_state"] = str(loop_state)
    if last_activity_t is not None:
        body["last_activity_t"] = int(last_activity_t)
    if queue_depth is not None:
        body["queue_depth"] = int(queue_depth)
    if paused_at_tick is not None:
        body["paused_at_tick"] = int(paused_at_tick)
    if paused_at_iso is not None:
        body["paused_at_iso"] = str(paused_at_iso)
    if tick_interval_sec is not None:
        body["tick_interval_sec"] = float(tick_interval_sec)
    # Atomic write: env_status.json is rewritten every tick (~1s) while Flask
    # reads it on every poll/turn. A plain write truncates then fills, so a
    # concurrent reader could see an empty/partial file → JSON error → spurious
    # "Runner not ready" (notably at phase transitions when concurrency spikes).
    # Write to a temp file in the same dir, then os.replace (atomic on POSIX):
    # readers always observe a complete previous-or-new file, never a partial one.
    text = json.dumps(body, ensure_ascii=False, indent=2)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), prefix=".env_status.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def read_env_status(sim_dir: str | Path) -> dict[str, Any] | None:
    """Read ``env_status.json``; return ``None`` if missing or invalid."""
    path = Path(sim_dir) / "env_status.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    if "status" in data:
        data = dict(data)
        data["status"] = normalize_env_status(str(data["status"]))
    return data


def is_runner_ready(sim_dir: str | Path) -> bool:
    """Return True when Runner is accepting IPC (``status == running``)."""
    data = read_env_status(sim_dir)
    return bool(data and data.get("status") == "running")


def patch_ipc_server_env_status(
    ipc_server: Any,
    sim_dir: str | Path,
    get_current_tick: Callable[[], int],
    *,
    get_loop_extra: Optional[Callable[[], dict[str, Any]]] = None,
) -> None:
    """Replace ``IPCServer._update_env_status`` so it keeps ``current_tick``."""

    def _merged_update(status: str) -> None:
        extra: dict[str, Any] = {}
        if get_loop_extra is not None:
            try:
                extra = dict(get_loop_extra() or {})
            except Exception:  # noqa: BLE001
                extra = {}
        write_env_status(
            sim_dir,
            get_current_tick(),
            status=normalize_env_status(status),
            loop_running=extra.get("loop_running"),
            loop_state=extra.get("loop_state"),
            last_activity_t=extra.get("last_activity_t"),
            queue_depth=extra.get("queue_depth"),
            paused_at_tick=extra.get("paused_at_tick"),
            paused_at_iso=extra.get("paused_at_iso"),
            tick_interval_sec=extra.get("tick_interval_sec"),
        )

    ipc_server._update_env_status = _merged_update  # type: ignore[method-assign]
