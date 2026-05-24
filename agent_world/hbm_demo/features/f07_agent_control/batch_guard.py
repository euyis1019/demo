"""F07-E — per-inject-batch guard state (first F2F / RDC tracking)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Set


@dataclass
class BatchGuardState:
    """Mutable state for one IPC inject batch (L5.1 first-action + L5.2 RDC quota)."""

    f2f_sent: Set[int] = field(default_factory=set)
    rdc_sent: Dict[int, int] = field(default_factory=dict)

    def mark_f2f(self, agent_id: int) -> None:
        self.f2f_sent.add(int(agent_id))

    def has_f2f(self, agent_id: int) -> bool:
        return int(agent_id) in self.f2f_sent

    def rdc_count(self, agent_id: int) -> int:
        return int(self.rdc_sent.get(int(agent_id), 0))

    def mark_rdc(self, agent_id: int, recipient_id: int) -> None:
        aid = int(agent_id)
        self.rdc_sent[aid] = self.rdc_sent.get(aid, 0) + 1
        _ = int(recipient_id)


__all__ = ["BatchGuardState"]
