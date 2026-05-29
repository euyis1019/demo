"""F06 read-only queries — LLM/prompt traces, trace links, place attributes.

Mixin for ``ReadOnlyWorldDB``; relies on ``self._with_retry`` from the base.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional


class TraceQueriesMixin:
    """agent_llm_trace / agent_action_trace_link / place reads."""

    def fetch_trace_by_id(self, trace_id: str) -> Optional[Dict[str, Any]]:
        def _query(conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
            row = conn.execute(
                "SELECT * FROM agent_llm_trace WHERE trace_id=?",
                (str(trace_id),),
            ).fetchone()
            return dict(row) if row else None

        return self._with_retry(_query)

    def fetch_trace_id_by_ref_key(self, ref_key: str) -> Optional[str]:
        def _query(conn: sqlite3.Connection) -> Optional[str]:
            row = conn.execute(
                """
                SELECT trace_id FROM agent_action_trace_link
                WHERE ref_key=?
                ORDER BY at_tick DESC
                LIMIT 1
                """,
                (str(ref_key),),
            ).fetchone()
            return str(row["trace_id"]) if row else None

        return self._with_retry(_query)

    def fetch_trace_links_for_trace(self, trace_id: str) -> List[Dict[str, Any]]:
        def _query(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
            rows = conn.execute(
                """
                SELECT link_id, trace_id, agent_id, at_tick, link_kind, ref_key
                FROM agent_action_trace_link
                WHERE trace_id=?
                ORDER BY at_tick, link_id
                """,
                (str(trace_id),),
            ).fetchall()
            return [dict(r) for r in rows]

        return self._with_retry(_query)

    def fetch_trace_links_since(
        self, since_t: int, t_now: int
    ) -> List[Dict[str, Any]]:
        def _query(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
            try:
                rows = conn.execute(
                    """
                    SELECT link_id, trace_id, agent_id, at_tick, link_kind, ref_key
                    FROM agent_action_trace_link
                    WHERE at_tick > ? AND at_tick <= ?
                    ORDER BY at_tick, link_id
                    """,
                    (int(since_t), int(t_now)),
                ).fetchall()
            except sqlite3.OperationalError:
                return []
            return [dict(r) for r in rows]

        return self._with_retry(_query)

    def list_traces(
        self,
        *,
        agent_id: Optional[int] = None,
        since_tick: Optional[int] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        def _query(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
            clauses = ["1=1"]
            params: List[Any] = []
            if agent_id is not None:
                clauses.append("agent_id=?")
                params.append(int(agent_id))
            if since_tick is not None:
                clauses.append("at_tick >= ?")
                params.append(int(since_tick))
            sql = f"""
                SELECT trace_id, agent_id, at_tick, phase, player_turn,
                       model, temperature, max_tokens, created_at
                FROM agent_llm_trace
                WHERE {' AND '.join(clauses)}
                ORDER BY at_tick DESC, trace_id DESC
                LIMIT ?
            """
            params.append(int(limit))
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

        return self._with_retry(_query)

    def fetch_place_attrs(self, place_ids: List[str]) -> Dict[str, str]:
        if not place_ids:
            return {}

        def _query(conn: sqlite3.Connection) -> Dict[str, str]:
            placeholders = ",".join("?" for _ in place_ids)
            rows = conn.execute(
                f"SELECT place_id, attrs FROM place WHERE place_id IN ({placeholders})",
                list(place_ids),
            ).fetchall()
            return {str(r["place_id"]): str(r["attrs"] or "{}") for r in rows}

        return self._with_retry(_query)
