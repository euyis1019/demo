"""AffinityManager —— 好感度业务逻辑（方案 §9：主路 piggyback + 规则法底噪）。

两条更新路（叠加，零额外 LLM 调用）：
* **主路**：NPC 决策时 LLM 顺带产出私有工具 ``adjust_affinity(target, delta,
  reason)``——该工具引擎 dispatcher 不认识会静默丢弃，所以由
  ``CyberTownNPC.private_tool_handler`` 在返回引擎**之前**拦截到这里；
  delta clamp [-3, +5]。
* **底噪（规则法）**：tick 末直接查 world_db（不依赖 obs——那是 NPC 决策内
  的局部变量，审计 AFF-4）：玩家当面说 +2 / 私信 +1 / 同地点共处 +0.5/拍
  （半分用两拍 +1 实现）/ 连续 ≥10 拍无互动 -1。每对单拍累计 clamp [-2, +5]。

注入：``prompt_suffix_provider`` 给 NPC 系统提示词追加第 6 段「我对在场各人
的态度」（只渲染在场者控 token），不动引擎前 5 段。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# 5 档阈值与行为指引（集中一处，调档只改这里）
LEVELS = [
    (80, "挚友", "无话不谈，可以交心、可以托付事情"),
    (60, "亲密", "很信任对方，主动关心，愿意分享心里话"),
    (40, "友好", "当朋友处，主动攀谈，愿意帮些小忙"),
    (20, "熟悉", "脸熟了，正常来往，话比对陌生人多些"),
    (0,  "陌生", "还不熟，客气但保持距离，不交浅言深"),
]

# 私有工具 schema（追加进 NPC 的 tools；引擎不认识它，必须前置拦截）
ADJUST_AFFINITY_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "adjust_affinity",
        "description": (
            "（内心活动，别人看不见）这一拍的互动让你对某人的观感变了，"
            "就调整你对 ta 的好感。变化要克制：日常寒暄 ±1，"
            "真正暖心/伤人的事才 ±3 以上。可以和说话动作同拍使用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target": {"type": "integer", "description": "对方 agent_id"},
                "delta": {"type": "integer", "description": "好感变化，-3 到 +5"},
                "reason": {"type": "string", "description": "一句话原因（内心记一笔）"},
            },
            "required": ["target", "delta"],
            "additionalProperties": False,
        },
    },
}

# 规则法权重（方案 §13 Q3 默认值，M4 可调）
RULE_F2F_FROM_PLAYER = 2      # 玩家当面对话
RULE_RDC_FROM_PLAYER = 1      # 玩家私信
RULE_COPRESENCE_EVERY = 2     # 同地点共处：每 2 拍 +1（等效 +0.5/拍）
RULE_DECAY_AFTER = 10         # 连续 N 拍无互动
RULE_DECAY = -1
LLM_DELTA_MIN, LLM_DELTA_MAX = -3, 5
RULE_TICK_MIN, RULE_TICK_MAX = -2, 5   # 规则法单拍累计 clamp


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
        lines = ["# 我对在场各人的态度（依此把握语气与主动程度，别直接念数字）"]
        for other in present:
            score = self._store.get_score(npc.agent_id, other)
            level, guide = self.level_of(score)
            who = self._names.get(other, f"agent_{other}")
            tag = "（玩家）" if other == self._player_id else ""
            lines.append(f"- {who}{tag}：{level} {score}/100 —— {guide}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # 规则法底噪（tick_loop 末调用；直接查 world_db）                      #
    # ------------------------------------------------------------------ #

    def apply_rule_based(self, asm: Any, report: Dict[str, Any]) -> None:
        """按本拍世界事实给「NPC 对玩家」的好感做底噪累计（fail-soft）。"""
        try:
            t = int(report.get("t", 0))
            deltas: Dict[int, int] = {}      # npc_id -> 本拍累计
            interacted: set = set()

            # 玩家本拍发出的消息（F2F 扇出行 recipient=NPC / RDC 单行）；
            # DISTINCT 防御理论上的重复行（审查 AFF-004）
            rows = asm.world_db._conn.execute(  # noqa: SLF001 — 只读统计
                "SELECT DISTINCT recipient_id, channel_type FROM direct_message "
                "WHERE sender_id=? AND attempted_at=? AND delivered=1",
                (self._player_id, t),
            ).fetchall()
            for rid, ch in rows:
                rid = int(rid)
                if ch == "F2F":
                    deltas[rid] = deltas.get(rid, 0) + RULE_F2F_FROM_PLAYER
                elif ch == "RDC":
                    deltas[rid] = deltas.get(rid, 0) + RULE_RDC_FROM_PLAYER
                interacted.add(rid)

            player_place = asm.world.location_of(self._player_id)
            for npc in asm.npcs:
                nid = npc.agent_id
                # 共处底噪：每 RULE_COPRESENCE_EVERY 拍 +1
                if (asm.world.location_of(nid) == player_place
                        and t % RULE_COPRESENCE_EVERY == 0):
                    deltas[nid] = deltas.get(nid, 0) + 1
                    interacted.add(nid)
                # 疏远衰减：太久没互动（衰减不刷新互动时刻）
                # rows_n 为空时 last=0 意为「从未互动」；严格大于（>）配合种子
                # 的 last_interact_at=-10，保证首次衰减最早发生在 t>10 的检查点
                # （审查 AFFINITY-001/AFF-005）。注意：共处底噪每 2 拍续期互动
                # 时刻，小世界里衰减本就罕见——属预期的温和设计，触发必留日志。
                rows_n = [r for r in self._store.pairs_of(nid)
                          if int(r["other_id"]) == self._player_id]
                last = int(rows_n[0]["last_interact_at"]) if rows_n else 0
                if nid not in interacted and t - last > RULE_DECAY_AFTER \
                        and t % RULE_DECAY_AFTER == 0:
                    deltas[nid] = deltas.get(nid, 0) + RULE_DECAY
                    log.info("好感度疏远衰减：%s→玩家 %d（上次互动 t=%d，现 t=%d）",
                             self._names.get(nid, nid), RULE_DECAY, last, t)

            for nid, d in deltas.items():
                d = max(RULE_TICK_MIN, min(RULE_TICK_MAX, d))
                if d == 0 or nid == self._player_id:
                    continue
                self._store.apply_delta(
                    nid, self._player_id, d, t,
                    reason="规则底噪", touch_interact=(nid in interacted),
                )
        except Exception as exc:  # noqa: BLE001 — 底噪失败不阻断 tick
            log.warning("好感度规则法本拍跳过：%s", exc)

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
