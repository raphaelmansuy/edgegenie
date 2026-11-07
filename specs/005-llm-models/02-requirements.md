# 02 · Requirements

[Index](README.md) · prev: [01 Current state](01-current-state.md) · next: [03 Architecture](03-architecture.md)

Every requirement has an id, a testable acceptance, and a link to the case that proves it. An id
marked **C** constrains the design; a requirement without an acceptance criterion is not a
requirement and has been removed.

---

## Functional

| ID | Requirement | Acceptance (testable) | Proved by |
|---|---|---|---|
| **FR-1** | Every chat model the workspace serves is offered without a code change | A model enabled in the workspace appears in `GET /api/models` within one discovery TTL (≤300 s) with no deploy | E-2 |
| **FR-2** | A provider can be added by configuration alone | Adding a `llm_provider` row + a `llm_model` row makes the model selectable and usable; no Python file is edited | E-2, E-4 |
| **FR-3** | Provider kinds are `databricks`, `openai`, `anthropic`, `google_vertex` | Each kind has an adapter; an unknown kind is rejected at validation, not at call time | E-4 |
| **FR-4** | A model id is canonical and stable | `provider/model` form; alias map resolves every id the app has ever stored to exactly one canonical id; a property test proves injectivity | E-1 |
| **FR-5** | Limits are data with provenance | Each model has `context_window`, `max_output`, `evidence` ∈ {measured, documented, default}; an unknown limit is marked, never guessed silently | E-3 |
| **FR-6** | The request never exceeds the believed cap | For every offered model, the resolved `output` ≤ `max_output`; a model whose cap cannot be established is offered as **unverified** and clamped to the conservative default | E-3 |
| **FR-7** | Per-user credentials are supported | A user can store a key for a provider; only that user's sessions can use it; a second user's request for that model is refused with a clear reason | E-5, E-7 |
| **FR-8** | Per-workspace credentials are supported | An app-level key is usable by every authorised user and is never revealed to any of them | E-5 |
| **FR-9** | A model switch takes effect on the live session | `POST /sessions/{id}/model` changes the model for the **next** turn; the current turn is never retargeted | E-6 |
| **FR-10** | A turn records the model actually used | The turn event carries model id, provider, resolved endpoint and wire protocol; the transcript shows it; a later switch does not rewrite history | E-6 |
| **FR-11** | Health is visible before use | Each model exposes `healthy`, `degraded`, `unauthorised`, `unknown` with a timestamp and, when failing, the provider's own message | E-9 |
| **FR-12** | Grants are per user and per model | A model may be restricted to a list of users or a group; the picker hides what the user may not use and the server refuses it independently | E-7 |
| **FR-13** | Deleting a provider or model cannot orphan a session | Soft-delete only; a session pinned to a removed model still reports its pin and can be resumed on an explicit replacement | E-10 |
| **FR-14** | Discovery is non-destructive | A discovery failure never removes a model; it marks it `unknown` and keeps the last known state | E-8 |
| **FR-15** | The picker is keyboard-complete and grouped | Provider groups, search over id and display name, arrow/Enter/Escape, `aria-activedescendant`, focus returns to the trigger | E-11 |

---

## Requirements that constrain the design

**C-1 · No secret leaves the server.** No API returns a credential, its ciphertext, or its full
plaintext. The maximum disclosed is `last4` plus a fingerprint. Test: response-scan test over every
`/api/llm/*` route for the plaintext and the ciphertext of a planted key. → [06](06-security-credentials.md)

