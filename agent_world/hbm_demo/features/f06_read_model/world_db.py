"""F06 Flask-side read-only SQLite world accessor."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from agent_world.hbm_demo.features.f01_session.paths import get_world_db_path
from agent_world.hbm_demo.shared.errors import DatabaseReadError
from agent_world.hbm_demo.shared.settings import DB_CONNECT_TIMEOUT, DB_READ_RETRIES

SYSTEM_SENDER_NAME = "彭博终端"


def sender_display_name(sender_id: Optional[int], name_map: dict[int, str]) -> str:
    if sender_id is None:
        return "未知"
    sid = int(sender_id)
    if sid == -1:
        return SYSTEM_SENDER_NAME
    return name_map.get(sid, f"agent_{sid}")


class ReadOnlyWorldDB:
    """Flask-side read-only SQLite accessor with lock retry."""

    def __init__(
        self,
        db_path: Path,
        *,
        timeout: float = DB_CONNECT_TIMEOUT,
        retries: int = DB_READ_RETRIES,
    ) -> None:
        self.db_path = db_path
        self.timeout = timeout
        self.retries = retries

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=self.timeout,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        return conn

    def _with_retry(self, fn: Any, *, retries: int | None = None) -> Any:
        delay = 0.05
        attempts = retries if retries is not None else self.retries
        last_exc: Exception | None = None
        for _attempt in range(attempts):
            try:
                conn = self._connect()
                try:
                    return fn(conn)
                finally:
                    conn.close()
            except sqlite3.OperationalError as exc:
                last_exc = exc
                if "locked" not in str(exc).lower():
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 0.5)
        if last_exc is not None:
            raise DatabaseReadError(str(last_exc)) from last_exc
        raise DatabaseReadError("database read failed")

    def agents_at(self, place_id: str) -> List[int]:
        def _query(conn: sqlite3.Connection) -> List[int]:
            rows = conn.execute(
                "SELECT agent_id FROM agent_location WHERE place_id=?",
                (place_id,),
            ).fetchall()
            return [int(r["agent_id"]) for r in rows]

        return self._with_retry(_query)

    def fetch_f2f_history_at(
        self,
        place_id: str,
        t_now: int,
        since_t: int,
        *,
        limit: int = 30,
        exclusive_since: bool = False,
    ) -> List[Tuple[int, int, int, str]]:
        def _query(conn: sqlite3.Connection) -> List[Tuple[int, int, int, str]]:
            since_op = ">" if exclusive_since else ">="
            rows = conn.execute(
                f"""
                SELECT MIN(message_id) AS message_id, sender_id,
                       attempted_at, content
                FROM direct_message
                WHERE channel_type='F2F' AND place_id=?
                  AND attempted_at {since_op} ? AND attempted_at <= ?
                GROUP BY sender_id, attempted_at, content
                ORDER BY attempted_at, message_id
                LIMIT ?
                """,
                (place_id, since_t, t_now, limit),
            ).fetchall()
            return [
                (
                    int(r["attempted_at"]),
                    int(r["sender_id"]),
                    int(r["message_id"]),
                    str(r["content"]),
                )
                for r in rows
            ]

        return self._with_retry(_query)

    def fetch_messages_since(
        self,
        *,
        channel_type: str,
        since_t: int,
        t_now: int,
    ) -> List[sqlite3.Row]:
        def _query(conn: sqlite3.Connection) -> List[sqlite3.Row]:
            return conn.execute(
                """
                SELECT message_id, sender_id, recipient_id, group_id,
                       channel_type, content, place_id, attempted_at, delivered
                FROM direct_message
                WHERE channel_type=? AND attempted_at > ? AND attempted_at <= ?
                ORDER BY attempted_at, message_id
                """,
                (channel_type, since_t, t_now),
            ).fetchall()

        return self._with_retry(_query)

    def has_f2f_after(
        self, place_id: str, start_tick: int, t_now: int
    ) -> bool:
        def _query(conn: sqlite3.Connection) -> bool:
            row = conn.execute(
                """
                SELECT 1 FROM direct_message
                WHERE channel_type='F2F' AND place_id=?
                  AND attempted_at > ? AND attempted_at <= ?
                LIMIT 1
                """,
                (place_id, start_tick, t_now),
            ).fetchone()
            return row is not None

        return bool(self._with_retry(_query))

    def has_rdc_pair_after(
        self,
        pairs: List[Tuple[int, int]],
        start_tick: int,
        t_now: int,
    ) -> bool:
        if not pairs:
            return False

        def _query(conn: sqlite3.Connection) -> bool:
            rows = conn.execute(
                """
                SELECT sender_id, recipient_id FROM direct_message
                WHERE channel_type='RDC'
                  AND attempted_at > ? AND attempted_at <= ?
                """,
                (start_tick, t_now),
            ).fetchall()
            for row in rows:
                s, r = int(row["sender_id"]), int(row["recipient_id"])
                for a, b in pairs:
                    if (s, r) == (a, b) or (s, r) == (b, a):
                        return True
            return False

        return bool(self._with_retry(_query))

    def fetch_rdc_messages(
        self,
        *,
        sender_id: int,
        recipient_id: int,
        since_t: int,
        t_now: int,
    ) -> List[sqlite3.Row]:
        def _query(conn: sqlite3.Connection) -> List[sqlite3.Row]:
            return conn.execute(
                """
                SELECT message_id, sender_id, recipient_id, content, attempted_at
                FROM direct_message
                WHERE channel_type='RDC'
                  AND sender_id=? AND recipient_id=?
                  AND attempted_at >= ? AND attempted_at <= ?
                ORDER BY attempted_at, message_id
                """,
                (sender_id, recipient_id, since_t, t_now),
            ).fetchall()

        return self._with_retry(_query)

    def has_grp_after(
        self, group_ids: Set[int], start_tick: int, t_now: int
    ) -> bool:
        if not group_ids:
            return False

        def _query(conn: sqlite3.Connection) -> bool:
            placeholders = ",".join("?" for _ in group_ids)
            params = [start_tick, t_now, *sorted(group_ids)]
            row = conn.execute(
                f"""
                SELECT 1 FROM direct_message
                WHERE channel_type='GRP'
                  AND attempted_at > ? AND attempted_at <= ?
                  AND group_id IN ({placeholders})
                LIMIT 1
                """,
                params,
            ).fetchone()
            return row is not None

        return bool(self._with_retry(_query))


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

    def fetch_f2f_by_places(
        self,
        since_t: int,
        t_now: int,
        place_ids: List[str],
        *,
        limit: int = 30,
    ) -> Dict[str, List[tuple]]:
        out: Dict[str, List[tuple]] = {}
        for place_id in place_ids:
            out[place_id] = self.fetch_f2f_history_at(
                place_id,
                t_now,
                since_t,
                limit=limit,
                exclusive_since=True,
            )
        return out

    def fetch_rdc_for_agent(
        self,
        agent_id: int,
        since_t: int,
        t_now: int,
    ) -> List[sqlite3.Row]:
        def _query(conn: sqlite3.Connection) -> List[sqlite3.Row]:
            return conn.execute(
                """
                SELECT message_id, sender_id, recipient_id, group_id,
                       channel_type, content, place_id, attempted_at, delivered
                FROM direct_message
                WHERE channel_type='RDC'
                  AND attempted_at > ? AND attempted_at <= ?
                  AND (sender_id=? OR recipient_id=?)
                ORDER BY attempted_at, message_id
                """,
                (since_t, t_now, int(agent_id), int(agent_id)),
            ).fetchall()

        return self._with_retry(_query)

    def fetch_grp_for_agent(
        self,
        agent_id: int,
        since_t: int,
        t_now: int,
    ) -> List[sqlite3.Row]:
        def _query(conn: sqlite3.Connection) -> List[sqlite3.Row]:
            return conn.execute(
                """
                SELECT dm.message_id, dm.sender_id, dm.recipient_id, dm.group_id,
                       dm.channel_type, dm.content, dm.place_id, dm.attempted_at,
                       dm.delivered
                FROM direct_message dm
                INNER JOIN group_member gm
                    ON gm.group_id = dm.group_id AND gm.agent_id = ?
                WHERE dm.channel_type='GRP'
                  AND dm.attempted_at > ? AND dm.attempted_at <= ?
                  AND (dm.sender_id=? OR dm.recipient_id=?)
                ORDER BY dm.attempted_at, dm.message_id
                """,
                (int(agent_id), since_t, t_now, int(agent_id), int(agent_id)),
            ).fetchall()

        return self._with_retry(_query)

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

    def fetch_broadcasts_since(
        self, since_t: int, t_now: int
    ) -> List[sqlite3.Row]:
        def _query(conn: sqlite3.Connection) -> List[sqlite3.Row]:
            return conn.execute(
                """
                SELECT message_id, sender_id, recipient_id, group_id,
                       channel_type, content, place_id, attempted_at, delivered
                FROM direct_message
                WHERE channel_type='RDC' AND sender_id=-1
                  AND attempted_at > ? AND attempted_at <= ?
                ORDER BY attempted_at, message_id
                """,
                (since_t, t_now),
            ).fetchall()

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


def make_readonly_db(sim_dir: Path | None = None) -> ReadOnlyWorldDB:
    return ReadOnlyWorldDB(get_world_db_path(sim_dir))
