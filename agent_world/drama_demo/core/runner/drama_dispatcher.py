"""drama demo ActionDispatcher — NPC 自主移动放行，言行一致（导演引导走 f05 另一条路）。"""

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
    """NPC 自主移动（``request_move``）始终放行——agent 按自己的角色意图决定要走就**真的走**（言行一致）。

    这与「导演引导」是两条不同的路：导演那条（f05 ``_gather_scene``）由引擎按 bert 把 NPC 搬到
    反应地点、曾导致 NPC 来回乱晃，仍按 ``npc_free_move`` 单独门控关掉；而 agent 自己发起的
    ``request_move`` 不再被引擎吞掉，落到通用 dispatcher 真正生效。移动克制由 drama_agent prompt
    「非必要不挪窝 / 言行一致」+ meta.acting_guide 把关，不靠引擎硬性禁止。"""

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

        return await super().dispatch(agent_id, action_type, t, **kwargs)


__all__ = ["DramaActionDispatcher", "_DRAMA_MOVE_REASON"]
