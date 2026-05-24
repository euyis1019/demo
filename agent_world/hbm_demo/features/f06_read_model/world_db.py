"""F06 Flask-side read-only SQLite world accessor."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, List, Optional, Set, Tuple

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
    ) -> List[Tuple[int, int, int, str]]:
        def _query(conn: sqlite3.Connection) -> List[Tuple[int, int, int, str]]:
            rows = conn.execute(
                """
                SELECT MIN(message_id) AS message_id, sender_id,
                       attempted_at, content
                FROM direct_message
                WHERE channel_type='F2F' AND place_id=?
                  AND attempted_at >= ? AND attempted_at <= ?
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
                       channel_type, content, place_id, attempted_at
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


def make_readonly_db(sim_dir: Path | None = None) -> ReadOnlyWorldDB:
    return ReadOnlyWorldDB(get_world_db_path(sim_dir))
