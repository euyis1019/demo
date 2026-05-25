-- world.db: agent_action_trace_link (F15 — outcome → trace association)
CREATE TABLE IF NOT EXISTS agent_action_trace_link (
    link_id    TEXT PRIMARY KEY,
    trace_id   TEXT NOT NULL,
    agent_id   INTEGER NOT NULL,
    at_tick    INTEGER NOT NULL,
    link_kind  TEXT NOT NULL,
    ref_key    TEXT NOT NULL,
    FOREIGN KEY (trace_id) REFERENCES agent_llm_trace(trace_id)
);
CREATE INDEX IF NOT EXISTS idx_action_trace_link_agent_tick
    ON agent_action_trace_link(agent_id, at_tick);
CREATE INDEX IF NOT EXISTS idx_action_trace_link_ref_key
    ON agent_action_trace_link(ref_key);
CREATE INDEX IF NOT EXISTS idx_action_trace_link_trace_id
    ON agent_action_trace_link(trace_id);
