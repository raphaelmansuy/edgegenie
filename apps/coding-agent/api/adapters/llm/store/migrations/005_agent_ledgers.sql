-- Spec 014: one encrypted row per ledger entity; state columns are indexed, not transcript-derived.
CREATE SCHEMA IF NOT EXISTS agent;
CREATE TABLE IF NOT EXISTS agent."session" (
 id text PRIMARY KEY, session_id text NOT NULL, owner text NOT NULL,
 asset_kind text NOT NULL, asset_id text NOT NULL, native_id text NOT NULL,
 state text NOT NULL, created double precision NOT NULL, version bigint NOT NULL CHECK(version>0), body bytea NOT NULL);
CREATE INDEX IF NOT EXISTS agent_session_session ON agent."session"(session_id,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_session_owner ON agent."session"(owner,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_session_state ON agent."session"(state,created,id);
CREATE TABLE IF NOT EXISTS agent."turn" (
 id text PRIMARY KEY, session_id text NOT NULL, owner text NOT NULL,
 asset_kind text NOT NULL, asset_id text NOT NULL, native_id text NOT NULL,
 state text NOT NULL, created double precision NOT NULL, version bigint NOT NULL CHECK(version>0), body bytea NOT NULL);
CREATE INDEX IF NOT EXISTS agent_turn_session ON agent."turn"(session_id,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_turn_owner ON agent."turn"(owner,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_turn_state ON agent."turn"(state,created,id);
CREATE TABLE IF NOT EXISTS agent."invocation" (
 id text PRIMARY KEY, session_id text NOT NULL, owner text NOT NULL,
 asset_kind text NOT NULL, asset_id text NOT NULL, native_id text NOT NULL,
 state text NOT NULL, created double precision NOT NULL, version bigint NOT NULL CHECK(version>0), body bytea NOT NULL);
CREATE INDEX IF NOT EXISTS agent_invocation_session ON agent."invocation"(session_id,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_invocation_owner ON agent."invocation"(owner,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_invocation_state ON agent."invocation"(state,created,id);
CREATE TABLE IF NOT EXISTS agent."change" (
 id text PRIMARY KEY, session_id text NOT NULL, owner text NOT NULL,
 asset_kind text NOT NULL, asset_id text NOT NULL, native_id text NOT NULL,
 state text NOT NULL, created double precision NOT NULL, version bigint NOT NULL CHECK(version>0), body bytea NOT NULL);
CREATE INDEX IF NOT EXISTS agent_change_session ON agent."change"(session_id,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_change_owner ON agent."change"(owner,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_change_state ON agent."change"(state,created,id);
CREATE TABLE IF NOT EXISTS agent."approval" (
 id text PRIMARY KEY, session_id text NOT NULL, owner text NOT NULL,
 asset_kind text NOT NULL, asset_id text NOT NULL, native_id text NOT NULL,
 state text NOT NULL, created double precision NOT NULL, version bigint NOT NULL CHECK(version>0), body bytea NOT NULL);
CREATE INDEX IF NOT EXISTS agent_approval_session ON agent."approval"(session_id,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_approval_owner ON agent."approval"(owner,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_approval_state ON agent."approval"(state,created,id);
CREATE TABLE IF NOT EXISTS agent."resource" (
 id text PRIMARY KEY, session_id text NOT NULL, owner text NOT NULL,
 asset_kind text NOT NULL, asset_id text NOT NULL, native_id text NOT NULL,
 state text NOT NULL, created double precision NOT NULL, version bigint NOT NULL CHECK(version>0), body bytea NOT NULL);
CREATE INDEX IF NOT EXISTS agent_resource_session ON agent."resource"(session_id,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_resource_owner ON agent."resource"(owner,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_resource_state ON agent."resource"(state,created,id);
CREATE TABLE IF NOT EXISTS agent."operation" (
 id text PRIMARY KEY, session_id text NOT NULL, owner text NOT NULL,
 asset_kind text NOT NULL, asset_id text NOT NULL, native_id text NOT NULL,
 state text NOT NULL, created double precision NOT NULL, version bigint NOT NULL CHECK(version>0), body bytea NOT NULL);
CREATE INDEX IF NOT EXISTS agent_operation_session ON agent."operation"(session_id,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_operation_owner ON agent."operation"(owner,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_operation_state ON agent."operation"(state,created,id);
CREATE TABLE IF NOT EXISTS agent."wakeup" (
 id text PRIMARY KEY, session_id text NOT NULL, owner text NOT NULL,
 asset_kind text NOT NULL, asset_id text NOT NULL, native_id text NOT NULL,
 state text NOT NULL, created double precision NOT NULL, version bigint NOT NULL CHECK(version>0), body bytea NOT NULL);
CREATE INDEX IF NOT EXISTS agent_wakeup_session ON agent."wakeup"(session_id,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_wakeup_owner ON agent."wakeup"(owner,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_wakeup_state ON agent."wakeup"(state,created,id);
CREATE TABLE IF NOT EXISTS agent."fake_asset" (
 id text PRIMARY KEY, session_id text NOT NULL, owner text NOT NULL,
 asset_kind text NOT NULL, asset_id text NOT NULL, native_id text NOT NULL,
 state text NOT NULL, created double precision NOT NULL, version bigint NOT NULL CHECK(version>0), body bytea NOT NULL);
CREATE INDEX IF NOT EXISTS agent_fake_asset_session ON agent."fake_asset"(session_id,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_fake_asset_owner ON agent."fake_asset"(owner,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_fake_asset_state ON agent."fake_asset"(state,created,id);
CREATE TABLE IF NOT EXISTS agent."fake_run" (
 id text PRIMARY KEY, session_id text NOT NULL, owner text NOT NULL,
 asset_kind text NOT NULL, asset_id text NOT NULL, native_id text NOT NULL,
 state text NOT NULL, created double precision NOT NULL, version bigint NOT NULL CHECK(version>0), body bytea NOT NULL);
CREATE INDEX IF NOT EXISTS agent_fake_run_session ON agent."fake_run"(session_id,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_fake_run_owner ON agent."fake_run"(owner,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_fake_run_state ON agent."fake_run"(state,created,id);
CREATE TABLE IF NOT EXISTS agent."previous_content" (
 id text PRIMARY KEY, session_id text NOT NULL, owner text NOT NULL,
 asset_kind text NOT NULL, asset_id text NOT NULL, native_id text NOT NULL,
 state text NOT NULL, created double precision NOT NULL, version bigint NOT NULL CHECK(version>0), body bytea NOT NULL);
CREATE INDEX IF NOT EXISTS agent_previous_content_session ON agent."previous_content"(session_id,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_previous_content_owner ON agent."previous_content"(owner,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_previous_content_state ON agent."previous_content"(state,created,id);
CREATE TABLE IF NOT EXISTS agent."evidence" (
 id text PRIMARY KEY, session_id text NOT NULL, owner text NOT NULL,
 asset_kind text NOT NULL, asset_id text NOT NULL, native_id text NOT NULL,
 state text NOT NULL, created double precision NOT NULL, version bigint NOT NULL CHECK(version>0), body bytea NOT NULL);
CREATE INDEX IF NOT EXISTS agent_evidence_session ON agent."evidence"(session_id,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_evidence_owner ON agent."evidence"(owner,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_evidence_state ON agent."evidence"(state,created,id);
CREATE TABLE IF NOT EXISTS agent."usage_pass" (
 id text PRIMARY KEY, session_id text NOT NULL, owner text NOT NULL,
 asset_kind text NOT NULL, asset_id text NOT NULL, native_id text NOT NULL,
 state text NOT NULL, created double precision NOT NULL, version bigint NOT NULL CHECK(version>0), body bytea NOT NULL);
CREATE INDEX IF NOT EXISTS agent_usage_pass_session ON agent."usage_pass"(session_id,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_usage_pass_owner ON agent."usage_pass"(owner,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_usage_pass_state ON agent."usage_pass"(state,created,id);
CREATE TABLE IF NOT EXISTS agent."preference" (
 id text PRIMARY KEY, session_id text NOT NULL, owner text NOT NULL,
 asset_kind text NOT NULL, asset_id text NOT NULL, native_id text NOT NULL,
 state text NOT NULL, created double precision NOT NULL, version bigint NOT NULL CHECK(version>0), body bytea NOT NULL);
CREATE INDEX IF NOT EXISTS agent_preference_session ON agent."preference"(session_id,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_preference_owner ON agent."preference"(owner,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_preference_state ON agent."preference"(state,created,id);
CREATE TABLE IF NOT EXISTS agent."outbox" (
 id text PRIMARY KEY, session_id text NOT NULL, owner text NOT NULL,
 asset_kind text NOT NULL, asset_id text NOT NULL, native_id text NOT NULL,
 state text NOT NULL, created double precision NOT NULL, version bigint NOT NULL CHECK(version>0), body bytea NOT NULL);
CREATE INDEX IF NOT EXISTS agent_outbox_session ON agent."outbox"(session_id,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_outbox_owner ON agent."outbox"(owner,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS agent_outbox_state ON agent."outbox"(state,created,id);
CREATE UNIQUE INDEX IF NOT EXISTS agent_operation_native ON agent.operation(asset_kind,native_id) WHERE native_id<>'';
CREATE TABLE IF NOT EXISTS agent.request(kind text NOT NULL,key text NOT NULL,id text NOT NULL,PRIMARY KEY(kind,key));

-- Compact owner/activity index: list and boot never read transcript snapshots.
CREATE TABLE IF NOT EXISTS agent.session_index (
    id text PRIMARY KEY, owner text NOT NULL, updated double precision NOT NULL, state text NOT NULL, header jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS session_index_owner ON agent.session_index(owner,state,updated DESC,id DESC);
INSERT INTO agent.session_index SELECT session_id,body->'session'->>'user_id',coalesce((body->>'lastSeen')::double precision,0),body->'session'->>'status',body->'session'
FROM agent.session_snapshot WHERE body->'session'->>'id' IS NOT NULL ON CONFLICT DO NOTHING;
