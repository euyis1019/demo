"""世界事件导演：定期向小镇投放环境事件（W5）。

它产出的只是**世界事实**（一句环境描述，如「飘起细雨，泥路有些滑」
「今天是集市日，广场比平时热闹」），经两条途径生效：
* NPC 感知：作为提示词附加段「# 此刻的天时人事」——如何反应全由 NPC；
* 玩家感知：快照 ``world_event`` 字段 → 前端 HUD 显示。

绝不指挥任何角色（§4.8）；事件有时限，到期自动消散。
fail-soft：LLM 失败/拒绝 → 本窗口无事件，世界照常。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from cyber_town.backend.llm.json_call import call_llm_json
from cyber_town.backend.prompts.directors import (
    WORLD_SYSTEM,
    render_world_event_segment,
    render_world_user,
)

log = logging.getLogger(__name__)

DECIDE_EVERY = 24                 # 每 N 拍考虑一次（默认 ≈2 游戏小时）
DEFAULT_DURATION = 18             # 事件默认持续拍数


class WorldDirector:
    """维护当前生效的环境事件（文本+剩余时限）。"""

    def __init__(self, client: Any, model: str,
                 decide_every: int = DECIDE_EVERY) -> None:
        self._client = client
        self._model = model
        self._decide_every = max(4, int(decide_every))
        self._event: Optional[str] = None
        self._expires_at: int = -1
        self._history: list = []      # 最近事件文本（避免重复）
        self._task: Any = None

    # ---- 查询面 ---------------------------------------------------------

    def current_event(self, t: int) -> Optional[str]:
        if self._event is not None and t >= self._expires_at:
            log.info("世界事件消散：%s", self._event)
            self._event = None
        return self._event

    # ---- NPC 感知挂点（CyberTownNPC.world_event_provider）---------------

    def render_for_npc(self, t: int) -> str:
        ev = self.current_event(t)
        return render_world_event_segment(ev) if ev else ""

    # ---- tick_loop 钩子（后台决策，绝不拖拍）----------------------------

    def maybe_decide(self, asm: Any, t: int) -> None:
        if t % self._decide_every != 0 or t == 0:
            return
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._decide(asm, t))

    async def _decide(self, asm: Any, t: int) -> None:
        wall = self._wall_time(asm, t)
        recent = "；".join(self._history[-3:]) or "（无）"
        cur = self._event or "（无）"
        data = await call_llm_json(
            self._client, self._model, WORLD_SYSTEM,
            render_world_user(wall, t, cur, recent),
        )
        if not data:
            return
        ev = data.get("event")
        if not ev or not str(ev).strip():
            log.info("世界事件导演 t=%s：本窗口平平常常（%s）",
                     t, str(data.get("reason", ""))[:60])
            return
        try:
            duration = max(8, min(40, int(data.get("duration_ticks", DEFAULT_DURATION))))
        except (TypeError, ValueError):
            duration = DEFAULT_DURATION
        self._event = str(ev).strip()[:80]
        self._expires_at = t + duration
        self._history.append(self._event)
        log.info("世界事件 t=%s（持续 %d 拍）：%s", t, duration, self._event)

    @staticmethod
    def _wall_time(asm: Any, t: int) -> str:
        cfg = (asm.scenario.get("clock") or {})
        try:
            h, m = str(cfg.get("start_time", "08:00")).split(":")
            total = (int(h) * 60 + int(m)
                     + t * int(cfg.get("minutes_per_tick", 5))) % (24 * 60)
            return f"{total // 60:02d}:{total % 60:02d}"
        except ValueError:
            return "?"
