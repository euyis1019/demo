"""AffinityStore —— 好感度持久化（独立 SQLite，不碰引擎 schema）。

设计（方案 §9）：
* 有序对 ``(npc_id, other_id)``：A 对 B 与 B 对 A 独立（允许单向冷淡）；
* 持有态度方必须是 NPC（玩家不调 LLM 不持有态度），写入前校验；
* 每次写入立即 commit（审计 AFF-6）；与 world.db 非原子是预期行为——
  好感度是软状态，崩溃最坏丢最近一拍 delta，可重算。
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS affinity (
  npc_id           INTEGER NOT NULL,
  other_id         INTEGER NOT NULL,
  score            INTEGER NOT NULL DEFAULT 10,
  updated_at       INTEGER NOT NULL DEFAULT 0,
  last_interact_at INTEGER NOT NULL DEFAULT 0,
  last_reason      TEXT,
  PRIMARY KEY (npc_id, other_id)
);
"""


class AffinityStore:
    """SQLite 读写：score 永远 clamp 到 [0, 100]。"""

    def __init__(self, db_path: str | Path, player_id: int) -> None:
        self._player_id = int(player_id)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ #

    def get_score(self, npc_id: int, other_id: int, default: int = 10) -> int:
        row = self._conn.execute(
            "SELECT score FROM affinity WHERE npc_id=? AND other_id=?",
            (int(npc_id), int(other_id)),
        ).fetchone()
        return int(row["score"]) if row else default

    def apply_delta(
        self,
        npc_id: int,
        other_id: int,
        delta: int,
        t: int,
        reason: str = "",
        touch_interact: bool = True,
    ) -> int:
        """加减分（带 clamp）并立即 commit；返回新 score。

        Raises:
            ValueError: 持有态度方是玩家时（会产生永不被读的死行）。
        """
        npc_id, other_id = int(npc_id), int(other_id)
        if npc_id == self._player_id:
            raise ValueError("玩家不持有好感度（不调 LLM），npc_id 不能是玩家")
        if npc_id == other_id:
            raise ValueError("不能对自己持有好感度")
        new_score = max(0, min(100, self.get_score(npc_id, other_id) + int(delta)))
        touched = 1 if touch_interact else 0
        self._conn.execute(
            "INSERT INTO affinity(npc_id, other_id, score, updated_at, "
            "  last_interact_at, last_reason) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(npc_id, other_id) DO UPDATE SET "
            "  score=excluded.score, updated_at=excluded.updated_at, "
            "  last_interact_at=CASE WHEN ? THEN excluded.last_interact_at "
            "                        ELSE affinity.last_interact_at END, "
            "  last_reason=excluded.last_reason",
            # 占位符顺序（审查 AFFINITY-002，勿乱序）：
            #   1-6 = VALUES(npc, other, score, updated_at, last_interact_at, reason)
            #   7   = CASE WHEN 条件（touched：衰减时传 0 → 不刷新互动时刻）
            (npc_id, other_id, new_score, int(t),
             int(t) if touch_interact else 0, reason[:120],
             touched),
        )
        self._conn.commit()
        return new_score

    def pairs_of(self, npc_id: int) -> List[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM affinity WHERE npc_id=?", (int(npc_id),),
        ).fetchall()

    def all_pairs(self) -> List[sqlite3.Row]:
        return self._conn.execute("SELECT * FROM affinity").fetchall()

    def seed(
        self,
        entries: List[Tuple[int, int, int, str]],
        initial_last_interact: int = -10,
    ) -> None:
        """灌初始底色（幂等：已存在的不覆盖）。entries=[(npc, other, score, reason)]

        ``initial_last_interact`` 默认 -10（= 衰减周期的"远古"）：种子关系是
        「早就认识」而非「t=0 刚互动过」，否则首个衰减检查点会误判
        （审查 AFFINITY-001——配合 manager 的严格大于条件，首次衰减最早 t=10+）。
        """
        for npc_id, other_id, score, reason in entries:
            if int(npc_id) == self._player_id:
                continue
            self._conn.execute(
                "INSERT OR IGNORE INTO affinity"
                "(npc_id, other_id, score, updated_at, last_interact_at, last_reason) "
                "VALUES(?,?,?,0,?,?)",
                (int(npc_id), int(other_id), max(0, min(100, int(score))),
                 int(initial_last_interact), reason),
            )
        self._conn.commit()
        log.info("好感度种子灌入完成（幂等），当前 %d 对", len(self.all_pairs()))
