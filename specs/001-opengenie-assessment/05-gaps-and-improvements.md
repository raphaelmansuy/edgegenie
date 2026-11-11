[Index](README.md) · prev: [04 Against the best agents](04-comparison-best-agents.md) · next: [06 Wireframes](06-wireframes.md)

# 05 · Gaps and improvements

What is missing, ranked. Every item is one of three kinds, and the kind decides whether it is on the
roadmap at all:

| Kind | Meaning | In [08](08-requirements.md)? |
|---|---|---|
| **Cannot** | A platform rule, a missing API, or an architectural property. Closing it is a rewrite or is impossible | no — recorded in [13](13-roadblocks.md) |
| **Does not yet** | Buildable here, with the substrate that exists | yes, if it is in the build list below |
| **Should not** | A different product. The cost is not a screen | no — refused below, with the reason |

Every gap has an id `[G-n]` defined here and cited from [03](03-comparison-genie-code.md),
[04](04-comparison-best-agents.md) and [11](11-implementation-plan.md).

---

## 1 · The gap register

Ranked by **(value × likelihood of use) ÷ cost**. `S` ≈ a day, `M` ≈ a week, `L` ≈ a month, `XL`
≈ a quarter or more.

| # | Gap | Kind | Value | Cost | Phase | Requirement |
|---|---|---|---|---|---|---|
| `[G-0]` | **The fence can fail open** (`F-1`) and **a truncated payload is not JSON** (`F-2`) | defect | **critical** | S | **1** | `[R-1]`, `[R-2]`, `[R-3]` |
| `[G-1]` | **Parallel chats** — one stream per page today | does not yet | high | M/L | 3 | `[R-14]` |
| `[G-2]` | **Search inside conversations** — the rail searches titles and folders only | does not yet | high | S/M | 3 | `[R-15]` |
| `[G-3]` | **Share a conversation** with a user or group | does not yet | medium | M | — | deferred (`[RB-8]`) |
| `[G-4]` | **Branch / regenerate** a turn | does not yet | high | M | 3 | `[R-16]` |
| `[G-5]` | **Read the workspace's `AGENTS.md` and user instructions** | does not yet | **highest** | S | 2 | `[R-17]` |
| `[G-6]` | **User and workspace skills** (Agent Skills standard) | does not yet | high | M | 2 | `[R-18]` |
| `[G-7]` | **Genie Ontology** through `system.ai.genie_one_mcp` | does not yet | high | S/M | 4 | `[R-19]` |
| `[G-8]` | **Dashboards, MLflow, SQL editor** surfaces | cannot (this app) | low here | XL | — | refused |
| `[G-9]` | **Documentation search with citations** | does not yet | medium | M | 4 | `[R-20]` |
| `[G-10]` | **Persistent memory** across sessions | does not yet | medium | M | — | deferred (`[RB-9]`) |
| `[G-11]` | **A second MCP server** (Genie, or a customer's) | cannot without forfeiting the fence | medium | L | — | `[RB-7]` |
| `[G-12]` | **`.xlsx` / `.xls` attachments** | does not yet | low | S | 2 | `[R-21]` |
| `[G-13]` | **Python execution for non-administrators** | cannot without a new identity story | medium | L | — | `[RB-6]` |
| `[G-14]` | **Answer feedback** (thumbs) | should not | — | S | — | refused |
| `[G-15]` | **Accept / reject a proposed notebook edit** | does not yet | high | M/L | 3 | `[R-22]` |
| `[G-16]` | **dbt / git repository work** | cannot (no checkout in the container) | high | XL | — | `[RB-10]` |
| `[G-17]` | **Scheduled agent turns** | does not yet | high | L | 4 | `[R-23]` |
| `[G-18]` | **ZeroOps-style background observation** | should not | — | XL | — | refused |
| `[G-19]` | **Inline completions** | should not | — | L | — | refused |
| `[G-20]` | **A spend ceiling** (not just a lever) | does not yet | medium | M | 2 | `[R-24]` |
| `[G-21]` | **Declarative hooks** for a platform team | does not yet | high | M | 4 | `[R-13]` |
| `[G-22]` | **Subagents** for catalog-scale search | does not yet | medium | L | 4 | `[R-25]` |
| `[G-23]` | **The journal is O(n²)** (`F-4`, `F-5`) | defect | **critical** | M | **1** | `[R-5]`, `[R-6]` |
| `[G-24]` | **Restart UX and lazy rehydration** (`F-9`) | defect | high | M | 2 | `[R-10]` |
| `[G-25]` | **Context compaction** (`F-10`) | does not yet | high | M | 2 | `[R-11]` |
| `[G-26]` | **Write mode is a policy, not a constant** (`F-8`) | does not yet | high | M | 2 | `[R-9]` |
| `[G-27]` | **The app-side fence is dead code** (`F-7`) | defect | medium | S | 1 | `[R-8]` |
| `[G-28]` | **Session ordering** (`F-6`), **ledger O(history)** (`F-11`) | defect | medium | S | 1 | `[R-7]`, `[R-12]` |
| `[G-29]` | **The docs claim the agent holds no token** (`F-3`) | defect | high (trust) | S | 1 | `[R-4]` |
| `[G-30]` | **A settled turn can be rewritten** (`F-12`) | defect | **critical** | S | **1** | `[R-26]` |
| `[G-31]` | **`closed:offline` is unreachable** (`F-13`) | defect | medium | S | **1** | `[R-27]` |
| `[G-32]` | **An active run reads as finished, with Cancel** (`F-14`) | defect | high | S | **1** | `[R-28]` |
| `[G-33]` | **`QUEUED` reported as failed** (`F-15`) | defect | high | S | **1** | `[R-29]` |
| `[G-34]` | **A retention reason that lies** (`F-16`) | defect | medium | S | **1** | `[R-30]` |
| `[G-35]` | **Completed work reported as `blocked`** (`F-17`) | defect | **critical** | M | **1** | `[R-31]` |

---

## 2 · The three that must land first, and why

`[G-0]` and `[G-23]` are in phase 1 because they are the two ways this product's own promises are
falsified by its own code.

**`[G-0]` is a safety defect.** "Writes stay inside the fence" is the product's second rule. A session
with no schema can write anywhere the user can, and *no test fails*. Shipping a feature on top of that
is building on a claim you have not checked.

**`[G-23]` is a wall, not a bug.** At ~1.8 GB written per turn, a conversation of ten turns writes
~18 GB. That does not fail gracefully; it makes the stream slow, then the database large, then the
reconnect read the whole thing. Every feature that produces *more* events — parallel chats, subagents,
hooks, compaction — makes it worse. It must be fixed before anything multiplies it.

`[G-29]` is in phase 1 because it is *cheap* and it is *trust*: a security review that finds a false
statement in `docs/09-security.md` stops trusting the rest of the document.

**And six more joined phase 1 after the diagrams were written** (`[R-26]`–`[R-31]`, step 1.9–1.14 in
[11](11-implementation-plan.md)). They were found by exhausting every state machine rather than reading
the request path, and three of them change a verdict the product shows a user. They are in phase 1 for
the same reason as the other nine: each is one guard or one table, and a state word that lies is the
cheapest kind of trust to lose.

---

## 3 · The build list, in the order a user would notice

### Phase 1 — make the promises true (nothing else starts)

| Requirement | What becomes true |
|---|---|
| `[R-1]` | No schema means **no write**, and the refusal names the reason. `WRITE_PATHS` can never be a wildcard |
| `[R-2]` | The parity table has rows for the empty cases, so the two runtimes cannot disagree there again |
| `[R-3]` | A truncated tool result is **valid JSON with an explicit window** (`returned`, `total`, `next_offset`) |
| `[R-4]` | The documentation either states the truth about the child's environment or the code stops passing the token; a test asserts whichever is chosen |
| `[R-5]` | The snapshot is a **checkpoint**, not a per-event write |
| `[R-6]` | Deltas are **coalesced** (≤100 ms or ≤2 KB), at the runtime and therefore in the reducer too |
| `[R-7]` | Sessions sort by `created_at` |
| `[R-8]` | The dead fence functions are retired **or** wired, with the decision recorded |
| `[R-12]` | The ledger is read per session, not per history |

### Phase 2 — the things a team asks for on day two

| Requirement | What becomes true |
|---|---|
| `[R-9]` | A session has a **write mode**: `read-only`, `fenced`, `ask` |
| `[R-10]` | A restart does not block idle sessions; an evicted session rehydrates on read |
| `[R-11]` | Compaction exists, `session.compacted` is emitted, and `max_turns_per_session` is honoured |
| `[R-17]` | The workspace's `AGENTS.md` and the user's instructions are **read and labelled as user-authored context** |
| `[R-18]` | A user skill and a workspace skill are loadable; `dbx_skill` lists them |
| `[R-21]` | `.xlsx` / `.xls` attachments are accepted as a text-bearing family |
| `[R-24]` | A per-session token and cost budget exists, and a turn that exceeds it is **blocked with the number** |

### Phase 3 — the surface, where Genie Code is ahead

| Requirement | What becomes true |
|---|---|
| `[R-14]` | Parallel chats: N live streams, one per session, in a tab strip |
| `[R-15]` | Search inside conversations, using the journal |
| `[R-16]` | Branch a conversation from a turn; regenerate a turn |
| `[R-22]` | A proposed notebook edit is shown as a diff and accepted or rejected |

### Phase 4 — the platform, for the team that governs it

| Requirement | What becomes true |
|---|---|
| `[R-13]` | Declarative hooks: a workspace names a rule, the fence evaluates it |
| `[R-19]` | Genie Ontology is reachable as a second, **separately fenced** tool server |
| `[R-20]` | Documentation search with citations |
| `[R-23]` | Scheduled agent turns under the app's identity, with a run record |
| `[R-25]` | A subagent scoped to catalog search, bounded in tokens and time |

---

## 4 · The refusals, with reasons

A roadmap that refuses nothing is a wish list. These are refused, and the reason is in the code or in
the platform, not in taste.

| Refused | Why, grounded |
|---|---|
| **Inline completions** `[G-19]` | It needs a *second* model route with different properties: sub-100 ms, debounced, cancellable, billed per keystroke. The ACP runtime starts a process per session and has no completion channel (`runtime.py` has `prompt`, not `complete`). Adding one is a new client, a new cost model and a new cancellation path — to compete with Cursor's Tab, which is best in class |
| **Connector marketplace** `[G-11]` | Every connector is an OAuth client, a token store, a revocation story and an egress decision. And the fence cannot cover a third-party MCP server: the whole model is *"the tool server was started with one folder and one schema"*, which a customer's server is not. Genie's own connectors are a beta behind a workspace setting |
| **Genie Migrate** `[G-8]` | A SQL-dialect translation product. Not a phase, a company |
| **ZeroOps** `[G-18]` | Watches live systems continuously. This app runs turns when a browser asks; there is no always-on observer, and building one is `[G-17]` plus an alerting surface |
| **Thumbs up/down** `[G-14]` | There is nowhere to send it. A feedback button whose data no one reads is a lie about caring |
| **A dashboard / MLflow surface** `[G-8]` | Those are Databricks' surfaces. OpenGenie shows *engineering* objects (notebook, job, run, pipeline, table) because that is what its tools can read and its fence can prove |

---

## 5 · What "improved" means, measurably

Not adjectives. Each of these is a number the plan moves, and each is checked in [15](15-e2e-plan.md).

| Metric | Today (measured) | After phase 1 | After phase 2 |
|---|---|---|---|
| Bytes written per turn (60 k answer) | ≈1.8 GB | ≤4 MB | ≤4 MB |
| `message.delta` events per 60 k answer | ≈15 000 | ≤600 | ≤600 |
| Tab work per delta | O(answer) | O(chunk) | O(chunk) |
| Sessions a restart blocks | all non-archived | only those mid-turn | only those mid-turn |
| Turns before the model window fails | 200 (hardcoded) | 200 (`settings`) | compaction, so unbounded |
| Tools advertised per turn | 28 | 28 | 28 (+1 if a Genie server is fenced) |
| A write outside the schema | executed | refused | refused, or an approval if the mode is `ask` |
| Conversations the rail can search | title + folder | title + folder | full text |
| A truncated list result | invalid JSON | valid JSON + window | valid JSON + window |

Next: [06 · Wireframes](06-wireframes.md).
