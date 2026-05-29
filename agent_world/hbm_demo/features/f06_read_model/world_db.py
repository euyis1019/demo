"""F06 Flask-side read-only SQLite world accessor.

`ReadOnlyWorldDB` is a facade composed from cohesive query mixins under
`queries/` (messages / moves / events / trace). The public class and every
method signature are unchanged — only the connection + lock-retry plumbing
lives here; the SQL reads live in their respective mixin module.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from agent_world.hbm_demo.features.f01_session.paths import get_world_db_path
from agent_world.hbm_demo.shared.errors import DatabaseReadError
from agent_world.hbm_demo.shared.settings import DB_CONNECT_TIMEOUT, DB_READ_RETRIES

from agent_world.hbm_demo.features.f06_read_model.display_names import (
    SYSTEM_SENDER_NAME,
    sender_display_name,
)
from agent_world.hbm_demo.features.f06_read_model.queries import (
    EventQueriesMixin,
    MessageQueriesMixin,
    MoveQueriesMixin,
    TraceQueriesMixin,
)

__all__ = [
    "ReadOnlyWorldDB",
    "make_readonly_db",
    "SYSTEM_SENDER_NAME",
    "sender_display_name",
]


class ReadOnlyWorldDB(
    MessageQueriesMixin,
    MoveQueriesMixin,
    EventQueriesMixin,
    TraceQueriesMixin,
):
    """Flask-side read-only SQLite accessor with lock retry.

    Query methods are provided by the mixins; this class owns only the
    read-only connection and the retry/backoff wrapper they call.
    """

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
        if not self.db_path.is_file():
            raise DatabaseReadError(
                "world.db 不存在或未初始化；请重启 run_hbm（./agent_world/hbm_demo/scripts/start_demo.sh）"
            )
        conn = sqlite3.connect(
            f"file:{self.db_path}?mode=ro",
            uri=True,
            timeout=self.timeout,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        return conn

    def _with_retry(self, fn, *, retries: int | None = None):
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
            except DatabaseReadError:
                raise
            except sqlite3.OperationalError as exc:
                last_exc = exc
                if "locked" in str(exc).lower():
                    time.sleep(delay)
                    delay = min(delay * 2, 0.5)
                    continue
                raise DatabaseReadError(str(exc)) from exc
        if last_exc is not None:
            raise DatabaseReadError(str(last_exc)) from last_exc
        raise DatabaseReadError("database read failed")


def make_readonly_db(sim_dir: Path | None = None) -> ReadOnlyWorldDB:
    return ReadOnlyWorldDB(get_world_db_path(sim_dir))
