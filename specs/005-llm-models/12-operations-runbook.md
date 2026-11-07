# 12 · Operations runbook

[Index](README.md) · prev: [11 Decisions](11-decisions-risks.md)

What to run, what to look at, and what to do at 3 a.m. Written for the person who did not build it.

---

## Configuration, in one place

All settings live in `Settings` ([`api/config.py`](../../apps/coding-agent/api/config.py)) with the
`APP_` prefix except where noted. Every one has a default that keeps the app working.

| Variable | Default | Meaning | Fails how |
|---|---|---|---|
| `LLM_DATABASE_URL` | unset | Lakebase Postgres DSN | unset → seed catalogue (C-5); unreachable → degraded |
| `LLM_KEK` | unset | base64 AES-256 KEK, development only | unset with no scope → key saving disabled, announced at boot |
| `LLM_KEK_SCOPE` / `LLM_KEK_KEY` | unset | Databricks secret scope and key name for the KEK | unreadable → falls back as above, with a `WARNING` |
| `LLM_ALLOW_EXTERNAL` | `0` | hide every external provider | `0` hides them; no error |
| `LLM_DISCOVERY_SECONDS` | `300` | discovery TTL | longer = staler list, fewer calls |
| `LLM_PROBE_SECONDS` | `900` | health probe interval per model | shorter = more tokens spent |
| `LLM_DEFAULT_MODEL` | `databricks/databricks-llama-4-maverick` | the preselected model | an id not in the catalogue → boot warning, first available model used |
| `APP_AGENT_MODE` | `fake` | `fake` / `stdio` / `http` | unchanged from today |
| `APP_TURN_IDLE_TIMEOUT` | `180` | the stall guard | unchanged from today |

**Secrets never go in `app.yaml`.** `valueFrom` may reference a scope, never a literal; the deployment
check ([`apps/coding-agent/scripts/deploy.sh`](../../apps/coding-agent/scripts/deploy.sh)) greps for
this.

---

## Health endpoints

| Route | Answers | Must not |
|---|---|---|
| `GET /api/ready` | app up, agent mode, catalogue source, model count | touch a provider (a readiness probe that calls out fails the app for a remote reason) |
| `GET /api/llm/health` | per-provider: credential present, last probe state, last error | return any secret material |
| `GET /api/models` | the catalogue, with `source` and `updatedAt` | block on discovery (serve the cache) |

```json
{
  "source": "database",
  "updatedAt": "2026-11-07T08:41:12Z",
  "providers": [
    {"id": "databricks", "state": "ok", "models": 5, "lastProbe": "2026-11-07T08:40:02Z"},
    {"id": "google_vertex", "state": "ok", "models": 3, "credential": {"scope": "user", "last4": "7f3a"}},
    {"id": "openai", "state": "unauthorised", "models": 4, "credential": {"scope": "user", "last4": "9c41"},
     "detail": "401 Unauthorized: Incorrect API key provided."}
  ]
}
```

---

## Diagnosis trees

### "A model is missing from the picker"

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E8F0FE','primaryTextColor':'#1F2937','primaryBorderColor':'#A8C0E8','lineColor':'#94A3B8'}}}%%
flowchart TB
    A["user says a model is missing"] --> B{"is the provider listed<br/>in /api/llm/health?"}
    B -->|"no"| C{"LLM_ALLOW_EXTERNAL=0 and<br/>provider is external?"}
    C -->|"yes"| C1["by policy. explain, do not change"]
    C -->|"no"| C2{"llm_provider.enabled?"}
    C2 -->|"false"| C3["enable the row"]
    C2 -->|"true"| C4["check the migration ran:<br/>SELECT * FROM llm_provider"]
    B -->|"yes"| D{"state?"}
    D -->|"not_served"| D1["discovery no longer lists it.<br/>check llm_discovery_run"]
    D -->|"not_enabled"| D2["platform gate. an account admin<br/>must enable it in the AI Gateway"]
    D -->|"unauthorised"| D3["credential. the row shows the<br/>provider's own message"]
    D -->|"degraded"| D4["look at llm_health.detail"]
    D -->|"unknown"| D5["never probed. wait for<br/>LLM_PROBE_SECONDS or probe now"]
    D -->|"available"| E{"does the user hold a grant?"}
    E -->|"no"| E1["llm_model_grant. deny wins over allow"]
    E -->|"yes"| F{"picker search<br/>filtering it out?"}
    F -->|"yes"| F1["clear the search"]
    F -->|"no"| F2["a UI bug: check the group comparator<br/>with the same fixture"]
```

### "A turn failed with a model error"

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E8F0FE','primaryTextColor':'#1F2937','primaryBorderColor':'#A8C0E8','lineColor':'#94A3B8'}}}%%
flowchart TB
    A["turn failed"] --> B{"llm_health.detail<br/>for the pinned model"}
    B -->|"401 / 403"| C["credential. rotate the key.<br/>check scope: user vs workspace"]
    B -->|"max_tokens"| D["cap. the registry lowered it<br/>automatically; retry the turn"]
    B -->|"thought_signature"| E["wire=vertex_openai for a Gemini model.<br/>set vertex_native or start the shim"]
    B -->|"ENOTFOUND / connect"| F["base_url. check the provider row<br/>and egress from the app"]
    B -->|"429"| G["rate limited. two retries already happened.<br/>wait, do not raise concurrency"]
    B -->|"stalled / sent nothing"| H["the agent, not the provider.<br/>read the stderr tail from the session log"]
    B -->|"MODEL is not enabled"| I["platform gate, not a bug"]
    B -->|"empty"| J["no probe since this model was added.<br/>probe it: POST /api/llm/models/{id}/probe"]
```

