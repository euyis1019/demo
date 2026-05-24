"""F11 — Live Turn Sync (round内增量同步).

F11-A: async inject + early player-turn return.
F11-B/C: delta API + frontend merge (see dev_logs/28).
"""

__all__ = [
    "clear_async_state",
    "start_background_turn",
    "sync_runtime_state",
]
