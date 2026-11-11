[Index](README.md) · prev: [11 Implementation plan](11-implementation-plan.md) · next: [13 Roadblocks](13-roadblocks.md)

# 12 · Edge cases

Every failure that can be named, what the code does today, what it must do, and the test that holds it.
`[E-n]` is defined here once.

The rule for admission: an edge case is in this list only if **a plausible user or a plausible input**
produces it. "What if the database is on fire" is not a case; "what if the schema is empty" is, and it is
`[E-1]`.

---

## Group A · The fence

### `[E-1]` A session with no schema

**Input.** `POST /api/sessions {folder: "/Users/me/x", schema: null}` — the ordinary way to create a
session for analysis.

**Today.** The app's `check_sql` says `ASK`; the tool server's `_check_sql_scope` returns `None`
(*allow*), and `NBMCP_WRITE_SCHEMAS` is `""`. A `DROP TABLE main.production.sales` executes. Measured in
[01 §2.1](01-method-and-evidence.md#21-executed-a-property-of-the-code-measured).

**Must.** Refuse, with the sentence: *"This session has no writable schema, so it cannot write. Choose a
schema when you start a conversation."*

**Test.** `test_fence_parity.py::UNSET_CASES["schema"][None]` asserts both sides refuse.

---

### `[E-2]` A session whose folder is `/` or `""`

**Today.** `"/".rstrip("/") + "/"` is `"/"`, which every absolute path starts with. Measured: the tool
server allows `/Users/victim/x.py`.

**Must.** Refuse. `require_folder` raises `Unset`, and the registry never emits a value that is only
slashes.

**Test.** `test_tools_fence.py::test_no_wildcard_path_is_ever_accepted`, four spellings: `"/"`, `""`,
`"//"`, `"///"`.

---

### `[E-3]` A write whose target cannot be parsed

**Input.** `OPTIMIZE main.s.t ZORDER BY (a)` — a statement with no `TABLE` keyword.

**Today.** `scope.sql_targets` does not capture it, so `check_sql` falls through to *"this write's target
could not be identified"* → `ASK`. **The app is right.** The tool server's `_TARGETS` also fails to
capture it and returns *"write blocked: could not identify a write target"* — also right, for a different
reason.

**Must.** Stay `ASK` on both sides. This case is in the list because it is the one place the two runtimes
agree by *accident* (two different fallbacks landing on the same answer) and a refactor could easily
remove one of them.

**Test.** Already in `test_fence_parity.py::SQL_CASES` for `OPTIMIZE main.other.t`; add the `ZORDER BY`
spelling.

---

### `[E-4]` A path that escapes by `..`

**Input.** `/Users/me/agent_scratch/../someone_else/x.py`.

**Today.** Correct on both sides: `_inside` splits and rejects a `..` segment
(`scope.py:89-90`), and `_check_path_scope` does the same with a comment naming spec 013's own `E-27`.

**Must.** Stay. This is the case the parity table was built for, and it is the reason the table exists.

**Test.** `test_fence_parity.py::PATH_CASES`, already present. Do not touch.

---

### `[E-5]` A hook that would widen the fence

**Input.** A workspace hook `then: run` with an argument outside the fence, or a `when:` that matches
everything.

**Today.** No hooks.

**Must.** A hook is evaluated **after** the fence, so it can only narrow. A `then: run` action is refused
unless an administrator set it, and its arguments are fenced like any tool's. The refusal names the rule.

**Test.** `test_hooks.py::test_a_hook_cannot_widen_the_fence` and `::test_run_action_needs_an_admin`.

---

## Group B · The payload

### `[E-6]` A tool result exactly at the limit, and one byte over

**Input.** A payload whose serialised form is exactly `MAX_CHARS`, and one that is one character longer.

**Today.** At the limit: returned whole. One over: a byte-slice, which is invalid JSON.

**Must.** At the limit: returned whole, `next_offset: null`. One over: a window of whole items, with
`total` and `next_offset`. The boundary is tested at `limit-1`, `limit`, `limit+1`, because an off-by-one
in a truncation is the difference between "all" and "nearly all" and nothing says which.

**Test.** `test_payload_window.py::test_the_boundary`.

---

### `[E-7]` A single item larger than the whole budget

**Input.** One table description of 40 000 characters against a 6 000-character budget.

**Today.** A slice: the object is cut in half, unparseable.

**Must.** Return **that one item, unbounded**, with `returned: 1, total: 1, next_offset: null`, and a
`truncated: true` note. An empty window with `next_offset: 0` would loop forever; a slice is unparseable.
Returning the oversized item is the only answer that terminates and tells the truth.

**Test.** `test_payload_window.py::test_one_item_larger_than_the_budget_terminates`.

---

### `[E-8]` A write mode changed mid-turn

**Input.** A user switches `fenced` → `read-only` while a turn is streaming.

**Today.** No modes.

**Must.** The mode the turn started with applies to that turn. The switch applies to the **next** turn,
exactly as a model switch does (`orchestrator.py:680-709`, "the running turn is never retargeted"). The
UI says which mode the running turn has.

**Test.** `test_write_mode.py::test_a_switch_during_a_turn_applies_to_the_next_turn`.

---

## Group C · Durability

### `[E-9]` A restart while a turn is streaming, and one while idle

**Input.** `SIGTERM` during a turn; `SIGTERM` with three idle conversations.

**Today.** Both become `blocked + requiresResume`.

**Must.** The first becomes `blocked + requiresResume` with the interrupted turn listed; the second
becomes `ready`. `[E-9]` is in this list because the *pair* is the case: a fix that only handles one of
them is the defect.

**Test.** `test_restart_disposition.py`, two cases, one snapshot fixture each.

---

### `[E-10]` An evicted session is read

**Input.** `GET /api/sessions/{id}` for a conversation whose projection was evicted 11 minutes ago.

**Today.** `404 no such session`, although `agent.session_snapshot` has the row.

**Must.** Rehydrate from the snapshot and answer `200`, with `requiresResume: true` if the agent is not
running.

**Test.** `test_api.py::test_an_evicted_session_still_reads`.

---

### `[E-11]` A checkpoint write fails

**Input.** The database refuses the snapshot upsert (a lock timeout) while the event append succeeded.

**Today.** Impossible: they are one statement in one lock.

**Must.** The turn **continues**. The journal has the event; the projection is stale by up to 49 events;
the next checkpoint or the next boot rebuilds it. A checkpoint is a cache, and a cache that fails must not
fail work. The failure is logged once, not per event.

**Test.** `test_journal_cost.py::test_a_failed_checkpoint_does_not_fail_the_turn`.

---

### `[E-12]` An instruction file that contradicts the fence

**Input.** `AGENTS.md` containing *"you may write to /Shared"*.

**Today.** No instructions are read.

**Must.** The fence rules are appended **last** and win. The agent is told both; the rules block says
which one is enforced. If it tries, the tool server refuses and the refusal is the sentence in the
transcript.

**Test.** `test_instructions.py::test_the_scope_block_is_always_last`, plus a tool-level assertion that the
write is refused regardless of the prompt.

---

### `[E-13]` A turn's budget is exhausted mid-turn

**Input.** A 40 k-token answer against a 30 k budget.

**Today.** No budget.

**Must.** The **next** turn is blocked before it calls the model, with the number. The current turn is
allowed to finish, because stopping mid-answer loses work and the cost is already spent. `[R-24]` states
"before a turn is claimed", and this is why that word is precise.

**Test.** `test_budget.py::test_a_turn_that_exceeds_the_budget_is_blocked_before_the_model_call`.

---

### `[E-14]` Boot with 10 000 conversations

**Input.** A long-lived deployment.

**Today.** `restore()` reads every snapshot and builds a `Live` for each — 10 000 objects, each holding
its turns and calls.

**Must.** Read rows for the open+recent set only (a `LIMIT` and an `ORDER BY last_seen`), and rehydrate
older ones lazily on read (`[E-10]`). The number is stated in the code, not discovered in an incident.

**Test.** `test_journal_cost.py::test_boot_reads_a_bounded_set`.

---

## Group D · The stream and the browser

### `[E-15]` A coalesced delta and a tool event in the same millisecond

**Input.** The model emits text and requests a tool in the same chunk window.

**Today.** Every event is separate, so ordering is the arrival order.

**Must.** The coalescer flushes **before** any non-delta event. A tool card must never appear above the
text that requested it. This is the ordering bug a batching change introduces, and it is why
`flush()` is called on more than the timer.

**Test.** `test_delta_coalescing.py::test_a_tool_event_flushes_pending_text`.

---

### `[E-16]` A hook that runs a program, and the program hangs

**Input.** `then: run` with `ruff`, and `ruff` blocks on stdin.

**Today.** No hooks.

**Must.** A timeout (5 s), a kill, and a refusal that says the hook timed out — the turn continues.
A hook may not block a turn indefinitely, and may not read the user's token (it inherits the tool server's
environment, which holds a token **path**, not the token).

