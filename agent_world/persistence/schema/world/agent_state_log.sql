-- world.db: agent_state_log (F12 — inner OS / current_state audit trail)
CREATE TABLE IF NOT EXISTS agent_state_log (
    log_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id     INTEGER NOT NULL,
    content      TEXT NOT NULL,
    at_tick      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_state_log_agent_tick
    ON agent_state_log(agent_id, at_tick);
