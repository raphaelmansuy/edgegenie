-- SQL assets and execution intents have their own owner-scoped, encrypted journal.
CREATE TABLE IF NOT EXISTS agent.sql_item (
    scope text NOT NULL,
    kind text NOT NULL,
    id text NOT NULL,
    created double precision NOT NULL,
    version bigint NOT NULL CHECK (version > 0),
    state text NOT NULL,
    source_ref text NOT NULL DEFAULT '',
    body bytea NOT NULL,
    PRIMARY KEY (scope, kind, id)
);
CREATE INDEX IF NOT EXISTS sql_recent ON agent.sql_item (scope, kind, created DESC, id DESC);
CREATE INDEX IF NOT EXISTS sql_active ON agent.sql_item (kind, state, scope, source_ref);
CREATE TABLE IF NOT EXISTS agent.sql_operation (
    scope text NOT NULL,
    key text NOT NULL,
    fingerprint text NOT NULL,
    id text NOT NULL,
    kind text NOT NULL,
    created double precision NOT NULL,
    PRIMARY KEY (scope, key)
);
