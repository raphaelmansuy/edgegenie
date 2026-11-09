-- Spec 010: a server-owned journal, independent of browser connections.
CREATE SCHEMA IF NOT EXISTS agent;
CREATE TABLE IF NOT EXISTS agent.session_snapshot (
    session_id text PRIMARY KEY,
    body jsonb NOT NULL,
    latest_seq bigint NOT NULL DEFAULT 0 CHECK (latest_seq >= 0)
);
CREATE TABLE IF NOT EXISTS agent.session_event (
    session_id text NOT NULL REFERENCES agent.session_snapshot(session_id),
    seq bigint NOT NULL CHECK (seq > 0),
    body jsonb NOT NULL,
    PRIMARY KEY (session_id, seq)
);
