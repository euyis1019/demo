"""F08 HTTP transport layer (Flask Blueprint, IPC client, health).

``routes`` is not imported here to avoid a circular import:
``ipc_helper`` → ``http`` package init → ``routes`` → ``game_service`` → ``f01_session.reset``.
Import ``drama_bp`` from ``agent_world.drama_demo.http.routes`` or the root ``routes`` shim.
"""

from agent_world.drama_demo.http.health import check_stack_health
from agent_world.drama_demo.http.http_errors import service_error_payload
from agent_world.drama_demo.http.ipc_helper import (
    get_ipc_client,
    send_inject_batch,
    send_move_agent,
    send_reset_world,
)

__all__ = [
    "check_stack_health",
    "service_error_payload",
    "get_ipc_client",
    "send_inject_batch",
    "send_move_agent",
    "send_reset_world",
]
