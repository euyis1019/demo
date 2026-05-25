-- world.db: agent_location_log (F12 — movement audit trail)
CREATE TABLE IF NOT EXISTS agent_location_log (
    log_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id     INTEGER NOT NULL,
    from_place   TEXT,
    to_place     TEXT NOT NULL,
    at_tick      INTEGER NOT NULL,
    source       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_location_log_tick
    ON agent_location_log(at_tick);