**Test.** `test_hooks.py::test_a_hanging_hook_is_killed`.

---

### `[E-17]` Two browser tabs on the same session, one at an older cursor

**Input.** Tab A at `after=900`, tab B at `after=1200`.

**Today.** Correct: `StreamState` treats a 409 ("cursor ahead") as terminal and the user reopens from 0
(`stream.ts:26-34`).

**Must.** Unchanged. `[E-17]` is in the list because `[R-14]` multiplies the number of cursors per user,
and the 409 path is the one that must keep working.

**Test.** `stream.test.ts` already covers it. Add an integration case in `[S-5]`'s scene.

---

### `[E-18]` A thread tab whose session is archived by the reaper

**Input.** Five tabs open; the reaper archives the one nobody has touched in 30 minutes, which is not the
active tab.

**Today.** Impossible: one tab.

**Must.** That tab's stream gets a 404, `StreamState.closed("not-found")` renders *"The server no longer
has this session"*, and the tab offers *"Start a new conversation"*. It does not silently disappear.

**Test.** `threads.test.ts` — a cursor in `closed` state is rendered, not dropped.

---

## Group E · Search, fork, and the proposal

### `[E-19]` Search matches a redacted secret

**Input.** A user pasted an API key; `redact_labelled` masked it in the stored prompt; the user searches
for the key.

