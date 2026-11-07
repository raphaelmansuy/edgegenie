# 08 · Six lenses

[Index](README.md) · prev: [07 UX](07-ux-ui-wireframes.md) · next: [09 Implementation plan](09-implementation-plan.md)

Six specialists reviewed this specification against the code. Each section is what they objected to,
what changed as a result, and what they still do not like. **This is the document to read to find
where the design is weakest** — the objections are not softened, and the unresolved ones are named.

---

## 1 · Product owner

**What this buys that we could not do yesterday**

One sentence: *a user can pick the best model for the task without waiting for a deploy, and can use
their own provider account without leaving the fenced app.* Everything follows from that.

**Objections and what changed**

1. *"Fourteen documents for a dropdown?"*
   → Fair, and answered by scope: the dropdown is three weeks of work; the **key store** is the
   feature. A dropdown that lists models it cannot authenticate is a lie with a nice UI.
2. *"The measurements say the model dominates. So why not just hardcode Gemini?"*
   → Because the measurements also say the ranking is task-dependent: gpt-oss-120b beat Gemini on
   V5 (39 % vs 86 % is a *different task mix*, and the held-out set shows 100 % for Gemini on V1 and
   100 % for Gemini on V6 while the gateway model gave 95 %). A product that hardcodes one model will
   be wrong for some tasks and will be unable to say why.
3. *"Who is this for?"*
   → Two users, named: (a) a data engineer whose workspace only serves gateway models, who now gets
   the model that scored 100 %; (b) a platform team that wants the app to use the organisation's
   existing Vertex/OpenAI contract rather than a Databricks-managed one.
4. *"What is the success metric?"*
   → Three, in order: **models usable per user** (from 5 to "everything served, plus what you bring");
   **time to add a model** (from a deploy to a row); **turns failed for a model reason** as a share
   of all turns, which must not rise — the whole point is fewer model failures, not more.
