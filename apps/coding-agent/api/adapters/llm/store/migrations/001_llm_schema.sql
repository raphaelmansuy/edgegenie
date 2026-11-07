-- 001_llm_schema.sql — the `llm` schema: six tables, their invariants, the indexes that matter.
--
-- Forward-only and idempotent: a Databricks App can restart a container mid-deploy, so running this
-- twice must be a no-op (05 §Migrations, E-16).
--
-- What is deliberately absent: the KEK (a database dump must not be a key dump), any plaintext of a
-- key, and a model's current health as a column (an opinion with no timestamp is indistinguishable
-- from a fact).

CREATE SCHEMA IF NOT EXISTS llm;

CREATE TABLE IF NOT EXISTS llm.schema_version (
    version     integer      PRIMARY KEY,
    applied_at  timestamptz  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS llm.llm_provider (
    id            text        PRIMARY KEY,
    display_name  text        NOT NULL,
    kind          text        NOT NULL,
    wire_default  text        NOT NULL,
    base_url      text,
    npm_package   text        NOT NULL DEFAULT '',
    extra_options jsonb       NOT NULL DEFAULT '{}'::jsonb,
    enabled       boolean     NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    -- A plaintext http:// provider is a finding, not a preference.
    CONSTRAINT provider_https CHECK (base_url IS NULL OR base_url = '' OR base_url LIKE 'https://%'),
    -- A cheap tripwire against a secret landing in a "templated values only" column.
    CONSTRAINT provider_no_key  CHECK (extra_options::text NOT LIKE '%sk-%')
);

CREATE TABLE IF NOT EXISTS llm.llm_model (
    id             text        PRIMARY KEY,
    provider_id    text        NOT NULL REFERENCES llm.llm_provider(id) ON DELETE RESTRICT,
    endpoint       text        NOT NULL,
    display_name   text        NOT NULL,
    group_name     text        NOT NULL DEFAULT '',
    capability     text        NOT NULL DEFAULT 'tools',
    wire           text        NOT NULL,
    context_window integer     NOT NULL,
    max_output     integer     NOT NULL,
    limit_evidence text        NOT NULL DEFAULT 'default',
    limit_source   text        NOT NULL DEFAULT 'assumed',
    credential_kind text       NOT NULL DEFAULT 'none',
    enabled        boolean     NOT NULL DEFAULT true,
    selectable     boolean     NOT NULL DEFAULT true,
    state          text        NOT NULL DEFAULT 'unknown',
    last_seen_at   timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT model_limits  CHECK (context_window > 0 AND max_output > 0 AND max_output <= context_window),
    CONSTRAINT model_evidence CHECK (limit_evidence IN ('measured', 'documented', 'default')),
    CONSTRAINT model_capability CHECK (capability IN ('tools', 'tools_and_reasoning', 'chat_only')),
    CONSTRAINT model_state CHECK (state IN ('available', 'degraded', 'unauthorised', 'not_served',
                                            'not_enabled', 'unknown'))
);

CREATE INDEX IF NOT EXISTS llm_model_provider_enabled ON llm.llm_model (provider_id, enabled);

CREATE TABLE IF NOT EXISTS llm.llm_model_grant (
    model_id     text        NOT NULL REFERENCES llm.llm_model(id) ON DELETE CASCADE,
    subject      text        NOT NULL,
    subject_kind text        NOT NULL,
    allow        boolean     NOT NULL,
    granted_by   text        NOT NULL DEFAULT '',
    granted_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (model_id, subject_kind, subject),
    CONSTRAINT grant_subject_kind CHECK (subject_kind IN ('user', 'group', 'all'))
);

CREATE INDEX IF NOT EXISTS llm_grant_model_subject ON llm.llm_model_grant (model_id, subject);

CREATE TABLE IF NOT EXISTS llm.llm_credential (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_id   text        NOT NULL REFERENCES llm.llm_provider(id) ON DELETE RESTRICT,
    scope_kind    text        NOT NULL,
    scope_id      text        NOT NULL,
    kind          text        NOT NULL,
    ciphertext    bytea       NOT NULL,
    iv            bytea       NOT NULL,
    auth_tag      bytea       NOT NULL,
    wrapped_dek   bytea       NOT NULL,
    dek_iv        bytea       NOT NULL,
    kek_key_id    text        NOT NULL,
    last4         text        NOT NULL DEFAULT '',
    fingerprint   text        NOT NULL DEFAULT '',
    project_hint  text        NOT NULL DEFAULT '',
    created_at    timestamptz NOT NULL DEFAULT now(),
    last_used_at  timestamptz,
    revoked_at    timestamptz,
    -- A row that is not encrypted cannot be written, so a "temporary plaintext" path cannot exist.
    CONSTRAINT credential_encrypted CHECK (octet_length(ciphertext) > 0 AND octet_length(wrapped_dek) > 0),
    CONSTRAINT credential_scope CHECK (scope_kind IN ('user', 'workspace'))
);

-- One live key per provider per scope. Rotation is an insert + revoke, never an update, so
-- `last_used_at` history survives and an audit can say which key a turn used (E-11).
CREATE UNIQUE INDEX IF NOT EXISTS llm_credential_one_live
    ON llm.llm_credential (provider_id, scope_kind, scope_id, kind)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS llm_credential_lookup
    ON llm.llm_credential (provider_id, scope_kind, scope_id)
    WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS llm.llm_health (
    id         bigserial   PRIMARY KEY,
    model_id   text        NOT NULL REFERENCES llm.llm_model(id) ON DELETE CASCADE,
    state      text        NOT NULL,
    detail     text        NOT NULL DEFAULT '',
    latency_ms integer     NOT NULL DEFAULT 0,
    source     text        NOT NULL DEFAULT 'probe',
    at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT health_state CHECK (state IN ('available', 'degraded', 'unauthorised', 'not_served',
                                             'not_enabled', 'unknown')),
    CONSTRAINT health_source CHECK (source IN ('probe', 'turn')),
    CONSTRAINT health_detail_len CHECK (length(detail) <= 400)
);

CREATE INDEX IF NOT EXISTS llm_health_latest ON llm.llm_health (model_id, at DESC);

CREATE TABLE IF NOT EXISTS llm.llm_turn_model (
    turn_id        text        PRIMARY KEY,
    session_id     text        NOT NULL,
    model_id       text        NOT NULL,
    provider_id    text        NOT NULL,
    wire           text        NOT NULL,
    endpoint       text        NOT NULL,
    credential_ref text        NOT NULL DEFAULT '',
    limit_evidence text        NOT NULL DEFAULT 'default',
    context_window integer     NOT NULL DEFAULT 0,
    max_output     integer     NOT NULL DEFAULT 0,
    at             timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS llm_turn_model_session ON llm.llm_turn_model (session_id, at DESC);

CREATE TABLE IF NOT EXISTS llm.llm_discovery_run (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_id text        NOT NULL,
    outcome     text        NOT NULL,
    models_seen integer     NOT NULL DEFAULT 0,
    detail      text        NOT NULL DEFAULT '',
    at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT discovery_outcome CHECK (outcome IN ('ok', 'denied', 'error'))
);

INSERT INTO llm.schema_version (version) VALUES (1) ON CONFLICT DO NOTHING;
