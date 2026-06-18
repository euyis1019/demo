"""AffinityManager —— 好感度业务逻辑（W3 纯自主化：唯一更新路 = LLM 主路）。

**好感度 100% 由 NPC 自己决定**（用户自主性审计后拍板）：NPC 决策时经私有
工具 ``adjust_affinity(target, delta, reason)`` 自主记录观感变化——该工具
引擎 dispatcher 不认识会静默丢弃，所以由 ``CyberTownNPC.private_tool_handler``
在返回引擎**之前**拦截到这里；delta clamp [-3, +5] 仅防爆表，是否调用/对谁/
多少/原因全由 LLM 决定。

> 历史注记：曾有「规则法底噪」（按消息历史自动 +2/+1/共处/衰减），因属
> 「后端代理 NPC 内心」且形成虚假自我认知回路，经审计后整体移除——
> 提示词层改为明确引导 LLM 主动评估（见 ADJUST_AFFINITY_TOOL 与第 6 段）。

注入：``prompt_suffix_provider`` 给 NPC 系统提示词追加第 6 段「我对在场各人
的态度」（只渲染在场者控 token），不动引擎前 5 段。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

# 文本件全部来自 prompts（W6 集中管理）；从本模块 re-export 维持旧引用面
from cyber_town.backend.prompts.affinity import (
    ADJUST_AFFINITY_TOOL,
    LEVELS,
    REFLECT_REMINDER,
    REPUTATION_NOTE,
    SUFFIX_FOOTER,
    SUFFIX_HEADER,
    render_attitude_line,
)

log = logging.getLogger(__name__)

LLM_DELTA_MIN, LLM_DELTA_MAX = -3, 5   # 主路单次 clamp（仅防爆表）


class AffinityManager:
    """好感度门面：NPC 挂点接线 / 两条更新路 / 渲染与快照导出。"""

    def __init__(self, store: Any, name_directory: Dict[int, str], player_id: int) -> None:
        self._store = store
        self._names = dict(name_directory)
        self._player_id = int(player_id)

    # ------------------------------------------------------------------ #
    # NPC 挂点接线（在 world_factory 装配之后调用，保持工厂与好感度解耦）   #
    # ------------------------------------------------------------------ #

    def wire_npcs(self, npcs: List[Any]) -> None:
        """给每个 CyberTownNPC 装上：私有工具 + 拦截 handler + 第 6 段渲染。"""
        for npc in npcs:
            npc.extra_tools = list(getattr(npc, "extra_tools", [])) + [ADJUST_AFFINITY_TOOL]
            npc.private_tool_names = frozenset(
                set(npc.private_tool_names) | {"adjust_affinity"}
            )
            npc.private_tool_handler = self._on_private_tool
            npc.prompt_suffix_provider = self._render_suffix
        log.info("好感度挂点接线完成：%d 个 NPC", len(npcs))

    def _on_private_tool(self, npc: Any, name: str, args: Dict[str, Any], t: int) -> None:
        """主路：拦截 adjust_affinity（永不进引擎 dispatcher）。

        内部全程 fail-soft 并落详细日志（审查 AFF-003：异常若上抛会被 npc.py
        吞成一行 warning，好感更新静默丢失难排查——在源头记全上下文）。
        """
        if name != "adjust_affinity":
            return
        try:
            target = int(args.get("target"))
            delta = max(LLM_DELTA_MIN, min(LLM_DELTA_MAX, int(args.get("delta", 0))))
            if delta == 0 or target == npc.agent_id:
                return
            new_score = self._store.apply_delta(
                npc.agent_id, target, delta, t,
                reason=str(args.get("reason", ""))[:120],
            )
            log.info("好感度(主路) %s→%s %+d => %d（%s）",
                     npc.name, self._names.get(target, target), delta, new_score,
                     args.get("reason", ""))
        except Exception as exc:  # noqa: BLE001 — 主路失败不阻断 NPC 决策
            log.error("好感度主路失败 npc=%s tool=%s args=%s t=%s：%s",
                      getattr(npc, "agent_id", "?"), name, args, t, exc)

    # ------------------------------------------------------------------ #
    # 第 6 段提示词（fn(npc, obs) -> str，空串=不追加）                     #
    # ------------------------------------------------------------------ #

    def _render_suffix(self, npc: Any, obs: Any) -> str:
        present = [int(a) for a in (getattr(obs, "co_located_agents", None) or [])]
        if not present:
            return ""
        lines = [SUFFIX_HEADER]
        for other in present:
            score = self._store.get_score(npc.agent_id, other)
            level, guide = self.level_of(score)
            who = self._names.get(other, f"agent_{other}")
            lines.append(render_attitude_line(
                who, other == self._player_id, level, score, guide))
        lines.append(SUFFIX_FOOTER)
        lines.append(REPUTATION_NOTE)  # 口碑流动软引导（焐心小镇支柱4）
        # 条件化自省提醒（非每拍重复，仅在真的收到话时触发——避免空泛诱导）
        heard = bool(getattr(obs, "incoming_messages", None)) or \
            bool(getattr(obs, "overheard", None))
        if heard:
            lines.append(REFLECT_REMINDER)
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # 导出                                                                 #
    # ------------------------------------------------------------------ #

    @staticmethod
    def level_of(score: int) -> tuple:
        for threshold, name, guide in LEVELS:
            if score >= threshold:
                return name, guide
        return LEVELS[-1][1], LEVELS[-1][2]

    def to_player_score(self, npc_id: int) -> Optional[int]:
        if npc_id == self._player_id:
            return None
        return self._store.get_score(npc_id, self._player_id)

    def snapshot_dict(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """全量好感度（WS 快照用）：{npc_id: {other_id: {score, level}}}"""
        out: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for row in self._store.all_pairs():
            level, _ = self.level_of(int(row["score"]))
            out.setdefault(str(row["npc_id"]), {})[str(row["other_id"])] = {
                "score": int(row["score"]), "level": level,
            }
        return out


## 世界种子里的初始底色（方案 §9：老乡/邻里的起步关系）
DEFAULT_SEED = [
    (1, 2, 45, "老乡，几十年街坊"),       # 老钱 → 阿香
    (2, 1, 45, "老乡，几十年街坊"),       # 阿香 → 老钱
    (1, 3, 35, "常来买农具的老主顾"),     # 老钱 → 大山
    (3, 1, 35, "镇上买东西全靠他"),       # 大山 → 老钱
    (2, 3, 30, "常来喝两杯的老实人"),     # 阿香 → 大山
    (3, 2, 30, "酒馆老板娘，热心肠"),     # 大山 → 阿香
    (3, 0, 30, "新邻居，看着顺眼"),       # 大山 → 玩家（人设：对新邻居有好感）
    (1, 0, 15, "新来的农场主，还不熟"),   # 老钱 → 玩家
    (2, 0, 10, "听说来了个新农场主"),     # 阿香 → 玩家
]
