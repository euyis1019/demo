"""激活导演：LLM 元决策「谁高频思考、谁降频、谁休眠」（W5）。

替代两代旧方案：硬规则心跳制（W3 前，时机被规则代理）与全员每拍激活
（W3，token 随 NPC 数线性烧）。导演每 ``DECIDE_EVERY`` 拍读一份世界摘要，
为每个 NPC 产出激活档位——**只分配思考预算，不接触行为内容**（§4.8）。

档位语义（频率 = 每几拍获得一次决策机会，按 id 错峰）：
* high : 每拍（在对话中/玩家在场/手头有事）
* low  : 每 4 拍（独处干活、无社交热点）
* sleep: 每 12 拍（长时间无事；保底唤醒，绝不永久冻结）

fail-soft：LLM 失败/超时/输出不合法 → 沿用上一份策略；首份默认全 high。
决策在后台 task 进行，绝不拖拍。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict

from cyber_town.backend.directors.base import call_llm_json

log = logging.getLogger(__name__)

DECIDE_EVERY = 10                  # 每 N 拍元决策一次
TIER_INTERVAL = {"high": 1, "low": 4, "sleep": 12}

_SYSTEM = (
    "你是一个多智能体小镇仿真的「激活导演」。你不控制任何角色的言行，"
    "只决定下个时间窗口里每个 NPC 获得思考机会的频率，目标是：\n"
    "1) 正在与玩家互动、或彼此对话进行中的 NPC 必须 high（不许打断对话）；\n"
    "2) 有未回应消息/刚被点名的 NPC 必须 high；\n"
    "3) 独处且无事的 NPC 用 low 省算力；长期完全无事的可 sleep；\n"
    "4) 宁可多给 high，不要让活跃场景卡顿。\n"
    "只输出 JSON：{\"tiers\": {\"<npc_id>\": \"high|low|sleep\", ...}, \"reason\": \"一句话\"}"
)


class ActivationDirector:
    """维护一张激活策略表，供 ActivationScheduler 查询。"""

    def __init__(self, client: Any, model: str, npc_ids: list,
                 decide_every: int = DECIDE_EVERY) -> None:
        self._client = client
        self._model = model
        self._npc_ids = [int(i) for i in npc_ids]
        self._decide_every = max(2, int(decide_every))
        # 首份策略：全 high（向纯自主的安全侧倾斜）
        self.tiers: Dict[int, str] = {i: "high" for i in self._npc_ids}
        self._task: Any = None

    # ---- ActivationScheduler 查询面 -----------------------------------

    def interval_of(self, npc_id: int) -> int:
        return TIER_INTERVAL.get(self.tiers.get(int(npc_id), "high"), 1)

    # ---- tick_loop 钩子（后台决策，绝不拖拍）---------------------------

    def maybe_decide(self, asm: Any, t: int) -> None:
        if t % self._decide_every != 0:
            return
        if self._task is not None and not self._task.done():
            return  # 上一轮还在跑，跳过
        self._task = asyncio.create_task(self._decide(asm, t))

    async def _decide(self, asm: Any, t: int) -> None:
        try:
            summary = self._world_digest(asm, t)
        except Exception as exc:  # noqa: BLE001 — 摘要失败不挡元决策
            log.warning("激活导演世界摘要失败：%s", exc)
            summary = "（世界摘要暂不可用，请保守地全员 high）"
        data = await call_llm_json(
            self._client, self._model, _SYSTEM,
            f"当前 tick t={t}。世界近况：\n{summary}\n请给出下个窗口的激活档位。",
        )
        if not data or "tiers" not in data:
            log.info("激活导演：本轮无有效输出，沿用现策略 %s", self.tiers)
            return
        new: Dict[int, str] = {}
        for k, v in (data.get("tiers") or {}).items():
            try:
                nid = int(k)
            except (TypeError, ValueError):
                continue
            if nid in self._npc_ids and v in TIER_INTERVAL:
                new[nid] = v
        # 未提到的 NPC 安全侧补 high（导演漏写不能让人冻结）
        for nid in self._npc_ids:
            new.setdefault(nid, "high")
        self.tiers = new
        log.info("激活导演 t=%s 新策略：%s（%s）",
                 t, new, str(data.get("reason", ""))[:80])

    # ---- 世界摘要（只读）------------------------------------------------

    def _world_digest(self, asm: Any, t: int) -> str:
        lines = []
        player_place = asm.world.location_of(asm.player.agent_id)
        lines.append(f"玩家位置：{player_place}")
        # 最近 5 拍的消息热度（含未回应私信检测的原料）
        rows = asm.world_db._conn.execute(  # noqa: SLF001 — 只读摘要
            "SELECT sender_id, recipient_id, channel_type FROM direct_message "
            "WHERE attempted_at > ? AND delivered=1", (t - 5,),
        ).fetchall()
        recent_pairs = {(int(s) if s is not None else -1, int(r)) for s, r, _ in rows}
        for npc in asm.npcs:
            nid = npc.agent_id
            place = asm.world.location_of(nid)
            cs = (npc.current_state or "").replace("\n", " ")[:40]
            talking = any(s == nid or r == nid for s, r in recent_pairs)
            with_player = "与玩家同地点" if place == player_place else "独处异地"
            lines.append(
                f"- NPC {nid}（{npc.name}）@{place}，{with_player}，"
                f"近5拍{'有' if talking else '无'}消息往来，状态：{cs}"
            )
        return "\n".join(lines)
