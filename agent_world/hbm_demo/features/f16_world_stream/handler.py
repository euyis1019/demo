"""F16 WebSocket handler — push session world delta (dev_logs/31 §14.4)."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict

from agent_world.hbm_demo import game_service as gs
from agent_world.hbm_demo.features.f16_world_stream.config import (
    is_world_stream_enabled,
    world_stream_poll_interval,
)
from agent_world.hbm_demo.features.f14_world_delta.handler import get_world_delta
from agent_world.hbm_demo.shared.env_status import is_runner_ready

log = logging.getLogger("agent_world.hbm_demo.f16")


def _delta_has_activity(delta: Dict[str, Any]) -> bool:
    room_f2f = delta.get("room_f2f") or {}
    if any(len(v or []) for v in room_f2f.values()):
        return True
    if delta.get("public_messages") or delta.get("observer_messages"):
        return True
    if delta.get("group_messages"):
        return True
    agent_messages = delta.get("agent_messages") or {}
    for payload in agent_messages.values():
        if (payload.get("rdc") or payload.get("grp")):
            return True
    if delta.get("location_changes") or delta.get("world_events"):
        return True
    return False


def _should_push(delta: Dict[str, Any], since_tick: int) -> bool:
    through = int(delta.get("through_tick", since_tick))
    if through > int(since_tick):
        return True
    if _delta_has_activity(delta):
        return True
    if delta.get("game_over"):
        return True
    return False


def register_world_stream_routes(sock: Any, *, url_prefix: str) -> None:
    """Register ``WS …/world-stream`` on the Flask-Sock instance."""

    @sock.route(f"{url_prefix}/simulations/<sim_id>/world-stream")
    def world_stream(ws: Any, sim_id: str) -> None:
        from flask import session

        if not is_world_stream_enabled():
            ws.send(json.dumps({"success": False, "error": "world_stream disabled"}))
            return

        if sim_id != gs.DEFAULT_SIM_ID:
            ws.send(json.dumps({"success": False, "error": f"unknown simulation_id: {sim_id}"}))
            return

        since_tick = 0
        try:
            initial = ws.receive(timeout=2)
            if initial:
                payload = json.loads(initial)
                if isinstance(payload, dict):
                    since_tick = max(0, int(payload.get("since_tick", 0)))
        except Exception:  # noqa: BLE001
            pass

        interval = world_stream_poll_interval()
        log.debug("world-stream connected sim=%s since_tick=%s", sim_id, since_tick)

        while True:
            if not is_runner_ready(gs.get_sim_dir()):
                ws.send(
                    json.dumps(
                        {
                            "success": False,
                            "error": "Runner not ready",
                        }
                    )
                )
                time.sleep(1.0)
                continue

            try:
                delta = get_world_delta(
                    session,
                    sim_id=sim_id,
                    since_tick=since_tick,
                )
            except Exception as exc:  # noqa: BLE001
                ws.send(json.dumps({"success": False, "error": str(exc)}))
                time.sleep(interval)
                continue

            if _should_push(delta, since_tick):
                ws.send(json.dumps({"success": True, "data": delta}, ensure_ascii=False))
                since_tick = int(delta.get("through_tick", since_tick))

            if delta.get("game_over"):
                return

            time.sleep(interval)


__all__ = ["register_world_stream_routes"]