5. *"What does it cost us?"*
   → One database dependency, one dependency for envelope encryption, and a settings surface. Bounded
   in [09 §Effort](09-implementation-plan.md#effort-and-what-each-phase-buys).

**Still unresolved:** whether external providers are enabled by default in a new deployment. Chosen:
`LLM_ALLOW_EXTERNAL=0` (off), because a pilot should opt in to egress. Owner: PO, before the pilot.

---

## 2 · Full-stack developer

**Objections**

1. *"This adds a database to an app that boots with a dict. That is a new failure mode."*
   → Accepted, and bounded by C-5: without a database the app boots, serves the seed catalogue and
   Databricks models, and disables key saving **with a visible reason**. The registry port has a
   memory implementation on day one ([`api/adapters/memory/store.py`](../../apps/coding-agent/api/adapters/memory/store.py)
   is the precedent), so `agent_mode="fake"` and the tests never need Postgres.
2. *"`set_model` already works. Why rewrite it?"*
   → It does not: it writes a config nothing re-reads, sends an id in the wrong dialect, and skips
   the credential refresh ([01 E6](01-current-state.md#e6-a-model-switch-can-be-sent-in-the-wrong-dialect)).
   The rewrite keeps its one correct part — the ACP string-then-union fallback at
   [`runtime.py:248-270`](../../apps/coding-agent/api/adapters/acp/runtime.py).
3. *"A restart per cross-provider switch is a UX regression."*
   → It is a cost, measured in P5 before it ships. If it exceeds 3 s, the fallback is an explicit
   "open a new session with this model" action, which is honest and simple. What is **not** an option
   is mutating a child's environment, which would add a second injection mechanism and break A4.
4. *"Four adapters means four places to get base URLs wrong."*
   → The inverse: four places to test one URL shape each, with a descriptor that is pure and
   unit-testable. Today the same URL logic is one function with string surgery and no tests for the
   non-Databricks case.
5. *"How does this stay DRY with 001's `ModelCatalog` port?"*
   → The port is **extended**, not duplicated ([`ports/__init__.py:92-94`](../../apps/coding-agent/api/ports/__init__.py)).
   `StaticModelCatalog` becomes `SeedCatalogue`, and `ModelService` composes it — one interface,
   one implementation per source, and the existing tests keep passing against the protocol.
6. *"SOLID, concretely?"*
   → S: the resolver resolves, the policy authorises, the vault opens secrets, the service assembles.
   O: a new provider is a new adapter, no existing file edited (C-2 enforces it). L: every adapter is
   substitutable behind `ProviderAdapter` — the probe test runs the same suite on all four.
   I: four small ports instead of one `ModelManager`. D: services depend on ports; `main.build()` is
   the only place that names an implementation, exactly as it is today
   ([`api/main.py:36-70`](../../apps/coding-agent/api/main.py)).

**Still unresolved:** whether the registry reads through an ORM or plain SQL. Chosen: plain SQL
through `psycopg`, because the queries are two joins and an ORM would add a dependency and a
migration system for four tables. Owner: whoever implements P1.

---

## 3 · Database expert

**Objections**

1. *"Six tables for a dropdown is over-modelling."*
   → Two are audit (`llm_health`, `llm_turn_model`) and one is the credential vault. Only three are
   actually about "which models exist". The audit tables are not optional: FR-10 and FR-11 both need
   history, and a single mutable `health` column cannot answer "did it flap?".
2. *"`llm_model.id` as text PK — no surrogate key?"*
   → Deliberate. The canonical id *is* the natural key and the alias map guarantees uniqueness. A
   surrogate would let two rows disagree about the same model, which is E5's bug in a new place.
3. *"`jsonb extra_options` will become a bag of everything."*
   → Bounded by two rules: templated values only (a `{env:…}` reference or a boolean), and a `CHECK`
   that refuses anything matching a key pattern. Anything that needs a real column gets one.
4. *"Where is the sequence for events?"*
   → Out of scope: this schema does not replace the event store. 001's `EVENT.seq` design
   ([001 08](../001-databricks-coding-agents/08-data-model.md)) stays the authority when it lands.
   Mixing the two now would make both wrong.
5. *"Retention on `llm_health` with a DELETE will bloat without VACUUM."*
   → Autovacuum handles it at this size (57 600 rows/day for 200 models). If the pilot shows bloat, the
   fix is a monthly partition, and that is written down rather than assumed away.
6. *"A revoked credential kept for 30 days is a secret kept for 30 days."*
   → The **ciphertext** is kept; the row is never decrypted again (`revoked_at` is checked before any
   `unwrap`), and the purge job zeroes the ciphertext at 30 days. The fingerprint survives so an audit
   can say "was it this key?" without the key existing.

**Still unresolved:** whether `llm_turn_model` should live beside 001's `TURN` table or replace its
`model_id` column. Chosen: beside, with a foreign key to the session, because this spec must ship
before 001's persistence does. Owner: whoever implements 001 P1, with a migration note.

---

## 4 · UX and UI designer

**Objections**

1. *"A picker with 40 models is a worse experience than 5."*
   → Hence grouping, search, capability facts and a strict order. The mitigation that matters is that
   the picker **opens on the current model** and most sessions never open it at all: the chip names
   the model, and the inspector holds the facts.
2. *"You are adding a settings route to an app with no settings."*
   → It has a palette and a shortcut sheet; a route fits the existing navigation better than a modal
   ([07 §Navigation map](07-ux-ui-wireframes.md#navigation-map)). `⌘,` is the convention users already
   expect, and `esc` leaves.
3. *"State glyphs (`○ ◌ ⚠ ✕`) are cryptic."*
   → They are always paired with words in the row's fact column, and the glyph is `aria-hidden` with
   the state text providing the accessible name. The glyph is a scanning aid, not the only signal.
4. *"The egress notice on the key screen is scarier than the feature."*
   → It should be. A user pasting a Google service-account key is handing this app the ability to
   spend their money and export their prompts. The notice is one sentence, not a wall, and it is
   separate from the Save gesture (K5).
5. *"What happens with no models at all?"*
   → A named empty state, not a blank list ([07 §Empty states](07-ux-ui-wireframes.md#empty-and-first-run-states)).

**Still unresolved:** whether the chip should show the provider ("vertex · gemini-3.8-flash") or just
the model. Chosen: just the model in the chip (space), the provider in the picker and inspector.
Owner: design, after the first usability pass.

---

## 5 · Front-end developer

**Objections**

1. *"A custom combobox is a lot of accessibility surface."*
   → It is, and a native `<select>` cannot express groups with badges. The contract is written and
   tested ([07 §Accessibility](07-ux-ui-wireframes.md#accessibility-contract)); the alternative —
   four `<optgroup>`s with no state — was rejected because it cannot show *why* a model is unusable.
2. *"Does this add bundle weight?"*
   → No new dependency. Search reuses the existing scorer
   ([`web/src/domain/fuzzy.ts`](../../apps/coding-agent/web/src/domain/fuzzy.ts)); grouping and ordering
   are pure functions in `domain/models.ts`, tested with Vitest like the rest of `domain/`.
3. *"Two components render the same model today. Will this become three?"*
   → It becomes **one component used in three places** (`ModelPicker`), plus one facts view. The
   duplicate `<select>` in `App.tsx` and `Chrome.tsx` is deleted, which is a net reduction.
4. *"CLS."*
   → The chip reserves its width from the model name at first paint, and the popover is absolutely
   positioned, so opening it cannot move the layout. `scripts/cls-audit.mjs` is the gate, and the
   existing rule that hides the chip below 1100 px is kept rather than fought.
5. *"The picker must work when `/api/models` is slow."*
   → It renders from the last known catalogue in `sessionStorage` with an "updated Nm ago" footer,
   and refreshes in the background (U10). A first-ever load shows skeleton rows, matching the `.sk`
   shimmer already in the stylesheet.

**Still unresolved:** virtualise the list beyond ~60 models. Not built for v1, noted in
[10 E-17](10-edge-cases-testing.md#scale), with the threshold measured.

---

## 6 · AI engineer

**Objections**

1. *"You are treating the model as a config value. It is a behaviour."*
   → Hence `capability` on every model (`tools`, `tools_and_reasoning`, `chat_only`) and the working
   agreement remaining per session rather than per model. The measured lesson — the same tools scored
   39 % and 86 % on different models — means a model switch is a **behaviour switch**, and the UI says
   so: "applies to your next message", never "updated".
2. *"The thought-signature problem is not optional for Gemini."*
   → Correct, and it is why [04 §Gemini](04-providers.md#gemini-on-vertex-ai) exists with the captured
   error and two working answers. The registry carries `wire = vertex_native | vertex_openai_shim`
   per model so the choice is data, not a fork.
3. *"Output caps are the most common invisible failure. Is the guard strong enough?"*
   → Stronger than today: the guard becomes a property of the resolver over the registry (C-4), the
   clamp is pure and total, and an observed cap error **lowers** the stored cap automatically while
   never raising it ([05 §Limit evidence](05-data-model-lakebase.md#limit-evidence)).
4. *"How do we know a model can call tools at all?"*
   → A `probe` that makes one tiny tool-calling request, cached with the health TTL. A model that
   cannot call tools is catalogued as `chat_only` and not selectable, with that reason shown. This is
   the difference between "we listed it" and "it works".
5. *"Reasoning models and tool loops."*
   → Named, not solved: `extra_body` carries per-model reasoning controls, and the turn's token
   accounting already exists ([`domain/events.py`](../../apps/coding-agent/api/domain/events.py)). A
   reasoning model that ends a turn without a tool call is the supervisor's problem
   ([`domain/supervisor.py`](../../apps/coding-agent/api/domain/supervisor.py)), unchanged.

**Still unresolved:** whether to standardise on ACP v2's model negotiation when agents support it. The
mapper already handles both dialects ([`mapper.py:207-213`](../../apps/coding-agent/api/adapters/acp/mapper.py));
the switch point is `set_model`, and the fallback shape stays.

---

## What all six agree on

| Agreement | Consequence |
|---|---|
| The **credential** is the hard part, not the list | P1 and P3 precede any UI work |
| A model's **provenance** must be immutable | the insert-once table, and a restart for cross-provider switches |
| A **provider** must be an adapter, not a row of URLs | the four-adapter design, and the C-2 grep test |
| **Degradation** must be designed, not caught | C-5 and the seed catalogue |
| The measurements in this repo are the **only** evidence of quality | no vendor ranking is shown; the user decides |

---

## What would make us reverse this design

| Condition | Consequence |
|---|---|
| P0 shows `opencode` cannot hold two provider blocks at once | one process per provider; the resolver returns a provider-scoped session instead of a config |
| P1 shows Lakebase cannot be attached to an app in this workspace | the vault moves to a Databricks secret scope per user, with a much lower key limit — recorded as a scope change, not a workaround |
| P2 shows a service-account JSON cannot authenticate Vertex | the shim ships, with an explicit extra process and its cost recorded in [11](11-decisions-risks.md) |
| The restart for a cross-provider switch exceeds 3 s | switching becomes "start a session with this model", and the design loses live switching |

Each is a probe with an exit criterion, not a hope.