### "Keys cannot be saved"

| Symptom | Cause | Fix |
|---|---|---|
| `source: seed` in `/api/models` | `LLM_DATABASE_URL` unset or wrong | set it; restart |
| `source: degraded` | the DB is unreachable | check network and the instance state; the app keeps serving |
| `key store disabled` in settings | neither `LLM_KEK` nor a readable scope | attach a secret scope or set `LLM_KEK` (development only) |
| `Test connection` fails for a JSON key | a malformed or incomplete service account | the form names the failing field; the provider's message is in the response |
| `403` from Vertex with a project name in it | the Vertex API is not enabled for that project | enable it in the GCP project; nothing to change in the app |

---

## Routine operations

| Task | When | How |
|---|---|---|
| Refresh discovery | after enabling a model in the workspace | `POST /api/llm/discovery/refresh` (admin) or wait `LLM_DISCOVERY_SECONDS` |
| Probe one model | after adding a key | `POST /api/llm/models/{id}/probe` |
| Rotate the KEK | on a schedule, or after a suspected leak | add a new `kek_key_id`, re-wrap in a background job, keep the old key until the re-wrap finishes |
| Revoke a user's key | on offboarding | `DELETE /api/llm/credentials/{id}`; the ciphertext is purged after 30 days |
| Purge health history | nightly | `DELETE FROM llm_health WHERE at < now() - interval '7 days'` |
| Check a session's models | while debugging | `SELECT * FROM llm_turn_model WHERE session_id = $1 ORDER BY at` |
| Verify no secret in the DB | on a schedule | `SELECT * FROM llm_credential LIMIT 1` — every column is opaque except `last4`/`fingerprint` |

---

## Alerts worth having

| Alert | Condition | Why it matters |
|---|---|---|
| `llm_credential_decrypt_failed` | any `unwrap` failure | a tampered row or a wrong KEK — both are incidents |
| `llm_no_models_available` | `available` count is 0 for 5 min | the app is unusable even though it responds |
| `llm_discovery_denied` | 3 consecutive `outcome=denied` | a permission change upstream; the catalogue goes stale |
| `llm_probe_failures` | > 50 % of probes failing for a provider | an outage upstream, or an expired key |
| `llm_cap_corrections` | > 5 cap corrections in an hour | a seed value is wrong, or a proxy changed its limits |
| `llm_secret_scan_hit` | the redaction counter rises on a response path | a leak attempt or a bug in a sink |

Each is a counter with a name; none of them page on a single occurrence except the first two.

---

## What we have not verified

The honest list. Each item names what would settle it and where.

| # | Unverified | Settled by |
|---|---|---|
| U1 | What `/api/2.0/serving-endpoints` returns beyond `name`, `task`, `state.ready` | [09 P2](09-implementation-plan.md#p2-discovery-with-provenance) probe |
| U2 | Whether Lakebase can be attached to this app in this workspace | [09 P1](09-implementation-plan.md#p1-the-registry-store-and-degradation) |
| U3 | Whether a **user** token can reach the Anthropic-native gateway route | [09 P0-b](09-implementation-plan.md#p0-the-multi-provider-probe) |
| U4 | Whether a service-account JSON authenticates the Vertex OpenAI-compatible endpoint directly, or only via a minted token | [09 P0-d](09-implementation-plan.md#p0-the-multi-provider-probe) |
| U5 | Whether one `opencode` process can hold two provider blocks and switch across them over ACP | [09 P0-a/b](09-implementation-plan.md#p0-the-multi-provider-probe) |
| U6 | The measured cost of a cross-provider restart | [09 P5](09-implementation-plan.md#p5-cross-provider-switching-and-immutable-provenance) |
| U7 | Whether `@ai-sdk/google-vertex` accepts a minted access token as `apiKey` (vs ADC only) | [09 P0-e](09-implementation-plan.md#p0-the-multi-provider-probe) |
| U8 | The real per-model limits for the external providers | probed per model at onboarding; stored with `evidence: documented` until measured |

---

## Deployment checklist

1. `databricks apps update` with the new `app.yaml` env (`LLM_*`), no secrets in the file.
2. Attach the secret scope (KEK) before the first key is saved.
3. Run the migrations with the app's own boot path (they are idempotent); confirm `schema_version`.
4. `GET /api/ready` → catalogue `source: database`.
5. `GET /api/models` → the five Databricks models, states `available` or `not_enabled`.
6. Add one test key per external provider as **the deploying user**, run `Test connection`, then delete
   the key. This proves the vault, the egress and the classifier in one pass.
7. Run the five tests in [10](10-edge-cases-testing.md#the-five-tests-to-write-first) against the
   deployed app.
8. Check the six CI gates in [09](09-implementation-plan.md#enforcement-not-convention).

Step 6 is the one people skip, and it is the only step that exercises the whole path end to end with
a real provider.
