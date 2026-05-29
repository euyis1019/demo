"""F06 read-only queries — direct_message (F2F / RDC / GRP) + existence checks.

Mixin for ``ReadOnlyWorldDB``; relies on ``self._with_retry`` from the base.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


class MessageQueriesMixin:
    """direct_message reads: F2F history, RDC, GRP, broadcasts, existence checks."""

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

    def fetch_f2f_from_sender_at(
        self,
        place_id: str,
        sender_id: int,
        t_now: int,
        since_t: int,
        *,
        limit: int = 500,
        exclusive_since: bool = False,
    ) -> List[Tuple[int, int, int, str]]:
        """F2F history for one sender — avoids player/agent mix crowding LIMIT windows."""

        def _query(conn: sqlite3.Connection) -> List[Tuple[int, int, int, str]]:
            since_op = ">" if exclusive_since else ">="
            rows = conn.execute(
                f"""
                SELECT MIN(message_id) AS message_id, sender_id,
                       attempted_at, content
                FROM direct_message
                WHERE channel_type='F2F' AND place_id=? AND sender_id=?
                  AND attempted_at {since_op} ? AND attempted_at <= ?
                GROUP BY sender_id, attempted_at, content
                ORDER BY attempted_at, message_id
                LIMIT ?
                """,
                (place_id, int(sender_id), since_t, t_now, limit),
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

    def has_npc_f2f_after(
        self,
        place_id: str,
        start_tick: int,
        t_now: int,
        *,
        npc_sender_ids: Optional[Iterable[int]] = None,
    ) -> bool:
        """F2F from NPC agents only (excludes virtual player sender_id=0)."""

        def _query(conn: sqlite3.Connection) -> bool:
            if npc_sender_ids is not None:
                ids = tuple(int(x) for x in npc_sender_ids)
                if not ids:
                    return False
                placeholders = ",".join("?" * len(ids))
                row = conn.execute(
                    f"""
                    SELECT 1 FROM direct_message
                    WHERE channel_type='F2F' AND place_id=?
                      AND attempted_at > ? AND attempted_at <= ?
                      AND sender_id IN ({placeholders})
                      AND sender_id != 0
                    LIMIT 1
                    """,
                    (place_id, start_tick, t_now, *ids),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT 1 FROM direct_message
                    WHERE channel_type='F2F' AND place_id=?
                      AND attempted_at > ? AND attempted_at <= ?
                      AND sender_id IS NOT NULL AND sender_id != 0
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
                exclusive_since=False,
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
