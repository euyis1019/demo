"""F07-E — per-inject-batch guard state (first F2F tracking)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Set


@dataclass
class BatchGuardState:
    """Mutable state for one IPC inject batch (L5.1 first-action guard)."""

    f2f_sent: Set[int] = field(default_factory=set)

    def mark_f2f(self, agent_id: int) -> None:
        self.f2f_sent.add(int(agent_id))

    def has_f2f(self, agent_id: int) -> bool:
        return int(agent_id) in self.f2f_sent


__all__ = ["BatchGuardState"]