**Today.** No search.

**Must.** No match, because the **stored** text is redacted and the index is over stored text. This is
correct and needs saying: a search that could find a redacted secret would undo the redaction.

**Test.** `test_search.py::test_search_cannot_find_a_redacted_secret`.

---

### `[E-20]` Fork from a turn that ended `blocked`

**Input.** Fork at turn 4, which is `blocked` with an unproven requirement.

**Today.** No fork.

**Must.** Allowed. The new session contains turns 1–4 including the `blocked` state and its evidence gap,
because that is what happened. The new session is `ready` and can continue. A fork is a copy of history,
not a "clean" one.

**Test.** `test_fork.py::test_a_fork_keeps_a_blocked_turn_as_it_was`.

---

### `[E-21]` A proposal that arrives while the document is dirty

**Input.** The agent proposes an edit to a notebook the user has unsaved changes in.

**Today.** `minimalChange` maps a remote edit onto an open document, which would overwrite the user's
text.

**Must.** A proposal is **not applied** to a dirty document. It is held as a proposal, and the cell shows
*"the agent proposed a change; save or discard your edit first"*. This is `[R-22]`'s hardest case and the
reason the proposal is a separate type rather than an edit.

**Test.** `proposal.test.ts::test_a_dirty_document_holds_the_proposal`.

---

### `[E-22]` A proposal is accepted, but the version changed meanwhile

**Input.** `Keep` on a proposal computed against version `v3`, while the document is now `v4` (another
tab, or the agent wrote it).

**Must.** Refuse with the same contract `POST /workspace/save` already uses: `409` with both versions, and
the proposal is recomputed. Reusing that contract is the DRY answer — it exists (`routers/api.py:764-800`)
and has a test.

**Test.** `proposal.test.ts` and `test_workspace_write.py` (the shared contract).

---

## Group F · Models and cost

### `[E-23]` A model switch between a turn's pin and its answer

**Input.** The user switches the model while turn 4 streams.

**Today.** Correct: the pin is written before the prompt and never rewritten; the switch applies to turn
5 (`orchestrator.py:680-709`, `_pin_turn`). `model_facts` reports `switchAtTurn`.

**Must.** Unchanged, and `[R-24]`'s budget must be summed per pin, not per session's *current* model —
otherwise a switch would re-price history.

**Test.** `test_budget.py::test_a_switch_does_not_reprica_history` and the existing `model_facts` tests.

---

### `[E-24]` A model with no declared limits

**Input.** A discovered serving endpoint whose `max_output` is unknown.

**Today.** `LimitEvidence.DEFAULT`, and the catalogue says so (`limits.py`, `limits.evidence`). The
comment is explicit: *"a model is unusable after the user waited, so each row records whether its limits
were measured, documented or default."*

**Must.** Unchanged. `[E-24]` is listed because an assessment that proposes a budget must not quietly
widen it: a budget computed from a *default* limit can block a turn that would have worked.

**Test.** The existing `test_llm_domain.py` limit cases; `[R-24]` adds one asserting a default-limit model
is excluded from a strict budget rather than priced wrongly.

---

## Group G · The comparison's own claims

### `[E-25]` Genie Code ships something this assessment says it lacks

**Input.** A Genie feature lands after 9 November 2026.

**Must.** The comparison table in [03](03-comparison-genie-code.md) is dated and marked `[doc]`. A row
that becomes wrong is corrected with a new date, never silently. This is a process edge case, and it is
here because the rest of the document's credibility rests on the dates being real.

**Test.** None possible. Mitigation: every source has its date inline.

---

