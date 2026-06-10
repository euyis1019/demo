"""激活调度器：默认全员每拍（W3）；接入激活导演后按档位错峰（W5）。

默认（无 interval_provider）每个 NPC 每拍都获得思考机会——行动时机不被任何
规则代理。接入激活导演后，频率由低频 LLM 元决策分配（high/low/sleep），
时机分配从「规则代理」升级为「管理 agent 判断」，详见方案 §15.1。

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
from typing import Any, Callable, List, Optional

from cyber_town.backend.config import PLAYER_ID

log = logging.getLogger(__name__)


class ActivationScheduler:
    """激活调度：默认全员每拍；接入激活导演后按其档位（W5 智能预算）。

    ``interval_provider``：fn(npc_id) -> int（每几拍一次思考机会）。
    None = 全员每拍（纯自主默认，向后兼容）。导演档位是 LLM 元决策而非
    硬规则——时机分配从「规则代理」升级为「管理 agent 判断」（方案 §15）。
    """

    def __init__(self, player_id: int = PLAYER_ID,
                 interval_provider: Optional[Callable[[int], int]] = None) -> None:
        self.player_id = int(player_id)
        self.interval_provider = interval_provider

    def pick_active(self, world: Any, t: int) -> List[int]:
        """返回本拍激活的 agent_id 列表（永远非 None；玩家恒在）。"""
        active: List[int] = [self.player_id]
        for aid in getattr(world, "agents", {}):
            aid = int(aid)
            if aid == self.player_id:
                continue
            interval = 1
            if self.interval_provider is not None:
                try:
                    interval = max(1, int(self.interval_provider(aid)))
                except Exception:  # noqa: BLE001 — 导演异常→安全侧每拍
                    interval = 1
            if (int(t) + aid) % interval == 0:   # 按 id 错峰
                active.append(aid)
        log.debug("t=%s active=%s", t, active)
        return active
