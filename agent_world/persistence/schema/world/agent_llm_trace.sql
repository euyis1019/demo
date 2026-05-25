-- world.db: agent_llm_trace (F15 — LLM prompt audit trail)
CREATE TABLE IF NOT EXISTS agent_llm_trace (
    trace_id           TEXT PRIMARY KEY,
    agent_id           INTEGER NOT NULL,
    at_tick            INTEGER NOT NULL,
    phase              TEXT,
    player_turn        INTEGER,
    model              TEXT,
    temperature        REAL,
    max_tokens         INTEGER,
    system_prompt      TEXT NOT NULL,
    user_prompt        TEXT NOT NULL,
    tool_calls_json    TEXT,
    assistant_content  TEXT,
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_llm_trace_agent_tick
    ON agent_llm_trace(agent_id, at_tick);
