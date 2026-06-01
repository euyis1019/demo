"""F01 session data model."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agent_world.drama_demo.features.f01_session.constants import (
    DEFAULT_PLACE_ID,
    INITIAL_STATS,
)


@dataclass
class DramaSession:
    task_id: str
    start_tick: int
    place_id: str = DEFAULT_PLACE_ID
    # 导演已判定到的最后一句玩家发言 tick（只在玩家有新发言时再判 bert 是否触发，避免反复判同一句）。
    last_judged_player_tick: Optional[int] = None
    player_turn: int = 1
    stats: Dict[str, int] = field(default_factory=lambda: dict(INITIAL_STATS))
    ending_id: Optional[str] = None
    # ---- bert（条件→反应）运行期状态 ----
    # 已触发过的 bert id 列表：驱动 once（一次性）+ requires/arms（反应链上膛）。
    fired_berts: List[str] = field(default_factory=list)
    # agent_id(str) → 该 NPC 当前要演的反应：某条 bert 命中后写入，被 knowledge.py 注入到该 NPC 下一拍 prompt。
    bert_reactions: Dict[str, str] = field(default_factory=dict)
    # 结局 bert 命中时的收场文案与基调（good|neutral|bad），供结局屏显示。
    ending_summary: str = ""
    ending_kind: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "start_tick": self.start_tick,
            "place_id": self.place_id,
            "last_judged_player_tick": self.last_judged_player_tick,
            "player_turn": self.player_turn,
            "stats": dict(self.stats),
            "ending_id": self.ending_id,
            "fired_berts": list(self.fired_berts),
            "bert_reactions": dict(self.bert_reactions),
            "ending_summary": self.ending_summary,
            "ending_kind": self.ending_kind,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DramaSession":
        stats = dict(INITIAL_STATS)
        stats.update(data.get("stats") or {})
        return cls(
            task_id=str(data.get("task_id") or uuid.uuid4().hex),
            start_tick=int(data.get("start_tick", 0)),
            place_id=str(data.get("place_id") or DEFAULT_PLACE_ID),
            last_judged_player_tick=data.get("last_judged_player_tick"),
            player_turn=int(data.get("player_turn", 1)),
            stats=stats,
            ending_id=data.get("ending_id"),
            fired_berts=[str(x) for x in (data.get("fired_berts") or [])],
            bert_reactions={str(k): str(v) for k, v in (data.get("bert_reactions") or {}).items()},
            ending_summary=str(data.get("ending_summary") or ""),
            ending_kind=str(data.get("ending_kind") or ""),
        )