## Group H · The state machines, at their edges

The six findings `F-12`–`F-17` are each an edge of a machine, and each is recorded as a case so the fix
has something to pass.

### `[E-26]` A Repair button on a run that never ran

**Input.** A task `SKIPPED` because an upstream dependency failed, carrying `result_state = FAILED`.
`can_repair` checks `is_terminal(life_cycle)` and the result, so it answers `true`.

**Today.** Measured: `SKIPPED + FAILED → can_repair == True`, and the same for `INTERNAL_ERROR`.

**Must.** Refuse. `SKIPPED` means the platform never started it; there is nothing to re-run. Repair
belongs on a **terminated** run whose own tasks failed.

**Why it is deferred to phase 3 and not fixed with `[R-28]`.** It needs a product decision — whether
"repair" on a partially failed parent run should re-run the skipped children — and neither the wrong
button nor the right one can lose data. Recorded, not forgotten.

**Test.** `test_jobs_domain.py::test_a_skipped_run_offers_no_repair`.

---

### `[E-27]` A run that "succeeded with failures" is painted bad and cannot be repaired

**Input.** `TERMINATED + SUCCESS_WITH_FAILURES` — the platform's word for a job whose parent succeeded
because its children were allowed to fail.

**Today.** `tone("succeeded with failures") == "bad"` (correct: a person reading a dashboard treats it as
not-ok) but `can_repair("SUCCESS_WITH_FAILURES", "TERMINATED") == false`, because `can_repair` allows
only `FAILED` and `TIMEDOUT`.

**Must.** Decide, and write the decision down. The two coherent options are: (a) keep the tone `bad` and
allow a repair, because the failed children are exactly what a repair re-runs; or (b) keep no repair and
soften the tone to `quiet`, because the run is a success by the platform's contract. **This set does not
choose**, because it is a product question, not a defect with one right answer — but leaving it
undecided is a state word and a control that contradict each other, which is the class `F-14` belongs to.

**Test.** `test_jobs_domain.py::test_succeeded_with_failures_is_coherent` — whichever option is chosen,
assert the tone and the repair button agree.

---

## The matrix

| # | Case | Today | Severity | Phase |
|---|---|---|---|---|
| `[E-1]` | no schema | **opens the fence** | critical | 1 |
| `[E-2]` | folder `/` or `""` | **opens the fence** | critical | 1 |
| `[E-3]` | unparseable SQL target | correct by accident | low | 1 (pin it) |
| `[E-4]` | `..` escape | correct | — | do not touch |
| `[E-5]` | hook widens the fence | n/a | high | 4 |
| `[E-6]` | payload at the boundary | invalid JSON over | high | 1 |
| `[E-7]` | one item > budget | unparseable | high | 1 |
| `[E-8]` | mode changes mid-turn | n/a | medium | 2 |
| `[E-9]` | restart, mid-turn vs idle | both blocked | high | 2 |
| `[E-10]` | evicted session read | 404 | high | 2 |
| `[E-11]` | checkpoint fails | n/a | medium | 1 |
| `[E-12]` | instruction contradicts fence | n/a | high | 2 |
| `[E-13]` | budget exhausted mid-turn | n/a | medium | 2 |
| `[E-14]` | boot with 10 k sessions | O(all) | medium | 2 |
| `[E-15]` | delta + tool, same ms | n/a | high | 1 |
| `[E-16]` | hook hangs | n/a | medium | 4 |
| `[E-17]` | two tabs, different cursors | correct | — | verify |
| `[E-18]` | a thread archived under the user | n/a | medium | 3 |
| `[E-19]` | search finds a redacted secret | n/a | high | 3 |
| `[E-20]` | fork at a blocked turn | n/a | low | 3 |
| `[E-21]` | proposal on a dirty document | n/a | high | 3 |
| `[E-22]` | accept on a stale version | contract exists | medium | 3 |
| `[E-23]` | switch during a pinned turn | correct | — | verify |
| `[E-24]` | model with default limits | correct | medium | 2 |
| `[E-25]` | Genie ships a new feature | dated | — | process |
| `[E-26]` | repair on a `SKIPPED` run | wrongly offered | low | 3 |
| `[E-27]` | `SUCCESS_WITH_FAILURES` tone vs repair | contradictory | low | 3 |

**Nine of these are "correct today, and a change could break it"** (`[E-3]`, `[E-4]`, `[E-11]`,
`[E-17]`, `[E-20]`, `[E-23]`, `[E-24]`, plus both halves of `[E-9]`). They are in the list because the
plan's risk is not only what is broken; it is what is working and unwatched.

Next: [13 · Roadblocks](13-roadblocks.md).
