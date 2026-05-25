"""HBM demo ActionDispatcher — agent-initiated MOVE is IPC-only (Flask routing)."""

from __future__ import annotations

import logging
from typing import Any, Dict

from agent_world.world.dispatcher import ActionDispatcher

try:
    from oasis.social_platform.typing import ActionType  # type: ignore
except Exception:  # noqa: BLE001
    from agent_world.world.dispatcher import ActionType  # type: ignore[assignment]

log = logging.getLogger("agent_world.hbm_demo.dispatcher")

_HBM_MOVE_REASON = "hbm_move_ipc_only"


class HbmActionDispatcher(ActionDispatcher):
    """Silently ignore agent ``request_move``; location changes use Flask IPC."""

    async def dispatch(
        self,
        agent_id: int,
        action_type: Any,
        t: int,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if isinstance(action_type, str):
            try:
                action_type = ActionType(action_type)
            except ValueError:
                pass

        move_type = getattr(ActionType, "REQUEST_MOVE", "request_move")
        if action_type == move_type or action_type == "request_move":
            place_id = kwargs.get("place_id") or kwargs.get("target")
            log.info(
                "HBM dispatcher: ignore agent request_move agent=%s place=%s t=%s",
                agent_id,
                place_id,
                t,
            )
            return {
                "success": False,
                "reason": _HBM_MOVE_REASON,
                "noop": True,
                "place_id": place_id,
            }

        return await super().dispatch(agent_id, action_type, t, **kwargs)


__all__ = ["HbmActionDispatcher", "_HBM_MOVE_REASON"]
