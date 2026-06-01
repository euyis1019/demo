"""F16 WebSocket registration for HBM demo (dev_logs/38 Phase R2)."""

from __future__ import annotations

import logging

from flask import Flask

log = logging.getLogger(__name__)


def register_drama_world_stream(app: Flask) -> None:
    """Register F16 world-stream WebSocket routes when enabled in turn_control."""
    from agent_world.drama_demo.features.f16_world_stream.config import (
        is_world_stream_enabled,
    )

    if not is_world_stream_enabled():
        return

    from flask_sock import Sock

    from agent_world.drama_demo.features.f16_world_stream import (
        register_world_stream_routes,
    )

    sock = Sock()
    sock.init_app(app)
    register_world_stream_routes(sock, url_prefix="/api/drama")
