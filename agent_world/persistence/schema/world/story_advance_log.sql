-- Story advance signals from LLM story_advance tool (dev_logs/30 §4.4.5 · dev_logs/31 Phase 5)
CREATE TABLE IF NOT EXISTS story_advance_log (
    log_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id   INTEGER NOT NULL,
    signal     TEXT    NOT NULL,
    at_tick    INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_story_advance_at_tick
    ON story_advance_log (at_tick);

CREATE INDEX IF NOT EXISTS idx_story_advance_signal
    ON story_advance_log (signal, at_tick);
