"""激活调度器：同地点 NPC 每拍激活 + 异地 NPC 低频心跳（方案 §4.3 / D5）。

引擎契约（world/step.py::_pick_active）：
* scheduler 非 None 且 ``pick_active`` 返回**非 None** → 直接用该列表，
  跳过 per-agent ``activity_level`` 门控（二者互斥，本项目只用 scheduler）。
* 返回 ``[]`` 合法（本拍 0 个 agent 决策）。

⚠ 红线级注意（审计 SEED-5）：``step.py:233`` 对 agent_id=0 有 ``or`` 真值
陷阱，仅在 scheduler 缺席的默认路径触发——所以本调度器**永远返回非 None
列表**，且玩家 id 恒在列表里（玩家不调 LLM，零 token；在列表里才能在
step 7 出队手机菜单命令）。
"""

from __future__ import annotations

import logging
from typing import Any, List

from cyber_town.backend.config import HEARTBEAT_EVERY, PLAYER_ID

log = logging.getLogger(__name__)


class ActivationScheduler:
    """同场每拍 + 异地心跳错峰。世界不冻结：玩家不在的地点 NPC 仍低频活动。"""

    def __init__(
        self,
        player_id: int = PLAYER_ID,
        heartbeat_every: int = HEARTBEAT_EVERY,
    ) -> None:
        self.player_id = int(player_id)
        self.heartbeat_every = max(1, int(heartbeat_every))

    def pick_active(self, world: Any, t: int) -> List[int]:
        """返回本拍激活的 agent_id 列表（永远非 None）。"""
        active: List[int] = [self.player_id]
        try:
            player_place = world.location_of(self.player_id)
        except Exception:  # noqa: BLE001 — 容错：定位失败则全员心跳制
            player_place = None

        for aid in getattr(world, "agents", {}):
            aid = int(aid)
            if aid == self.player_id:
                continue
            if player_place is not None and world.location_of(aid) == player_place:
                active.append(aid)              # 同场：每拍激活
            elif (int(t) + aid) % self.heartbeat_every == 0:
                active.append(aid)              # 异地：低频心跳，按 id 错峰
        log.debug("t=%s active=%s", t, active)
        return active
