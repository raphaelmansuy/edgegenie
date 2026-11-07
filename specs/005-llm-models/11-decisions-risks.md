# 11 · Decisions and risks

[Index](README.md) · prev: [10 Edge cases](10-edge-cases-testing.md) · next: [12 Operations](12-operations-runbook.md)

Format for a decision: **D-n · decision — because — alternatives rejected — revisit when.** Every
rejected alternative is named, because a decision without a rejected alternative is a preference.

---

## Decisions

| ID | Decision | Because | Rejected | Revisit when |
|---|---|---|---|---|
| **D1** | Model ids resolve through **data** (a registry + an alias map), never through string manipulation | [`agent_config.py:180-189`](../../apps/coding-agent/api/adapters/acp/agent_config.py) turns an unknown id into a plausible wrong endpoint instead of an error; Axiom A1 | a longer `KNOWN_ENDPOINTS` dict; a naming convention enforced by a validator | never |
| **D2** | One **adapter per wire protocol**, behind one port; the domain never names a vendor | the four protocols differ behaviourally (Anthropic headers, Vertex signatures, Databricks caps), and a URL template cannot express that; Axiom A2 | a data-driven table of base URLs; a single "compatible" adapter with flags | if a protocol becomes universal — not foreseeable |
| **D3** | Credentials live in Lakebase, **envelope-encrypted**, with the KEK outside the database | a database dump must not be a key dump; the two failure modes must be independent ([06](06-security-credentials.md#where-a-key-could-live-and-why-we-chose-one-place)) | plaintext with column grants; a KEK in an env var; per-session entry with no storage | if a Databricks secret scope can hold per-user values directly, which would remove the vault |
| **D4** | One **`LLM_PROVIDER_KEY`** environment variable, not vendor-named variables | one name means one injection mechanism and one thing to audit; vendor names invite a second key in the same process (Axiom A4) | `OPENAI_API_KEY` etc. per provider; a key file like the tool server's token | if a provider SDK cannot be configured from a generic variable — then the adapter maps it, not the app |
| **D5** | A **cross-provider switch restarts the child**; a same-provider switch uses ACP | a child's environment is fixed at spawn, and adding a variable later needs a second mechanism | mutate `os.environ` of the parent (leaks to every subprocess); a polling file (a second mechanism) | if P5 measures the restart above 3 s — then "open a new session with this model" |
| **D6** | **No automatic fallback** to another model on failure | a silent substitution makes the transcript lie about who answered; the evidence chain breaks | automatic retry on a cheaper model; a "smart" router | if a user-visible "retry with X" action proves insufficient |
| **D7** | **No per-turn routing** in this spec | routing needs the registry first, and a routing policy is a product decision about cost and quality that no measurement here supports yet | a cost-aware router; a "best model" heuristic | after the pilot has per-model cost and success data |
| **D8** | Discovery **never deletes** a row; it marks `not_served` | discovery failing must not revoke access, which is exactly what the current `None`-means-do-not-filter rule protects ([`serving.py:22-32`](../../apps/coding-agent/api/adapters/databricks/serving.py)) | reconcile-by-delete; soft-delete with a TTL | never |
| **D9** | **Limits are data with provenance**; a cap error lowers, never raises | three measured caps in one workspace; a wrong cap makes a model unusable after a wait | trusting a model's self-reported window; a single global cap | never |
| **D10** | A turn's model is an **insert-once** record, and the app role has no `UPDATE` on it | provenance is the product; the current code can rewrite `session.model` under a live turn | a mutable `model_id` on the session | never |
| **D11** | The **app boots without a database** | local development, demo mode and the pilot all run without Lakebase today | require Lakebase; a SQLite fallback (a second SQL dialect to test) | never |
| **D12** | `LLM_ALLOW_EXTERNAL` defaults to **off** | external calls move prompts and money outside Unity Catalog; a pilot should opt in | on by default with a warning | after a workspace has approved an external provider in policy |
| **D13** | The picker is a **combobox popover**, not a `<select>` and not a modal | a `<select>` cannot show state or a remedy; a modal interrupts a per-session choice | native `<select>` with `<optgroup>`; a modal sheet at all widths | if the list stays under ~8 selectable models |
| **D14** | **Grouping and order are pure, tested functions** | a list that reorders itself cannot be learned; today two `<select>`s disagree on formatting | server-side ordering only (untestable in isolation) | never |
| **D15** | Diagrams and specs are **generated and verified**, not hand-drawn | an ASCII box one column out drifts invisibly; three verifiers already exist for spec 003 | hand-drawn ASCII with a review habit | never |

---

## Decisions this spec reverses or amends

| Earlier decision | What happens | Why |
|---|---|---|
| [001 14 D-15](../001-databricks-coding-agents/14-decisions-risks.md) "model choice visible per message" | **strengthened**: per-message becomes per-turn and immutable | the existing implementation can rewrite it |
| [001 14 R-12](../001-databricks-coding-agents/14-decisions-risks.md) "model choice is dictated by what the gateway exposes" | **closed**: the registry plus external providers remove the constraint | the risk is now about credentials, not availability |
| [001 14 Q-1](../001-databricks-coding-agents/14-decisions-risks.md) "is a non-gateway model allowed?" | **answered**: yes, behind `LLM_ALLOW_EXTERNAL`, with a per-provider key | measured: the best scoring model was not a gateway model |
| [003 §Scope](../003-improve-dev-ux-ui/README.md) "collaborative multi-cursor editing" out of scope | untouched | unrelated |
| [004](../004-crdt-collaboration/README.md) CRDT work | **not touched**, but 004's Lakebase plan and this spec's `llm` schema must share a migration runner | two migration runners in one app is a defect waiting |

The last row is a real coordination cost and is stated rather than assumed away:
[009 §P7](09-implementation-plan.md#p7-delete-the-old-path) does not resolve it, because it belongs to
004. Whoever implements 004 P1 must adopt this spec's forward-only runner rather than add a second one.

---

## Risks

Likelihood × impact, with a named mitigation and an owner. **Bold** rows could sink the feature.

| ID | Risk | L | I | Mitigation | Owner | Residual |
|---|---|---|---|---|---|---|
| **R-1** | **A provider key leaks** through a log, an event, an export or an injected prompt (TH-9) | M | **Critical** | envelope encryption; one key in one child; redaction at every sink; the eight-sink scan in [10](10-edge-cases-testing.md#secret-hygiene); builtin shell denied | Security | **Medium**: the child's memory holds a key while a session runs |
| **R-2** | **Cross-user key use** (TH-10) | L | **Critical** | scope is `(kind, id)`; resolution passes the session user; E-12 as the first test written | Security | Low |
| **R-3** | A model is offered that cannot work, and the user waits to find out | H | High | capability probe; `Test connection`; health before use; the classifier names the cause | AI | Low |
| **R-4** | Lakebase cannot be attached to an app in this workspace ([001 R-09](../001-databricks-coding-agents/14-decisions-risks.md)) | H | Medium | C-5: the app degrades to the seed catalogue and the Databricks models keep working | Full-stack | Medium: no key store in that workspace |
| **R-5** | The `EnvKek` mode reaches production | M | High | `put()` refuses when `APP_ENV=production` and no scope KEK exists; the mode is shown in settings and logged at boot | Security | Low |
| **R-6** | The cross-provider restart is slow enough to feel broken | M | Medium | measured in P5 before it ships; the fallback is an explicit new-session action | Full-stack | Low |
| **R-7** | The agent drops the `thought_signature` on Gemini turns | H (if the OpenAI-compatible path is used) | High | `wire = vertex_native` by default; the shim as the measured fallback; the captured error is a classifier case | AI | Low with native, Medium with the shim |
| **R-8** | The picker becomes a wall of 40 models | M | Medium | grouping, search, current-model-first, collapse; one component in three places | UX | Low |
| **R-9** | A provider's API changes and the adapter breaks silently | M | Medium | the health classifier names the provider's words; one adapter file to change (A2); a recorded error body per provider in tests | AI | Low |
| **R-10** | Two migration runners (this spec's and 004's) | M | Medium | named here; 004 must adopt this runner | Platform | Medium until 004 starts |
| **R-11** | The registry becomes a router by accretion | M | Medium | [D7](#decisions) is the written boundary; a routing feature needs its own spec | PO | Low |
| **R-12** | Keys are stored but never rotated, and expire silently | H | Medium | `last_used_at`; the provider-reported expiry in the UI; a settings banner for a key unused for 90 days | Ops | Medium |
| **R-13** | Cost surprises on a user's own account | M | Medium | no cost prediction promised; per-turn usage is recorded and shown; the settings screen names the key's owner | PO | Medium: the app cannot cap a provider account |

---

## Open questions

| # | Question | Blocks | Who decides | By when |
|---|---|---|---|---|
| Q-1 | Are external providers permitted by workspace policy at all? | D12's default | platform + security | before P3 |
| Q-2 | Is a Databricks secret scope attachable to the app, for the KEK? | which `KekProvider` ships | platform | before P3 |
| Q-3 | Does the workspace allow a Lakebase instance for this app? | P1's hard path | platform | before P1 |
| Q-4 | Should a workspace key be usable by everyone, or only listed users? | grant defaults | PO + security | before P3 |
| Q-5 | Retention of `llm_turn_model` — 90 days like the turn record, or longer for audit? | schema comment only | privacy owner | before P1 |
| Q-6 | Is an external provider's data-retention statement acceptable for this workspace's data? | whether `LLM_ALLOW_EXTERNAL` can ever be 1 | security | before the pilot |

Q-1 and Q-6 are the same question asked twice on purpose: the technical flag and the policy decision
must not drift apart.

---

## Claims this spec will not make

1. **"Cheaper."** No cost comparison is offered. A user's own key may be cheaper or dearer than the
   gateway; the app shows observed usage, not a promise.
2. **"Every model works."** A model that cannot call tools is catalogued and not selectable, with the
   reason. A model that is gated in a workspace is shown as gated.
3. **"As safe as the gateway."** External calls leave Unity Catalog. That is stated in the settings
   screen, in [06](06-security-credentials.md#egress-what-a-provider-key-actually-permits), and in the
   threat model — not hidden behind a toggle.
4. **"Production ready"** until the five tests in [10](10-edge-cases-testing.md#the-five-tests-to-write-first)
   and the six CI checks in [09](09-implementation-plan.md#enforcement-not-convention) pass.

---

## How this spec stays true

| Mechanism | Detail |
|---|---|
| Every claim labelled | `[verified]` / `[documented]` / `[proposal]` / `[unverified]`, per [README](README.md#provenance-of-the-claims-in-this-spec) |
| Diagrams generated | `tools/diagrams.py` and `tools/wireframes.py`; `verify-spec-ascii.mjs` parses the result |
| Links verified | `verify-spec-links.mjs`, which already exists for spec 003 |
| Mermaid parsed | `verify-spec-mermaid.mjs`, with the real Mermaid parser |
| Unverified work listed | [01 §What we have not verified](01-current-state.md#what-we-have-not-verified) and [12 §What we have not verified](12-operations-runbook.md#what-we-have-not-verified) |
| A change names the documents to re-read | the [cross-reference matrix](README.md#cross-reference-matrix) |
| This log | every significant change is a D-nn entry or amends one |
