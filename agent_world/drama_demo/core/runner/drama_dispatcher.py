"""HBM demo ActionDispatcher — agent-initiated MOVE is IPC-only (Flask routing)."""

from __future__ import annotations

import logging
from typing import Any, Dict

from agent_world.world.dispatcher import ActionDispatcher

try:
    from oasis.social_platform.typing import ActionType  # type: ignore
except Exception:  # noqa: BLE001
    from agent_world.world.dispatcher import ActionType  # type: ignore[assignment]

log = logging.getLogger("agent_world.drama_demo.dispatcher")

_DRAMA_MOVE_REASON = "drama_move_ipc_only"


class DramaActionDispatcher(ActionDispatcher):
    """Suppress agent ``request_move`` by default (location via Flask IPC);
    ``DRAMA_FREE_MOVE=1`` lets request_move through to the generic dispatcher (旋钮2)."""

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

        # 旋钮2：默认抑制 agent 自主移动（旧版脚本搬人）；DRAMA_FREE_MOVE=1 时放开，
        # request_move 落到通用 dispatcher 真正生效（移动引导见 drama_agent prompt「非必要不移动」）。
        from agent_world.drama_demo.shared.story_pack.scenario_adapter import (
            is_free_move_enabled,
        )

        move_type = getattr(ActionType, "REQUEST_MOVE", "request_move")
        if (action_type == move_type or action_type == "request_move") and not is_free_move_enabled():
            place_id = kwargs.get("place_id") or kwargs.get("target")
            log.info(
                "HBM dispatcher: ignore agent request_move agent=%s place=%s t=%s",
                agent_id,
                place_id,
                t,
            )
            return {
                "success": False,
                "reason": _DRAMA_MOVE_REASON,
                "noop": True,
                "place_id": place_id,
            }

        return await super().dispatch(agent_id, action_type, t, **kwargs)


__all__ = ["DramaActionDispatcher", "_DRAMA_MOVE_REASON"]
