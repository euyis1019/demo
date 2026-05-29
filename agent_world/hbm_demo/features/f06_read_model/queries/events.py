"""F06 read-only queries — group membership/events, relations, state & story logs.

Mixin for ``ReadOnlyWorldDB``; relies on ``self._with_retry`` from the base.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional


class EventQueriesMixin:
    """group_member / group_event / relation / agent_state_log / story_advance_log reads."""

    def fetch_group_members(self) -> Dict[int, List[int]]:
        def _query(conn: sqlite3.Connection) -> Dict[int, List[int]]:
            rows = conn.execute(
                "SELECT group_id, agent_id FROM group_member ORDER BY group_id, agent_id"
            ).fetchall()
            out: Dict[int, List[int]] = {}
            for row in rows:
                gid = int(row["group_id"])
                out.setdefault(gid, []).append(int(row["agent_id"]))
            return out

        return self._with_retry(_query)

    def fetch_group_events_since(
        self, since_t: int, t_now: int
    ) -> List[Dict[str, Any]]:
        def _query(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
            rows = conn.execute(
                """
                SELECT event_id, group_id, agent_id, event_type, occurred_at, actor_id
                FROM group_event
                WHERE occurred_at > ? AND occurred_at <= ?
                ORDER BY occurred_at, event_id
                """,
                (since_t, t_now),
            ).fetchall()
            return [dict(r) for r in rows]

        return self._with_retry(_query)

    def fetch_relations_snapshot(self) -> List[Dict[str, Any]]:
        def _query(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
            rows = conn.execute(
                """
                SELECT src_agent, dst_agent, relation_type, created_at, expires_at
                FROM relation
                ORDER BY src_agent, dst_agent, relation_type
                """
            ).fetchall()
            return [dict(r) for r in rows]

        return self._with_retry(_query)

    def fetch_state_logs_since(
        self,
        since_t: int,
        t_now: int,
        agent_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        def _query(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
            if agent_id is None:
                rows = conn.execute(
                    """
                    SELECT log_id, agent_id, content, at_tick
                    FROM agent_state_log
                    WHERE at_tick > ? AND at_tick <= ?
                    ORDER BY at_tick, log_id
                    """,
                    (since_t, t_now),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT log_id, agent_id, content, at_tick
                    FROM agent_state_log
                    WHERE agent_id=? AND at_tick > ? AND at_tick <= ?
                    ORDER BY at_tick, log_id
                    """,
                    (int(agent_id), since_t, t_now),
                ).fetchall()
            return [dict(r) for r in rows]

        return self._with_retry(_query)

    def fetch_story_advance_since(
        self,
        since_t: int,
        t_now: int,
        *,
        signal: Optional[str] = None,
        agent_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        def _query(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
            sql = """
                SELECT log_id, agent_id, signal, at_tick
                FROM story_advance_log
                WHERE at_tick > ? AND at_tick <= ?
            """
            params: list[Any] = [int(since_t), int(t_now)]
            if signal is not None:
                sql += " AND signal = ?"
                params.append(str(signal))
            if agent_id is not None:
                sql += " AND agent_id = ?"
                params.append(int(agent_id))
            sql += " ORDER BY at_tick ASC, log_id ASC"
            try:
                rows = conn.execute(sql, tuple(params)).fetchall()
            except sqlite3.OperationalError:
                return []
            return [dict(r) for r in rows]

        return self._with_retry(_query)
