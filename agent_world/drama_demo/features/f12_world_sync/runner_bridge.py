"""F12 Runner IPC bridge — optional location calibration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger("agent_world.drama_demo.f12")


def fetch_runner_locations(sim_dir: Any) -> Optional[Dict[str, Dict[str, Any]]]:
    """Return agent locations from Runner LIST_PLACES when IPC is available."""
    if sim_dir is None:
        return None
    try:
        from agent_world.drama_demo.http.ipc_helper import (
            fetch_list_places,
            get_ipc_client,
        )
        from agent_world.drama_demo.shared.env_status import is_runner_ready

        sim_path = Path(sim_dir)
        if not is_runner_ready(sim_path):
            return None
        payload = fetch_list_places(get_ipc_client(str(sim_path)))
        raw = payload.get("agent_locations") or {}
        out: Dict[str, Dict[str, Any]] = {}
        for key, place_id in raw.items():
            out[str(int(key))] = {
                "place_id": str(place_id),
                "arrived_at": 0,
            }
        return out
    except Exception as exc:  # noqa: BLE001
        log.debug("fetch_runner_locations skipped: %s", exc)
        return None
