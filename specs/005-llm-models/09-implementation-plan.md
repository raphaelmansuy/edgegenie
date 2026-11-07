# 09 · Implementation plan

[Index](README.md) · prev: [08 Lenses](08-lenses.md) · next: [10 Edge cases](10-edge-cases-testing.md)

Seven phases. Each ends in a state that is **shippable and verifiable on its own**, and none depends
on a later phase to be useful. Ordering principle: **prove the two hard properties before building
the surface.** The two hard properties are "one process can hold several providers" and "a key can be
stored and used without ever leaving the server". A beautiful picker over a broken key path is the
failure this order prevents.

```
P0 probe ──► P1 store + degradation ──► P2 discovery ──► P3 vault
                                                            │
                                            P4 resolver ────┘
                                                 │
                                       P5 switching + provenance
                                                 │
                                       P6 the picker + settings
                                                 │
                                       P7 delete the old path
```

---

## Effort and what each phase buys

| Phase | Effort | Buys | Reversible? |
|---|---|---|---|
| P0 | ½ day | a decision that cannot be made from documentation | yes, nothing ships |
| P1 | 3 days | persistence with a defined absence | yes, behind a flag |
| P2 | 2 days | every served model is known, with provenance | yes |
| P3 | 4 days | a key that can be stored and used safely | yes, keys are additive |
| P4 | 3 days | one resolution path, limits clamped, adapters proven | no — this is the cut-over |
| P5 | 3 days | live switching and immutable provenance | partly |
| P6 | 5 days | the surfaces | yes |
| P7 | 1 day | one way to answer "which models exist" | no, and that is the point |

Total **≈ 3.5 weeks** for one full-stack engineer with the specs in hand, plus the probes' findings
feeding back into [04](04-providers.md) and [11](11-decisions-risks.md).

---

## P0 · The multi-provider probe

