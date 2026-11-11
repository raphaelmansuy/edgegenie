[Index](README.md) · prev: [08 Requirements](08-requirements.md) · next: [10 Architecture](10-architecture.md)

# 09 · Eight lenses

The same work, seen by the eight people who will have to live with it. Each lens answers: **what do I
own, what is wrong from where I sit, what would I refuse, and how do I know it worked?** Where two
lenses disagree, the disagreement is named at the end and resolved.

These are roles, not people. A real review would replace several of them. `[L-8]` was **added**
after the first seven were written, because none of them owned the question *is this proven?* — and
adding it found six defects ([02 §8](02-assessment-opengenie.md#8--six-state-machine-defects-proved-by-exhaustion)).

---

## `[L-1]` Product owner

**What I own.** The promise on the README, the roadmap, and the refusal to ship a claim I cannot prove.

**What is wrong from here.** The product has a good sentence and a bad title.
"The Databricks coding agent, on the model you choose" is true, differentiating and defensible.
"On par with Genie Code" (spec 006) is not, has not been since Genie shipped its command centre, and
cannot become true without building a BI surface, an ontology and a scheduler.

**What I would do about it, in the order a customer would notice.**

1. **Fix the four false claims before any new feature** (`[R-1]`–`[R-4]`). A product whose selling point
   is governance cannot be caught with a fence that fails open. This is not engineering caution; it is
   the product's only differentiator.
2. **Then the one thing users ask for on day two:** *"can it follow our conventions?"* → `[R-17]`
   instructions and `[R-18]` skills. It is a day's work, it turns every conversation from zero-context
   into team-context, and it is the cheapest parity win in the whole comparison.
3. **Then parallel chats** (`[R-14]`). Not because it is fun, but because the Genie blog's own customer
   quote is a user running fifteen threads and complaining about tab management. That is a paying
   customer describing their blocker.
4. **Then the audit surface** (`[R-24]` cost per turn, and the existing turn pins made visible). This is
   the thing no competitor has and this product already stores.

**What I refuse, out loud.**
Inline completions, connectors, Genie Migrate, ZeroOps, dashboards. Each is a product. A roadmap that
lists them is a roadmap that will be 30% delivered in a year and will have shipped none of the four
items above.

**How I know it worked.** One sentence changes: I can say *"the governed coding agent you can prove"*
without a footnote, because the fence closes, the claims are true, and a conversation can be handed to
an auditor.

**My one disagreement with engineering.** They want phase 1 to take three weeks because `[R-5]` and
`[R-6]` are "a rewrite of the commit path". It is one function and one coalescer. I will take the
rewrite risk to get the safety fixes in a week.

---

## `[L-2]` UI/UX expert

**What I own.** The shell, the words, the states, and whether a person can tell what happened.

**What is wrong from here.**

1. **`F-9` is a UX defect before it is a durability one.** Every restart turns every conversation into
   a red banner. To a user that reads as *"this app loses my work"*, which is the opposite of the
   truth — the journal is unusually good. The fix is a distinction (`[R-10]`), and the copy already
   exists in `domain/mission.ts`.
2. **`F-6` is invisible in a demo and obvious in use.** A rail that groups by day and orders randomly
   inside a day looks like it is sorting by something the user cannot see. It erodes trust in every
   other list.
3. **One conversation at a time is a *layout* limitation, not a server one.** The shell already has a
   tab strip for documents (`DocTabs`); conversations are documents in every way that matters. `[R-14]`
   is mostly a matter of moving `useSessionStream` from a singleton to a keyed map.
4. **Provenance is the missing habit.** `[R-17]` injects instructions, and the transcript must show them
   **labelled by source** or the user cannot tell what they typed from what their team configured. That
   is a UI decision with a governance consequence, and it belongs in the wireframe (F6) not in a
   component's default.

**What I would refuse.** A fifth session state. There are four words in `mission.ts` and every new
state is a screen someone has to write copy for. `[R-10]` adds a *distinction*, not a state: `ready`
already exists.

**How I know it worked.** A user can answer, without clicking: what is running, what needs me, what did
it cost, and what was it told. Four questions, four surfaces, no new screens.

**My one disagreement with the database lens.** They want `SESSION_BUDGET` as a table. I want it
visible in the inspector, which means it must be in the session read. Both are satisfiable; the table
wins, and the read joins it (`F8`).

---

## `[L-3]` Full-stack development expert

**What I own.** The seam. Whether the two halves agree about the vocabulary, the state machine and the
error contract.

**What is wrong from here.**

1. **The vocabulary has a hole.** `session.compacted` is in `EVENT_TYPES`, in the TypeScript union, in
   `event-parity.json` — and emitted by nobody (`F-10`). The parity test is *happy about it*, because
   parity tests compare declarations. A vocabulary test that checks **every type is producible** is the
   missing half.
2. **The reducer is not the bottleneck it looks like** (`F-5`). `append()` is O(n) per delta and called
   per delta, but the fix belongs at the source (`[R-6]`), not in the reducer. Fixing it in the reducer
   would be treating a symptom in the layer that has the least information.
3. **`api/domain/scope.py` has functions nothing calls** (`F-7`). From a full-stack seat this is worse
   than dead code: it is dead code that a document describes as a layer. Either wire it or delete it;
   `[R-8]` requires the decision, and `[RB-5]` argues for deletion.
4. **The error contract is good and must stay.** `PermissionError → 403`, `LookupError → 404`,
   `ValueError → 422`, `DomainError → 409`, `RuntimeError → 502`, in one `_dbx_errors`. Every new route
   in this plan uses it unchanged; a second mapping would be the beginning of two truth stories.

**What I would refuse.** A new HTTP route for something a stream event already carries. `[R-14]` needs
**no** new endpoint: N streams are N `EventSource`s with different ids.

**How I know it worked.** `event-parity.json` is unchanged, but a new test asserts that every name in it
has a producer, and the count of routes rises by zero for phase 1.

---

## `[L-4]` Database expert

**What I own.** The journal, the migrations, the cost of a write, and the correctness of a replay.

**What is wrong from here.**

1. **`F-4` is the finding I would have made first.** `commit()` writes the full snapshot per event
   inside `self._lock` — a single connection, a single asyncio lock, one round trip per delta. At
   15 000 deltas that is not "a lot of data", it is **a serialized write path shared by every session
   on the server**. The lock is process-wide, so one long answer delays every other conversation's
   commits. That is the real cost, and it is worse than the storage number.
2. **`since()` has no index beyond the primary key.** `PRIMARY KEY (session_id, seq)` makes it a range
   scan within the key, which is fine. But a reconnect replays from `?after=0`
   (`useSessionStream.ts:166`) and the handler pages with `LIMIT 2000` in a loop — so a 15 000-event
   turn is 8 round trips before the first byte of live data. Coalescing (`[R-6]`) fixes this too, which
   is why it and `[R-5]` are one phase.
3. **`snapshots()` reads every row on boot.** `SELECT body FROM agent.session_snapshot ORDER BY
   session_id` with no bound, and `restore()` builds a `Live` for each. At 10 000 conversations that is
   a slow start and a large heap. `[R-10]`'s lazy rehydration is the fix for the *read* path; a bound on
   the boot set is a phase-2 note (`[E-14]`).
4. **A migration that adds a column to the snapshot must be versioned.** `_snapshot()` writes
   `version: 1` and `restore()` **raises** on anything else (`orchestrator.py:168-169`). `[R-9]`'s
   `write_mode` and `[R-24]`'s budget are session facts; putting them in `body` forces a version bump,
   which will refuse to start against the old rows. So: **two nullable columns on the snapshot table**,
   not fields in the JSON. That is a real design consequence of a real line of code.

**What I would refuse.** A `session_event` row per delta as the *permanent* design. It is correct and
it does not scale; the coalescer is not an optimisation, it is the schema's stated unit ("one event")
being applied to a stream that has 15 000 of them.

**How I know it worked.** `explain analyze` on the two hot statements, a bytes-written counter asserted
in a test, and a boot that reads `O(open sessions)` rows rather than `O(all history)`.

**My one disagreement with the system-design lens.** They want a checkpoint table separate from
`session_snapshot`. I want the checkpoint **in** the snapshot row (`checkpoint_seq`), because two
sources of truth for "how far is the projection" is how a replay diverges.

---

## `[L-5]` System design expert

**What I own.** The boundaries, the failure modes, and what happens under load.

**What is wrong from here.**

1. **The single-writer advisory lock is correct and it is a ceiling.** `pg_try_advisory_lock(0x4F50454E47454E49)`
   means exactly one server owns the journal (`postgres.py:43`). That is the right call for
   correctness — a stale worker must not write behind a replacement. But it means **throughput is one
   process**, and `F-4` puts a per-delta round trip in the hot path. The two together are the reason a
   dozen concurrent long turns will feel slow.
2. **Processes per session are the second ceiling.** `APP_MAX_CONCURRENT_AGENTS=4` limits *turns*, and
   `APP_REAP_KEEP_MINIMUM=8` limits *live sessions*. `[R-14]` (parallel chats) increases the demand for
   both without changing the supply. The plan must raise the *kept* count deliberately, or parallel
   chats will evict each other.
3. **`[R-19]`'s second tool server is the only item that changes the topology.** Two servers per session
   doubles the process count and the tool schemas. `[RB-7]` argues it must be a *separate, read-only*
   server, never a merge.

**What I would refuse.** Any design where a hook runs in its own process (`[07 §10]`). It would need
its own identity, timeout, failure mode and audit row, and it would sit *beside* the thing that already
classifies writes rather than inside it.

**How I know it worked.** The commit path is O(1) per event and O(events/50) per turn; two conversations
can stream at once without one delaying the other's commits; and the process count per session is
documented in one place with the arithmetic.

---

## `[L-6]` O(n) expert

**What I own.** The complexity of every path a user waits on, stated as a formula rather than a feeling.

**What is wrong from here, as formulas.**

| Path | Today | After |
|---|---|---|
| Committing a turn's events | `O(d · S)` where `d` = deltas and `S` = snapshot size, and `S = O(answer)`. With `d = O(answer)` → **`O(n²)` bytes** | `O(d) + O(d/50 · S)` → **`O(n)`** |
| Reducer appending a delta | `O(len(answer))` per delta → **`O(n²)`** characters copied | `O(1)` per coalesced chunk, so `O(n)` total |
| Reconnect replay | `O(events)` in `LIMIT 2000` chunks, `O(d)` round trips | `O(events/600)` events, `O(d/600)` round trips |
| `read_ledger` on a page load | `O(total history)` — every file, every request | `O(1)` — one file |
| `sessions_for` | `O(s log s)` but on a random key | `O(s log s)` on `created_at` |
| Search (`[R-15]`) | no implementation | `O(log N + k)` with a GIN index |
| Fork (`[R-16]`) | no implementation | `O(k)` where `k` = events in the prefix, one `INSERT … SELECT` |
| Budget check (`[R-24]`) | no implementation | `O(1)` if `SESSION_BUDGET` is maintained, `O(t)` if summed from pins — so maintain it |
| `restore()` on boot | `O(all sessions)` | `O(all sessions)` rows read but **one `Live` per open session**, so `O(open)` heap |

**The two that matter** are the first two, because they are the same bug at two layers, and because
`n` is the length of an answer — the thing this product produces.

**What I would refuse.** Any "just cap it" fix. `MAX_ANSWER = 200_000` already caps the symptom and the
cost is still quadratic up to the cap. A cap bounds `n`; it does not change the exponent.

**How I know it worked.** `test_journal_cost.py` counts *writes*, not bytes, so it fails on a
regression to per-event snapshots regardless of payload size.

---

## `[L-7]` AI engineer

**What I own.** The loop: what the model sees, what it may call, and whether a claim is true.

**What is wrong from here.**

1. **The context the model gets is thinner than the product implies.** No workspace instructions
   (`[R-17]`), no user skills (`[R-18]`), no ontology (`[R-19]`), no documentation search (`[R-20]`).
   Genie Code has all four. In practice this means every conversation starts by rediscovering what the
   team already knows, and it is the single largest accuracy lever left — larger than the model choice,
   which is the lever this product already built.
2. **Truncation is the dangerous failure and it is still present** (`F-2`). The repository's own
   experiments measured what happens: an agent handed a fragment reports it as the whole truth with full
   confidence. `[R-3]` is an AI-safety fix dressed as a payload fix.
3. **The supervisor is the best thing here and it has one blind spot.** `supervisor.decide` matches
   claims to completed calls; a *hallucinated result summary* on a real call still passes, because the
   check is "was there a completed call of that name", not "does the summary match the call's output".
   That is `[E-6]` and it is deliberately **not** in this plan: tightening it needs a diff of the
   tool's own result against the claim, and getting that wrong produces false `blocked` turns — the
   worst failure this product has.

**What I would refuse.** Raising `MAX_AUDITS` from 2 to "as many as it takes". The measured behaviour
is that a second audit pass resolves most gaps; a third mostly burns tokens on a model that has already
concluded. The number is a *product* decision recorded in `supervisor.py:46`, not a knob.

**How I know it worked.** The exam suite's score does not drop when `[R-17]` and `[R-18]` land (a
regression gate: the same 11 missions, the same models), and the fragment-fabrication scenario is
re-run with the windowed payload and produces a correct answer at the same cost.

---

## `[L-8]` Verification engineer — the lens this set had to add

**Why an eighth lens.** The request was to *make sure all is proven*. The first seven lenses each argue
about a **decision**; none of them owns **whether the argument is checkable**. That is a distinct job, and
it found six defects the other seven missed ([02 §8](02-assessment-opengenie.md#8--six-state-machine-defects-proved-by-exhaustion)).

**What I own.** The difference between "the code does X" and "the code can only do X". The first is a
reading; the second is a proof, and only the second belongs in a specification.

**How I work.** For every state machine, I enumerate the **product** of its axes and run it, rather than
reading the transitions the author intended. Eight statuses × five terminal targets. Six life cycles ×
ten results. Five states × three refcounts. Every `(status, online)` pair the stream hook can observe.

**What that found, and what it says about the other seven lenses.**

| Lens | Its finding was | The enumeration's finding was |
|---|---|---|
| AI engineer (`[L-7]`) | "the supervisor is the best thing here and has one blind spot (`[E-6]`)" | the *mirror* blind spot: completed work reported as `blocked` (`F-17`), which is worse because it punishes a compliant agent |
| Full-stack (`[L-3]`) | "`session.compacted` is declared and never emitted" | the same class, twice more: `closed:offline` (`F-13`) and a `run_word` that reads the convenient field (`F-14`) |
| Database (`[L-4]`) | "`commit()` writes the full snapshot per event" | a smaller one in a rule that deletes files: a reason that is not the reason (`F-16`) |
| System design (`[L-5]`) | "single writer is a ceiling; processes are a ceiling" | a turn's terminal state is not terminal (`F-12`) — a *state* invariant, not a throughput one |

**What I refuse to accept as proof.** Four things, and each has a cost:

| Claim offered as proof | Why it is not one | What is |
|---|---|---|
| "1 303 tests pass" | a suite says what it covers; `F-12` and `F-17` are in code it exercises | the specific matrix, printed |
| "the docstring says X" | `F-14`'s docstring states the rule it breaks | the executed grid |
| "the type declares X" | `F-13`: the union has a member nothing produces | a reachability walk |
| "the diagram shows X" | a diagram is a claim about intent until it is generated from a table | this document's §16 |

**How I know it worked.** Every diagram in [07](07-diagrams.md) names the command that produced its
table, and re-running that command reproduces the table. A diagram whose command is missing is a bug in
the document, not a figure.

**My one disagreement with the PO.** They wanted phase 1 to be one week of safety fixes. Six of the
seventeen findings are state-machine defects that were *not* on that list, and three of them change a
verdict a user reads. I would rather ship phase 1 in two weeks with `F-12` and `F-17` fixed than in one
week with a fence that closes and a turn that can still be rewritten after it finished.

---

## Where the lenses disagree, and how it is resolved

| Disagreement | Lenses | Resolution | Where |
|---|---|---|---|
| How long phase 1 may take | PO wants a week; full-stack warns the commit path is a rewrite | **Split:** `[R-1]`–`[R-4]`, `[R-7]`, `[R-8]`, `[R-12]` in week 1 (surgical); `[R-5]`, `[R-6]` in week 2 as the one change with a cost test | [11 §2](11-implementation-plan.md) |
| Where the budget lives | UX wants it in the session read; database wants a table | **Both:** a table, joined into the session read. One writer, one reader, no duplication | `[R-24]`, `[07 §6]` |
| Where the checkpoint lives | System design wants its own table; database wants a column | **Database wins:** `checkpoint_seq` on the snapshot row. Two sources of truth for "how far" is how a replay diverges | `[R-5]` |
| Whether to wire or delete `check_sql` | Full-stack says delete; PO says "two layers is the promise" | **Delete, and change the promise to what is true:** the fence is one implementation, in the tool server, held to a table. Wiring it means a new bridge call on every SQL statement | `[R-8]`, `[RB-5]` |
| Whether a hook can run code | System design says no; AI engineer wants `ruff` after every write | **Both, in sequence:** phase 4 ships declarative rules; an `after_tool: run` action is specified but gated behind an administrator flag, because it is a program in the tool server | `[R-13]`, `[E-16]` |
| Whether to chase subagents | AI engineer says it is the real data problem; PO says it is not on the critical path | **PO wins on order:** phase 4, after the surface. The AI engineer's reason (context isolation) is recorded in `[G-22]` so it is not lost | [04 §3.2](04-comparison-best-agents.md#32-subagents-the-pattern-this-product-can-afford) |

Next: [10 · Architecture](10-architecture.md).