**C-2 · The domain never branches on a vendor.** No `if provider ==` outside an adapter package. Test:
an import-and-grep test in CI (`rg "== '(openai|anthropic|google_vertex|databricks)'" api/domain` must
match nothing). → Axiom A2, [03](03-architecture.md#ports-and-adapters)

**C-3 · One resolution path.** `config_for` may exist as a thin wrapper for compatibility, but every
call must go through the resolver. Test: a grep test proving `KNOWN_ENDPOINTS` no longer exists and
`config_for` has at most one definition and is called only from the resolver's façade.

**C-4 · Every offered model can be called.** The guard test at
`tests/test_genie_features.py:512-519` is generalised: iterate the registry (not `Settings`), assert
each model resolves to a non-empty endpoint, a protocol, a credential **reference**, and an output cap
that is either proven or explicitly flagged. → [10](10-edge-cases-testing.md#model-identity-and-limits)

**C-5 · The app boots without a database.** If Lakebase is unreachable, the catalogue is built from
the seed file, credential-backed models are reported unavailable with a named reason, and Databricks
models continue to work. Test: start with an unreachable DSN and assert `/api/models` is 200. →
[10 E-14](10-edge-cases-testing.md#storage-and-degradation)

**C-6 · No per-request discovery.** Discovery is cached and refreshed on a schedule or explicitly.
Test: 100 `GET /api/models` produce ≤1 upstream discovery call.

**C-7 · The fence is unchanged.** Adding a provider must not add a write path to the workspace, and
the tool server's scope and token handling are untouched. Test: the existing scope tests still pass
and no new tool is registered.

**C-8 · A turn's provenance is immutable.** Writing a turn's model record twice is a no-op; a switch
creates a new record. Test: append-only assertion at the store seam.

---

## Non-functional

| ID | Requirement | Target | Proved by |
|---|---|---|---|
| **NFR-1** | `GET /api/models` p95 latency | ≤ 120 ms cached, ≤ 800 ms cold with discovery | E-12 |
| **NFR-2** | Picker interaction | opens in ≤ 50 ms with a preloaded catalogue; no layout shift (CLS ≤ 0.02) | `scripts/cls-audit.mjs`, E-11 |
| **NFR-3** | Credential decryption | ≤ 5 ms per resolution; cache only within a turn | E-5 |
| **NFR-4** | Key material at rest | AES-256-GCM envelope; data key wrapped by a KEK that is never in the database | E-5 |
| **NFR-5** | No secret in any log, event, or export | 0 occurrences, scanned by regex including `dapi`, `sk-`, `AIza`, `BEGIN PRIVATE KEY` | E-13 |
| **NFR-6** | Accessibility | WCAG 2.2 AA: the picker is a `combobox`+`listbox` with visible focus, ≥ 24 px targets, works at 200 % zoom | E-11 |
| **NFR-7** | Backward compatibility | Every id stored by the current app resolves; no session fails to load after the upgrade | E-1 |
| **NFR-8** | Observability | Each resolution emits one structured line: model id, provider, protocol, credential source, outcome — never the secret | E-12 |

---

## Requirements about failure, stated as behaviour

These are requirements because each was a real failure in this repository or in the probe record.

| ID | When | The app must |
|---|---|---|
| **FR-16** | The provider's key is wrong or expired | classify `unauthorised`, keep the model visible and marked, and quote the provider's message — never retry silently |
| **FR-17** | The provider returns 429 | retry with backoff at most twice, surface "the model is busy, retrying", and keep the turn cancellable |
| **FR-18** | The endpoint exists but the model id is unknown to it | refuse at selection time when discovery said so; otherwise fail the turn with the provider's 404 text and mark the model `degraded` |
| **FR-19** | The credential is missing for a model that needs one | offer the model with an explicit "add a key" action; do not offer it as selectable and then fail |
| **FR-20** | A model is disabled in the workspace (`MODEL is not enabled`) | show it in the picker under a "not enabled here" group with the platform's own words and what to ask an admin for |

FR-20 is the honest treatment of the constraint measured in
[the original spec §3.2](../../docs/genie-code-replacement-spec.md): hiding the model teaches the user
nothing; naming the gate gives them the action.

---

## What is explicitly **not** a requirement

| Not required | Why |
|---|---|
| Automatic fallback to another model on failure | A silent substitution makes the transcript lie. A user-visible "retry with X" action is the alternative ([11 D6](11-decisions-risks.md)). |
| Cost prediction | The registry stores price data when available, but predicting a tool-loop turn is unreliable; the app shows the *observed* cost after the fact. |
| Central key management beyond this app | A workspace-level secret backend is the platform's job. This spec consumes it if present ([06](06-security-credentials.md#where-a-key-could-live-and-why-we-chose-one-place)). |
| Per-turn model routing | [11 D7](11-decisions-risks.md). |
| Models without tool calling | The product is a coding agent; a model that cannot call tools cannot do the job. Such models are catalogued but marked non-selectable with that reason. |

---

## The requirements that will be argued about

Two requirements are the ones where a reviewer reliably disagrees, so the argument is stated here
rather than discovered in review.

**FR-7 (per-user keys) vs. C-1 (no secret leaves the server).**
These are compatible but they cost something: a per-user key means the app becomes a secret store,
with rotation, deletion and audit obligations that a workspace token never imposed. The alternative —
only app-level keys — is simpler and is what [11 D3](11-decisions-risks.md) calls the fallback if
envelope encryption cannot get a KEK. The requirement stays because the user's own key is the only way
to use a provider account the workspace does not own, which is exactly the gap
[00 §Why](00-why-first-principles.md) describes.

**FR-20 (show not-enabled models) vs. NFR-2 (a short list).**
Showing unusable entries lengthens the picker. The mitigation is grouping and default-collapse, not
deletion: the "not enabled here" group is closed by default, appears only when the user searches or
expands, and carries the admin action. A user who never looks never sees it; a user who wonders why
Gemini is missing gets an answer instead of silence.

---

## Traceability

| Requirement group | Architecture | Data | UX | Tests |
|---|---|---|---|---|
| FR-1, FR-2, FR-3, FR-14 | [03 §Catalogue assembly](03-architecture.md#catalogue-assembly) | [05 §Tables](05-data-model-lakebase.md#tables) | — | E-2, E-8 |
| FR-4, FR-5, FR-6 | [03 §Resolution](03-architecture.md#the-resolution-pipeline) | [05 §Limit evidence](05-data-model-lakebase.md#limit-evidence) | — | E-1, E-3 |
| FR-7, FR-8, FR-12 | [06](06-security-credentials.md) | [05 §Credentials](05-data-model-lakebase.md#llmcredential-ciphertext-only-and-the-shape-is-the-security-control) | [07 §Settings](07-ux-ui-wireframes.md#screen-5-providers-and-keys) | E-5, E-7 |
| FR-9, FR-10, C-8 | [03 §Switching](03-architecture.md#switching-a-model) | [05 §Turns](05-data-model-lakebase.md#llmturnmodel-the-audit-record) | [07 §Inspector](07-ux-ui-wireframes.md#screen-4-the-inspector-i-and-the-only-model-facts-surface-below-1100-px) | E-6 |
| FR-11, FR-16..20 | [04 §Health](04-providers.md#health-and-classification) | [05 §Health](05-data-model-lakebase.md#llmhealth-append-only-observations) | [07 §States](07-ux-ui-wireframes.md#picker-states) | E-9 |
| FR-15, NFR-2, NFR-6 | [03 §Front end](03-architecture.md#front-end) | — | [07](07-ux-ui-wireframes.md) | E-11 |
| C-1, NFR-4, NFR-5 | [06](06-security-credentials.md) | [05](05-data-model-lakebase.md) | [07 §Key entry](07-ux-ui-wireframes.md#screen-5-providers-and-keys) | E-5, E-13 |
| C-5, NFR-1 | [03 §Degradation](03-architecture.md#degradation-is-a-first-class-state) | — | [07 §Degraded](07-ux-ui-wireframes.md#picker-states) | E-14 |
| C-7 | [03 §What is untouched](03-architecture.md#what-this-spec-does-not-touch) | — | — | E-15 |
