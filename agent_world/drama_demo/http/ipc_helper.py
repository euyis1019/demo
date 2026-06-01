"""Flask-side IPC helpers for drama demo (world loop + legacy batch)."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from agent_world.app.services.simulation_ipc import IPCResponse, SimulationIPCClient
from agent_world.drama_demo.features.f07_agent_control.config import (
    is_world_loop_enabled,
    resolve_inject_tick_count,
)
from agent_world.drama_demo.shared.errors import IpcFailedError, IpcTimeoutError
from agent_world.drama_demo.shared.settings import (
    DEFAULT_IPC_TIMEOUT,
    DEFAULT_MOVE_TIMEOUT,
    DEFAULT_RESET_TIMEOUT,
)
from agent_world.ipc.commands import CommandType


def get_ipc_client(sim_dir: str) -> SimulationIPCClient:
    """Return a file-IPC client for the given simulation directory."""
    return SimulationIPCClient(sim_dir)


def _ensure_ipc_completed(resp: IPCResponse, *, operation: str) -> IPCResponse:
    if resp.status.value == "completed":
        return resp
    raise IpcFailedError(resp.error or f"{operation} failed: {resp.status.value}")


def send_get_loop_status(
    client: SimulationIPCClient,
    *,
    timeout: float = DEFAULT_MOVE_TIMEOUT,
) -> IPCResponse:
    try:
        resp = client.send_command(CommandType.GET_LOOP_STATUS, {}, timeout=timeout)
    except TimeoutError as exc:
        raise IpcTimeoutError(str(exc)) from exc
    return _ensure_ipc_completed(resp, operation="GET_LOOP_STATUS")


def send_pause_loop(
    client: SimulationIPCClient,
    *,
    timeout: float = DEFAULT_MOVE_TIMEOUT,
) -> IPCResponse:
    try:
        resp = client.send_command(CommandType.PAUSE_LOOP, {}, timeout=timeout)
    except TimeoutError as exc:
        raise IpcTimeoutError(str(exc)) from exc
    return _ensure_ipc_completed(resp, operation="PAUSE_LOOP")


def send_resume_loop(
    client: SimulationIPCClient,
    *,
    timeout: float = DEFAULT_MOVE_TIMEOUT,
) -> IPCResponse:
    try:
        resp = client.send_command(CommandType.RESUME_LOOP, {}, timeout=timeout)
    except TimeoutError as exc:
        raise IpcTimeoutError(str(exc)) from exc
    return _ensure_ipc_completed(resp, operation="RESUME_LOOP")


def send_update_session_mirror(
    client: SimulationIPCClient,
    *,
    turn_context: Dict[str, Any],
    timeout: float = DEFAULT_MOVE_TIMEOUT,
) -> IPCResponse:
    try:
        resp = client.send_command(
            CommandType.UPDATE_SESSION_MIRROR,
            {"turn_context": turn_context},
            timeout=timeout,
        )
    except TimeoutError as exc:
        raise IpcTimeoutError(str(exc)) from exc
    return _ensure_ipc_completed(resp, operation="UPDATE_SESSION_MIRROR")


def push_session_mirror(
    client: SimulationIPCClient,
    session: Any,
    *,
    player_text: str = "",
    timeout: float = DEFAULT_MOVE_TIMEOUT,
) -> None:
    """Sync Flask session snapshot to Runner (no-op when world loop disabled)."""
    if not is_world_loop_enabled():
        return
    from agent_world.drama_demo.features.f07_agent_control.session_mirror import (
        mirror_from_session,
    )

    mirror = mirror_from_session(session, player_text=player_text)
    send_update_session_mirror(client, turn_context=mirror, timeout=timeout)


def push_turn_context_mirror(
    client: SimulationIPCClient,
    turn_context: Dict[str, Any],
    *,
    stats: Optional[Dict[str, Any]] = None,
    timeout: float = DEFAULT_MOVE_TIMEOUT,
) -> None:
    """Push the active inject batch turn_context — before Flask player_turn increment."""
    if not is_world_loop_enabled():
        return
    mirror = dict(turn_context)
    if stats is not None:
        mirror["stats"] = dict(stats)
    send_update_session_mirror(client, turn_context=mirror, timeout=timeout)


def send_enqueue_player_input(
    client: SimulationIPCClient,
    *,
    events: List[Dict[str, Any]],
    turn_context: Optional[Dict[str, Any]] = None,
    broadcast: Optional[Dict[str, Any]] = None,
    player_f2f: Optional[Dict[str, Any]] = None,
    player_rdc: Optional[Dict[str, Any]] = None,
    player_grp: Optional[Dict[str, Any]] = None,
    timeout: float = DEFAULT_IPC_TIMEOUT,
) -> IPCResponse:
    payload: Dict[str, Any] = {"events": events}
    if broadcast:
        payload["broadcast"] = broadcast
    if turn_context:
        payload["turn_context"] = turn_context
    if player_f2f:
        payload["player_f2f"] = player_f2f
    if player_rdc:
        payload["player_rdc"] = player_rdc
    if player_grp:
        payload["player_grp"] = player_grp
    try:
        resp = client.send_command(
            CommandType.ENQUEUE_PLAYER_INPUT,
            payload,
            timeout=timeout,
        )
    except TimeoutError as exc:
        raise IpcTimeoutError(str(exc)) from exc
    return _ensure_ipc_completed(resp, operation="ENQUEUE_PLAYER_INPUT")


def send_enqueue_script_event(
    client: SimulationIPCClient,
    *,
    events: List[Dict[str, Any]],
    broadcast: Optional[Dict[str, Any]] = None,
    timeout: float = DEFAULT_IPC_TIMEOUT,
) -> IPCResponse:
    payload: Dict[str, Any] = {"events": events}
    if broadcast:
        payload["broadcast"] = broadcast
    try:
        resp = client.send_command(
            CommandType.INJECT_SCRIPT_EVENT,
            payload,
            timeout=timeout,
        )
    except TimeoutError as exc:
        raise IpcTimeoutError(str(exc)) from exc
    return _ensure_ipc_completed(resp, operation="INJECT_SCRIPT_EVENT")


def wait_for_loop_window(
    client: SimulationIPCClient,
    *,
    start_tick: int,
    min_ticks: int = 8,
    timeout: float = DEFAULT_IPC_TIMEOUT,
    poll_sec: float = 0.25,
) -> Dict[str, Any]:
    """Wait until queue drained and ``current_tick >= start_tick + min_ticks``."""
    deadline = time.monotonic() + float(timeout)
    last: Dict[str, Any] = {}
    while time.monotonic() < deadline:
        resp = send_get_loop_status(client, timeout=min(30.0, timeout))
        last = dict(resp.result or {})
        tick = int(last.get("current_tick", 0))
        depth = int(last.get("queue_depth", 0))
        if tick >= int(start_tick) + int(min_ticks) and depth == 0:
            return last
        time.sleep(poll_sec)
    raise IpcTimeoutError(
        f"world loop window timeout start={start_tick} min_ticks={min_ticks} last={last}"
    )


def send_inject_batch(
    client: SimulationIPCClient,
    *,
    events: List[Dict[str, Any]],
    tick_count: int = 6,
    broadcast: Optional[Dict[str, Any]] = None,
    turn_context: Optional[Dict[str, Any]] = None,
    player_f2f: Optional[Dict[str, Any]] = None,
    timeout: float = DEFAULT_IPC_TIMEOUT,
) -> IPCResponse:
    """Legacy batch inject, or enqueue-only when world loop is enabled."""
    if is_world_loop_enabled():
        if turn_context:
            return send_enqueue_player_input(
                client,
                events=events,
                broadcast=broadcast,
                turn_context=turn_context,
                player_f2f=player_f2f,
                timeout=timeout,
            )
        return send_enqueue_script_event(
            client,
            events=events,
            broadcast=broadcast,
            timeout=timeout,
        )

    payload: Dict[str, Any] = {"events": events, "tick_count": tick_count}
    if broadcast:
        payload["broadcast"] = broadcast
    if turn_context:
        payload["turn_context"] = turn_context
    if player_f2f:
        payload["player_f2f"] = player_f2f
    try:
        resp = client.send_command(
            CommandType.INJECT_SCRIPT_EVENT,
            payload,
            timeout=timeout,
        )
    except TimeoutError as exc:
        raise IpcTimeoutError(str(exc)) from exc
    return _ensure_ipc_completed(resp, operation="INJECT_SCRIPT_EVENT")


def resolve_loop_min_ticks(phase: str, tick_count: int) -> int:
    return resolve_inject_tick_count(phase, tick_count)


def send_move_agent(
    client: SimulationIPCClient,
    *,
    agent_id: int,
    place_id: str,
    timeout: float = DEFAULT_MOVE_TIMEOUT,
) -> IPCResponse:
    """Force-move an agent via IPC MOVE_AGENT."""
    try:
        resp = client.send_command(
            CommandType.MOVE_AGENT,
            {"agent_id": int(agent_id), "place_id": str(place_id)},
            timeout=timeout,
        )
    except TimeoutError as exc:
        raise IpcTimeoutError(str(exc)) from exc
    return _ensure_ipc_completed(resp, operation="MOVE_AGENT")


def send_reset_world(
    client: SimulationIPCClient,
    *,
    timeout: float = DEFAULT_RESET_TIMEOUT,
) -> IPCResponse:
    """Reset Runner world state to scenario initial (messages, tick, locations)."""
    try:
        resp = client.send_command(CommandType.RESET_WORLD, {}, timeout=timeout)
    except TimeoutError as exc:
        raise IpcTimeoutError(str(exc)) from exc
    return _ensure_ipc_completed(resp, operation="RESET_WORLD")


def fetch_list_places(client: SimulationIPCClient) -> Dict[str, Any]:
    """Return Runner place list and agent locations (IPC LIST_PLACES)."""
    resp = client.send_command(CommandType.LIST_PLACES, {}, timeout=DEFAULT_MOVE_TIMEOUT)
    resp = _ensure_ipc_completed(resp, operation="LIST_PLACES")
    return dict(resp.result or {})
