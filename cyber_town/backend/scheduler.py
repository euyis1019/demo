"""激活调度器：**全员每拍激活**（W3 纯自主化，用户拍板推翻原 D5 心跳制）。

每个 NPC 每拍都获得思考机会——行动时机不再被调度器代理，世界全域同步活着
（token 成本随 NPC 数线性增长，3 NPC 规模可接受）。

引擎契约（world/step.py::_pick_active）：
* scheduler 非 None 且 ``pick_active`` 返回**非 None** → 直接用该列表，
  跳过 per-agent ``activity_level`` 门控（二者互斥，本项目只用 scheduler）。

⚠ 红线级注意（审计 SEED-5）：``step.py:233`` 对 agent_id=0 有 ``or`` 真值
陷阱，仅在 scheduler 缺席的默认路径触发——所以本调度器**永远返回非 None
列表**（这也是全员激活仍保留 scheduler 而非传 None 的原因），且玩家 id
恒在列表里（玩家不调 LLM，零 token；在列表里才能出队手机菜单命令）。
"""

from __future__ import annotations

import logging
from typing import Any, List

from cyber_town.backend.config import PLAYER_ID

log = logging.getLogger(__name__)


class ActivationScheduler:
    """全员每拍激活：谁都不被代理「何时能思考」。"""

    def __init__(self, player_id: int = PLAYER_ID) -> None:
        self.player_id = int(player_id)

    def pick_active(self, world: Any, t: int) -> List[int]:
        """返回本拍激活的 agent_id 列表（永远非 None；玩家恒在 + 全部 NPC）。"""
        active: List[int] = [self.player_id]
        for aid in getattr(world, "agents", {}):
            aid = int(aid)
            if aid != self.player_id:
                active.append(aid)
        log.debug("t=%s active=%s", t, active)
        return active