**Goal:** know whether one agent process can serve two providers, before designing around the answer.
Half a day. This is U5 in [01](01-current-state.md#what-we-have-not-verified), and it is the one
finding that can invalidate the architecture.

| # | Probe | Method | Exit criterion |
|---|---|---|---|
| a | Two provider blocks in one config | write `opencode.json` with `vertex` **and** `dbx` (the shape in [`experiments/steps/06_opencode_vertex_gemini.sh`](../../experiments/steps/06_opencode_vertex_gemini.sh) already does this), start `opencode acp`, `session/new`, read `configOptions` | the model list contains values from **both** providers |
| b | Switch across providers over ACP | `session/set_config_option {configId:"model", value:"<other provider id>"}` then one prompt | a completed turn with the other provider's answer, and usage tokens |
| c | One process, second env var | spawn with `LLM_PROVIDER_KEY` in `env` and confirm the child sees it, then confirm a config change is **not** picked up without a restart | the env is visible at spawn and a config rewrite alone does not switch provider |
| d | Vertex with a service-account JSON | mint an access token from the JSON in Python, call the OpenAI-compatible Vertex endpoint once | HTTP 200 and a completion |
| e | Vertex native adapter with the same key | `@ai-sdk/google-vertex` with `apiKey` = the minted token | a tool-calling round trip succeeds (this decides shim vs native) |

**Exit criteria feed three documents:**

| Result | Goes to |
|---|---|
| a/b fail | [11 D8](11-decisions-risks.md): one process per provider; [03 §Switching](03-architecture.md#switching-a-model) amended |
| c fails (env not visible) | the whole injection design is wrong: stop and report |
| d fails | Vertex is unreachable without ADC inside the app: the feature is scoped out with a reason |
| e fails | the shim ships; [04 §Gemini](04-providers.md#gemini-on-vertex-ai) keeps its fallback and adds the cost |

> **Do not start P1 before this returns.** A store for a design that cannot work is a week lost.

---

## P1 · The registry store, and degradation

**Goal:** a catalogue that survives a deploy, and an app that still works when it does not.

| Work | File | Acceptance |
|---|---|---|
| `RegistryStore` port | `api/ports/__init__.py` (extend) | protocol: providers, models, upsert, health, turn pin |
| `MemoryRegistryStore` | `api/adapters/llm/store/memory.py` | all tests and demo mode use it; no Postgres needed |
| `SeedRegistryStore` | `api/adapters/llm/store/seed.py` | loads `seed/llm_models.yaml`; validates every row against the domain |
| `PgRegistryStore` | `api/adapters/llm/store/pg.py` | plain SQL via `psycopg`; the six queries in [05](05-data-model-lakebase.md) |
| migrations | `api/adapters/llm/store/migrations/*.sql` | forward-only, idempotent, `schema_version` stamped |
| boot selection | `api/main.py` | `LLM_DATABASE_URL` absent → seed; unreachable → degraded; ahead → refuse to start |
| `cryptography` pinned | `requirements.txt` **and** `pyproject.toml` | `tests/test_packaging.py` passes (it walks imports) |
| seed file | `apps/coding-agent/seed/llm_models.yaml` | the five measured Databricks models with `evidence: measured` and the source |

**Test that matters:** start the app with `LLM_DATABASE_URL` pointing at a closed port; `GET /api/models`
returns **200** with `source: "degraded"` and the Databricks models present. That single test is C-5.

**Risk:** 001 R-09 calls the Lakebase app-provisioning flow fragile. Mitigation: P1 ships with the
seed store as a first-class citizen, so a workspace where Lakebase cannot be attached loses only the
key store, not the model list. Recorded in [11 R-4](11-decisions-risks.md#risks).

---

## P2 · Discovery, with provenance

**Goal:** every model the workspace serves is known, and every fact about it says where it came from.

| Work | File | Acceptance |
|---|---|---|
| extend `ServingBrowser` into a discovery adapter | `api/adapters/llm/discovery/databricks.py` | returns `ModelSpec`s, not just names; keeps the `None`-means-do-not-filter rule |
| merge with precedence | `api/services/model_service.py` | the field-level table in [03](03-architecture.md#catalogue-assembly) is a test |
| discovery run record | `llm_discovery_run` | one row per pass, with outcome and count |
| health classification table | `api/domain/llm/errors.py` | the five captured strings in [04](04-providers.md#health-and-classification) classify correctly |
| scheduled refresh | `api/main.py` lifespan task | every `LLM_DISCOVERY_SECONDS` (default 300), not per request (C-6) |
| `GET /api/models` shape | `api/routers/api.py` | `{available, default, source, updatedAt}`; provider, capability, limits, evidence, state per model |

**What the probe in P0-b adds here:** whether the serving-endpoints response carries foundation model
names or limits. If it does, those become `evidence: documented`/`measured` automatically; if not, the
seed file stays the source and the adapter stores only existence and readiness.

**Test that matters:** a discovery failure (403) changes **nothing** about the catalogue except
`source` and `updatedAt`. A model that disappears from discovery becomes `not_served` and is **not**
deleted — FR-14.

---

## P3 · The credential vault

**Goal:** a key can be stored, listed, tested, rotated and revoked, and never comes back.

| Work | File | Acceptance |
|---|---|---|
| `CredentialVault` port | `api/ports/__init__.py` | put, open, revoke, list — no method returns plaintext except `open` |
| envelope implementation | `api/adapters/llm/vault/pg.py` | AES-256-GCM; DEK per row; KEK from a scope or `LLM_KEK` |
| `KekProvider` | `api/adapters/llm/vault/kek.py` | `ScopeKek` and `EnvKek`; the mode is logged once at boot |
| local vault | `api/adapters/llm/vault/local.py` | env-only, for development: keys come from `LLM_<PROVIDER>_KEY` |
| secret validators | `api/domain/llm/credentials.py` | one validator per kind: api key, service-account JSON, access token |
| Vertex token minting | `api/adapters/llm/providers/vertex.py` | JWT assertion → access token, cached to `expiry − 60 s` |
| routes | `api/routers/llm.py` | `PUT/GET/DELETE /api/llm/credentials`, `POST /api/llm/credentials/test` |
| redaction | `api/domain/redact.py` (extract from the existing rules) | the seven patterns in [06](06-security-credentials.md#redaction-at-the-source) |

**Tests that matter, in order of severity:**

1. A planted key appears in **no** response body, log line, event payload or agent config file (S1–S5).
2. `open()` on a revoked row raises, and never decrypts (S7).
3. A cross-user `open()` raises and is logged (E-5 / TH-10).
4. A database dump decrypted without the KEK yields nothing (S10).
5. `Test connection` fails **before** save for a malformed service-account JSON (K3).

**Risk:** the `EnvKek` mode reaching production. Mitigation: `put()` refuses when `APP_ENV=production`
and no scope-based KEK is available, and the settings screen shows the mode. Recorded in
[11 R-5](11-decisions-risks.md#risks).

---

## P4 · The resolver, and the adapter cut-over

**Goal:** one path from an id to everything a child needs. This is the phase that removes the old
path, so it is the only one that cannot be partially rolled back.

| Work | File | Acceptance |
|---|---|---|
| domain value objects | `api/domain/llm/model.py` | `ModelId`, `ProviderKind`, `WireProtocol`, `ModelSpec`, `ResolvedModel`, capability |
| alias map | `api/domain/llm/model.py` | every legacy id in [04](04-providers.md#ids-and-the-alias-map) resolves; injectivity property test |
| limit clamp | `api/domain/llm/limits.py` | total, pure, and total: any `(context, output)` input yields a valid pair |
| policy | `api/domain/llm/policy.py` | grant precedence as specified; deny always wins |
| four adapters | `api/adapters/llm/providers/*.py` | descriptor is pure; a shared conformance test runs on all four |
| resolver | `api/services/model_resolver.py` | the seven steps; returns `ResolvedModel` or a typed error |
| config writer | `api/adapters/acp/agent_config.py` | golden-file test: the Databricks output is **byte-identical** to today's |
| delete | `api/adapters/acp/agent_config.py` | `KNOWN_ENDPOINTS` and the string surgery removed; `ENDPOINT_LIMITS` moves to the seed file |
| `config_for` shim | `api/adapters/acp/agent_config.py` | one definition, delegating to the resolver, kept only until P7 |

**Test that matters:** the golden file. If the Databricks config changes by one byte, the exam results
in this repository stop being comparable, and that is the regression this phase cannot afford.

**DRY note:** `ENDPOINT_LIMITS` is not duplicated into the seed file while the dict exists — the dict is
**moved**, and the test that guarded it
([`tests/test_genie_features.py:512-519`](../../apps/coding-agent/tests/test_genie_features.py)) is
rewritten to iterate the registry (C-4) rather than deleted.

---

## P5 · Cross-provider switching and immutable provenance

**Goal:** a switch works, and a turn's model cannot be rewritten.

| Work | File | Acceptance |
|---|---|---|
| resolve the ACP-side id | `api/services/orchestrator.py` | the id sent to `set_config_option` is the one the agent advertises, not the app's |
| restart path | `api/services/orchestrator.py` | cross-provider switch drains the turn, closes the child, starts a new one, keeps the session |
| credential in env | `api/services/orchestrator.py` | `SessionSpec.env` carries exactly one provider key (S6) |
| turn pin | `api/services/orchestrator.py` + store | insert-once before the prompt; no update grant |
| delete the dead write | `api/services/orchestrator.py` | the `config_for(...).write()` at `:275-278` and its silent `except OSError` are gone |
| measure the restart | P5 harness | p50 and p95 of a cross-provider switch, recorded in [11](11-decisions-risks.md) |

**Test that matters:** start a turn, switch the model mid-turn, assert the turn's pin is unchanged and
the **next** turn's pin is the new model. That is FR-9 and FR-10 together.

**Fallback, if the restart exceeds 3 s:** the endpoint returns `{requiresNewSession: true}` and the UI
offers it as an action. Still honest, still no silent substitution.

---

## P6 · The picker and the settings surface

**Goal:** the surfaces in [07](07-ux-ui-wireframes.md).

| Work | File | Acceptance |
|---|---|---|
| pure domain | `web/src/domain/models.ts` | grouping, rank reuse, label, order — unit-tested, no React |
| picker | `web/src/components/ModelPicker.tsx` | combobox/listbox, glyphs, groups, `⌘⏎`, `esc`, focus return |
| inspector facts | `web/src/components/ModelFacts.tsx` | per-turn breakdown with the switch point |
| settings route | `web/src/components/ProviderSettings.tsx` | one row per provider; Test/Rotate/Revoke; no reveal |
| add-key form | `web/src/components/AddKey.tsx` | per-field validation, masking, Test-before-Save |
| delete the duplicates | `web/src/App.tsx`, `web/src/components/Chrome.tsx` | the two `<select>` elements are gone; one picker remains |
| palette command | `web/src/domain/commands.ts` | `model` opens the picker from anywhere |

**Acceptance:** `npm run test`, `npm run audit` (a11y, overflow, shell, CLS) and a new
`scripts/model-picker.e2e.mjs` that drives the popover with the keyboard only.

---

## P7 · Delete the old path

**Goal:** one way to answer "which models exist".

| Work | Acceptance |
|---|---|
| remove `config_for` and every call site | `rg "config_for" apps/coding-agent` → 0 |
| remove `StaticModelCatalog` | `rg "StaticModelCatalog"` → 0, and its tests are ported to `SeedCatalogue` |
| remove the `LLM_ALLOW_EXTERNAL` dead branches, if the flag stays | one code path, one flag |
| update [01](01-current-state.md) with the new line numbers | the audit reflects the code, not the plan |
| re-run the exam suite on two models | the numbers still hold; a regression here means the config changed |

`rg … → 0` is the acceptance, because a "removed" function with one caller is not removed.

---

## Enforcement, not convention

Four checks run in CI. Each one stops a specific regression that a code review reliably misses.

| Check | Command | What it stops |
|---|---|---|
| **Layer rule** (C-2) | `rg` for a vendor equality in `api/domain` and `api/services` returns nothing (the pattern is in [10](10-edge-cases-testing.md#the-six-ci-gates)) | a vendor branch creeping into the core |
| **One resolver** (C-3) | `rg -c "def config_for" api` ≤ 1 and `rg "KNOWN_ENDPOINTS" api` empty | the old string surgery surviving beside the new path |
| **Limits** (C-4) | `pytest -k limits` over the registry | an offered model asking for more than it allows |
| **Diagrams** | `node scripts/verify-spec-ascii.mjs ../../../specs/005-llm-models` (from `apps/coding-agent/web`) | an ASCII box drifting, which is invisible in a diff |
| **Links** | `node scripts/verify-spec-links.mjs specs/005-llm-models` | a cross-reference to a section that was renamed |
| **Mermaid** | `node scripts/verify-spec-mermaid.mjs specs/005-llm-models` | a diagram that renders as a red error box |

The last three already exist for spec 003
([`web/scripts/verify-spec-links.mjs`](../../apps/coding-agent/web/scripts/verify-spec-links.mjs),
[`verify-spec-mermaid.mjs`](../../apps/coding-agent/web/scripts/verify-spec-mermaid.mjs)); this spec
adds the ASCII one and wires all three into `package.json`:

```json
"verify:spec-005": "node scripts/verify-spec-links.mjs ../../../specs/005-llm-models && node scripts/verify-spec-ascii.mjs ../../../specs/005-llm-models"
```

---

## Test plan, by layer

| Layer | Kind | What it covers | Where |
|---|---|---|---|
| domain | unit, property | id canonicalisation, alias injectivity, clamp, policy precedence | `tests/test_llm_domain.py` |
| adapters | unit with a fake HTTP layer | four descriptors, secret validation, token minting, error classification | `tests/test_llm_providers.py` |
| store | integration (skipped without a DSN) | migrations idempotent, upsert, insert-once pin, retention query | `tests/test_llm_store.py` |
| vault | unit + integration | round trip, tamper detection, revoked, cross-user, no-KEK | `tests/test_llm_vault.py` |
| service | unit | catalogue precedence, degradation, resolution pipeline | `tests/test_llm_service.py` |
| API | contract | every route's status codes and that no response contains a secret | `tests/test_llm_api.py` |
| front end | unit | grouping, order, rank, copy exhaustiveness | `web/src/domain/models.test.ts` |
| front end | component | keyboard model, focus return, announcement | `web/src/components/ModelPicker.test.tsx` |
| end to end | Playwright | picker open → select → switch → transcript shows the pin | `web/scripts/model-picker.e2e.mjs` |
| end to end | Python | a real turn against a fake provider that asserts the received headers | `tests/test_llm_e2e.py` |

**The one end-to-end test that matters most:** a fake provider records the `Authorization` header it
receives; the test asserts it equals the key that was stored for **that user**, and that the other
user's key never appears in any request. That single test covers FR-7, FR-8, TH-10 and S6 at once.

---

## What could still go wrong with this plan

| Risk | Signal | Response |
|---|---|---|
| P0 invalidates the single-process design | probe b | one process per provider; the plan adds a week, the architecture survives |
| Lakebase cannot be attached | P1 test | seed store only; keys move to a secret scope per user, with a lower key limit |
| The golden-file test fails on day one | P4 | stop and diff: the config must not change for the Databricks path |
| The restart is slow | P5 measurement | "start a session with this model" instead of live switching |
| A provider's API changes under us | P2 probes | the health classifier names it, and the adapter changes in one file (A2) |
| The scope grows into routing | review | [11 D7](11-decisions-risks.md) is the written boundary |

---

## Definition of done

1. `GET /api/models` lists every served model plus every configured external model, with state,
   limits and evidence.
2. A user adds a Vertex service-account JSON key, tests it, and runs a turn on
   `google_vertex/google/gemini-3.8-flash` — and the key appears in no response, log or file.
3. A second user cannot use that key, and is told why.
4. A switch mid-session leaves the earlier turns' pins untouched and applies to the next turn.
5. With the database stopped, the app boots and Databricks models work.
6. `rg "config_for|KNOWN_ENDPOINTS|StaticModelCatalog"` returns only the deliberate compatibility shim
   and its single test.
7. All six CI checks in §Enforcement pass, including the diagram and link verifiers.
