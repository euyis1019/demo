"""Flask-side IPC helpers for HBM demo (batch inject / move)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent_world.app.services.simulation_ipc import IPCResponse, SimulationIPCClient
from agent_world.hbm_demo.shared.errors import IpcFailedError, IpcTimeoutError
from agent_world.hbm_demo.shared.settings import (
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


def send_inject_batch(
    client: SimulationIPCClient,
    *,
    events: List[Dict[str, Any]],
    tick_count: int = 6,
    broadcast: Optional[Dict[str, Any]] = None,
    timeout: float = DEFAULT_IPC_TIMEOUT,
) -> IPCResponse:
    """Send batch script inject with optional broadcast and tick_count."""
    payload: Dict[str, Any] = {"events": events, "tick_count": tick_count}
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
