"""Thread-safe FIFO queues for player input and script events (dev_logs/31 §四)."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional


@dataclass
class PlayerInputItem:
    events: List[Dict[str, Any]]
    turn_context: Dict[str, Any]
    broadcast: Optional[Dict[str, Any]] = None


@dataclass
class ScriptQueueItem:
    events: List[Dict[str, Any]]
    broadcast: Optional[Dict[str, Any]] = None


@dataclass
class PlayerInputQueue:
    max_depth: int = 32

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _player: Deque[PlayerInputItem] = field(default_factory=deque, repr=False)
    _script: Deque[ScriptQueueItem] = field(default_factory=deque, repr=False)
    _total_enqueued: int = 0
    _total_drained: int = 0

    def enqueue_player(self, item: PlayerInputItem) -> bool:
        with self._lock:
            if len(self._player) >= int(self.max_depth):
                return False
            self._player.append(item)
            self._total_enqueued += 1
            return True

    def enqueue_script(self, item: ScriptQueueItem) -> bool:
        with self._lock:
            if len(self._script) >= int(self.max_depth):
                return False
            self._script.append(item)
            self._total_enqueued += 1
            return True

    def depth(self) -> int:
        with self._lock:
            return len(self._player) + len(self._script)

    def player_depth(self) -> int:
        with self._lock:
            return len(self._player)

    def drain_for_tick(self) -> tuple[List[PlayerInputItem], List[ScriptQueueItem]]:
        """Drain all pending items at a tick boundary (player first, then script)."""
        with self._lock:
            players = list(self._player)
            scripts = list(self._script)
            self._player.clear()
            self._script.clear()
            self._total_drained += len(players) + len(scripts)
            return players, scripts

    def clear(self) -> None:
        with self._lock:
            self._player.clear()
            self._script.clear()

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "queue_depth": len(self._player) + len(self._script),
                "player_queue_depth": len(self._player),
                "script_queue_depth": len(self._script),
                "total_enqueued": self._total_enqueued,
                "total_drained": self._total_drained,
            }


__all__ = ["PlayerInputItem", "PlayerInputQueue", "ScriptQueueItem"]
