"""F01 session data model."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from agent_world.hbm_demo.features.f01_session.constants import (
    DEFAULT_PHASE,
    DEFAULT_PLACE_ID,
    INITIAL_STATS,
)


@dataclass
class HbmSession:
    task_id: str
    start_tick: int
    place_id: str = DEFAULT_PLACE_ID
    phase: str = DEFAULT_PHASE
    # 当前剧情节点 id（节点驱动；phase 降级为该节点 beats_label 的显示值）。
    current_node_id: Optional[str] = None
    player_turn: int = 1
    stats: Dict[str, int] = field(default_factory=lambda: dict(INITIAL_STATS))
    phase2_start_tick: Optional[int] = None
    phase3_start_tick: Optional[int] = None
    phase4_start_tick: Optional[int] = None
    ending_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "start_tick": self.start_tick,
            "place_id": self.place_id,
            "phase": self.phase,
            "current_node_id": self.current_node_id,
            "player_turn": self.player_turn,
            "stats": dict(self.stats),
            "phase2_start_tick": self.phase2_start_tick,
            "phase3_start_tick": self.phase3_start_tick,
            "phase4_start_tick": self.phase4_start_tick,
            "ending_id": self.ending_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HbmSession":
        stats = dict(INITIAL_STATS)
        stats.update(data.get("stats") or {})
        return cls(
            task_id=str(data.get("task_id") or uuid.uuid4().hex),
            start_tick=int(data.get("start_tick", 0)),
            place_id=str(data.get("place_id") or DEFAULT_PLACE_ID),
            phase=str(data.get("phase") or DEFAULT_PHASE),
            current_node_id=data.get("current_node_id"),
            player_turn=int(data.get("player_turn", 1)),
            stats=stats,
            phase2_start_tick=data.get("phase2_start_tick"),
            phase3_start_tick=data.get("phase3_start_tick"),
            phase4_start_tick=data.get("phase4_start_tick"),
            ending_id=data.get("ending_id"),
        )
