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
            elif self._needs_urgent_wake(world, aid, t):
                # W7 紧急唤醒：有未读私信（已送达、还没看过）的 NPC 不等档位
                # ——「手机响了把人叫醒」是思考预算分配，不碰行为内容（§4.8）。
                # 没有它，low/sleep 档 NPC 最长 4~12 拍后才看到私信，玩家
                # 体感就是已读不回（W7 截图复现的根因之一）。
                # W17：扩展到「玩家发到群里的消息」——否则睡眠中的 NPC 看不到
                # 玩家在群里招呼，群聊永远冷场（只唤醒玩家发的群消息，NPC 之间
                # 的群闲聊不强制叫醒，避免连锁唤醒雪崩）。
                active.append(aid)
                log.info("t=%s NPC %s 有未读私信/群招呼，紧急唤醒（绕过档位）", t, aid)
        log.debug("t=%s active=%s", t, active)
        return active

    @staticmethod
    def _needs_urgent_wake(world: Any, aid: int, t: int) -> bool:
        """该 NPC 是否有值得立刻叫醒的未读消息（已送达、还没感知过；fail-soft）：

        * 任何人发来的 RDC 私信——私信盼回音，最伤的是已读不回；
        * **玩家**发到群里的 GRP 消息——玩家在群里招呼总得有人应；NPC 之间的
          群闲聊不在此列（避免每条群消息都把全员叫醒造成连锁唤醒）。
        """
        try:
            db = getattr(world, "world_db", None)
            agent = world.agents.get(aid)
            if db is None or agent is None:
                return False
            last_seen = int(getattr(agent, "last_message_seen_at", -1) or -1)
            rows = db.fetch_arrived_for(aid, int(t), last_seen)
            for r in rows:
                ch = getattr(r, "channel_type", "")
                if ch == "RDC":
                    return True
                if ch == "GRP" and int(getattr(r, "sender_id", -1)) == PLAYER_ID:
                    return True
            return False
        except Exception:  # noqa: BLE001 — 查询失败不影响正常调度
            return False
