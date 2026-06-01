"""F06 read-only queries — agent locations and movement logs.

Mixin for ``ReadOnlyWorldDB``; relies on ``self._with_retry`` from the base.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List


class MoveQueriesMixin:
    """agent_location and agent_location_log reads."""

    def agents_at(self, place_id: str) -> List[int]:
        def _query(conn: sqlite3.Connection) -> List[int]:
            rows = conn.execute(
                "SELECT agent_id FROM agent_location WHERE place_id=?",
                (place_id,),
            ).fetchall()
            return [int(r["agent_id"]) for r in rows]

        return self._with_retry(_query)

    def fetch_all_agent_locations(self) -> Dict[int, Dict[str, Any]]:
        def _query(conn: sqlite3.Connection) -> Dict[int, Dict[str, Any]]:
            rows = conn.execute(
                "SELECT agent_id, place_id, arrived_at FROM agent_location"
            ).fetchall()
            return {
                int(r["agent_id"]): {
                    "place_id": str(r["place_id"]),
                    "arrived_at": int(r["arrived_at"]),
                }
                for r in rows
            }

        return self._with_retry(_query)

    def fetch_location_logs_since(
        self, since_t: int, t_now: int
    ) -> List[Dict[str, Any]]:
        def _query(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
            rows = conn.execute(
                """
                SELECT log_id, agent_id, from_place, to_place, at_tick, source
                FROM agent_location_log
                WHERE at_tick > ? AND at_tick <= ?
                ORDER BY at_tick, log_id
                """,
                (since_t, t_now),
            ).fetchall()
            return [dict(r) for r in rows]

        return self._with_retry(_query)
