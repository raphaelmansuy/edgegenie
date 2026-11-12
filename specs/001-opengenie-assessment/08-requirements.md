[Index](README.md) · prev: [07 Diagrams](07-diagrams.md) · next: [09 Seven lenses](09-lenses.md)

# 08 · Requirements

Every `[R-n]` is defined here once and cited everywhere else. A requirement is only in this list if it
has **a test** in [11](11-implementation-plan.md) and **a stated level of proof** in
[15 §3.1](15-e2e-plan.md) — a scene where a scene proves
something a unit test cannot, and an explicit "unit-only, and here is why" where it does not. A
requirement with neither is a wish.

Each carries: **the statement** (falsifiable), **why** (the finding or gap it closes), **the gate**
(what proves it), **the phase**, and **the scene** or the reason there is none.

---

## Phase 1 — make the promises true

Nothing in phases 2–4 starts until every `[R-1]`–`[R-8]` and `[R-12]` is green. They are safety and
cost, and both compound.

### `[R-1]` No fence means no write

> **Statement.** A session with no writable schema **refuses** every SQL write, a session with no
> writable folder **refuses** every path write, and neither can be configured into a wildcard. A
> refusal names which of the two is missing and what to do.
>
> **Why.** `F-1`: `_check_sql_scope` returns `None` for empty `WRITE_SCHEMAS`, and
> `folder.rstrip("/") + "/"` turns `"/"` and `""` into `"/"`, a prefix every path matches. Measured:
> the tool server allows a write the app says must ASK.
>
> **Gate.** `tests/test_fence_parity.py` gains an `EMPTY_CASES` table — empty schema, empty folder,
> `"/"`, a folder of only slashes — asserted against **both** runtimes, with the tool server's answer
> required to be *refuse*. Plus `tests/test_tools_fence.py::test_no_wildcard_path_is_ever_accepted`.
>
> **Phase** 1. **Closes** `[G-0]`, `[G-27]`'s premise.
> **Scene.** `[S-1]` — end to end.

---

### `[R-2]` The parity table covers the empty cases

> **Statement.** `tests/test_fence_parity.py` contains at least one row per **fence dimension**
> (path, SQL target, job name, app name, instance name) in which the dimension is **unset**, and the
> tool server's verdict for every such row is refusal.
>
> **Why.** The table is the guard that was supposed to prevent `F-1`, and it has no empty-case row. The
> guard was right about what it measured; it measured the easy half.
>
> **Gate.** A test that enumerates `Scope`'s five fields and fails if a field has no unset row:
> `test_every_fence_dimension_has_an_unset_row`.
>
> **Phase** 1.
> **Scene.** `[S-1]` — end to end.

---

### `[R-3]` A truncated tool result is valid JSON with an explicit window

> **Statement.** For every tool that can exceed the character budget, the returned text is
> **parseable JSON** and either contains the whole payload or carries
> `{"returned": n, "total": N, "next_offset": m}`. No response is a byte-slice of a serialised object.
>
> **Why.** `F-2`: measured `json.loads(_trim(payload))` → `JSONDecodeError: Invalid control character
> at char 6000`. The exact defect class the repository documents at `docs/genie-code-replacement-spec.md`
> §4.8/§4.9 and fixed for two tools, never fixed for the shared path.
>
> **Gate.** A property test: for 200 synthetic payloads of every tool's shape, `json.loads` succeeds
> and `returned + next_offset` arithmetic is consistent. Plus a test that pages a 200-row list from
> `next_offset` and reconstructs the original array exactly.
>
> **Phase** 1. **Closes** `[G-0]` second half.
> **Scene.** `[S-2]` — end to end.

---

### `[R-4]` The documentation and the child's environment agree

> **Statement.** Either the agent child does **not** receive `DATABRICKS_TOKEN`, or
> `docs/08-architecture.md` and `docs/09-security.md` state that it does and name the deny-lists as the
> boundary. Whichever is chosen, **a test asserts it**, so the statement cannot drift again.
>
> **Why.** `F-3`: `orchestrator.py:578` sets the token on the child, and two pages say it does not.
> The deny-lists make the current design safe; the *claim* is what is false, and a security reviewer
> who finds one false claim stops trusting the document.
>
> **Gate.** `tests/test_agent_isolation.py` gains `test_the_child_environment_matches_the_documented_contract`:
> if the proxy design is in place, assert no token; otherwise assert the token **is** present (so the
> doc's claim is the one that must change) and that both deny-lists are intact.
>
> **Phase** 1 (the documentation and the test). The proxy is a phase-4 option, recorded in `[RB-4]`.
> **Scene.** none: this requirement is unit-only, and [15 §3.1](15-e2e-plan.md) says why.
> **Closes** `[G-29]`.

---

### `[R-5]` The snapshot is a checkpoint, not a per-event write

> **Statement.** A committed event appends to `agent.session_event` and **does not** write
> `agent.session_snapshot`, except when the checkpoint interval (50 events or 5 s, whichever is first)
> is reached. A restart replays from `checkpoint_seq` and yields the same projection as before.
>
> **Why.** `F-4`: `commit()` writes the whole snapshot per event. Measured ≈1.8 GB per turn for a
> 60 k answer, ≈18 GB per ten turns. O(n²) in answer length.
>
> **Gate.** `tests/test_journal_cost.py`, a new file:
> * `test_a_thousand_deltas_write_one_snapshot` — count `INSERT … session_snapshot` via a fake cursor;
> * `test_replay_from_checkpoint_equals_replay_from_zero` — the same projection from either start;
> * `test_bytes_written_per_turn_is_below_one_megabyte` — a budget assertion, not a comment.
>
> **Phase** 1. **Closes** `[G-23]`.
> **Scene.** `[S-3]` — end to end.

---

### `[R-6]` Deltas are coalesced at the source

> **Statement.** Consecutive `message.delta` (and `thought.delta`) events are accumulated and emitted
> at most once per 100 ms or 2 KB, whichever is first, and **always** at the end of a turn. The
> accumulated text is identical to the concatenation of the original deltas.
>
> **Why.** `F-4` and `F-5`: 15 000 events per answer is 15 000 commits and 15 000 string copies. The
> reduction is ~2 orders of magnitude and it fixes the server and the tab with one change.
>
> **Gate.** `tests/test_delta_coalescing.py`: text identity, boundary flush, cancellation flush, and a
> counting test that a 60 000-character answer produces ≤ 600 `message.delta` events.
> `web/src/domain/events.test.ts` keeps its `append` tests, since the reducer is unchanged.
>
> **Phase** 1. **Closes** `[G-23]`, `[G-5]`'s cost premise.
> **Scene.** `[S-3]` — end to end.

---

### `[R-7]` Sessions sort by creation time

> **Statement.** `GET /api/sessions` returns sessions newest-first by `created_at`, with the id as a
> deterministic tie-breaker. The order is stable across identical requests.
>
> **Why.** `F-6`: `sorted(key=lambda s: s.id)` over `uuid4().hex[:16]`, while the docstring says
> "newest first". Measured: five random ids are not in descending order.
>
> **Gate.** `tests/test_api.py::test_sessions_are_newest_first` — create three with controlled clocks,
> assert the order, call twice, assert the same.
>
> **Phase** 1. **Closes** `[G-28]`.
> **Scene.** `[S-4]` — end to end.

---

### `[R-8]` Dead fence code is either wired or retired

> **Statement.** Every function in `api/domain/scope.py` is reachable from a production call site, or
> is deleted. `scope.py` contains no function whose only caller is a test.
>
> **Why.** `F-7`: `check_sql`, `check_job`, `check_app`, `check_instance` have no production caller,
> while `tests/test_fence_parity.py` says the fence exists "in two runtimes". The request path has one,
> and it is the one `F-1` shows to fail open.
>
> **Gate.** `tests/test_dead_code.py::test_scope_has_no_test_only_function` — a reachability assertion
> built from `rg`, not from a hand-kept list.
>
> **Phase** 1. **Closes** `[G-27]`. **The decision is `[RB-5]`.**
> **Scene.** none: this requirement is unit-only, and [15 §3.1](15-e2e-plan.md) says why.

---

### `[R-12]` The ledger read is per session

> **Statement.** `read_ledger(session_id)` reads one file. No request parses a directory.
>
> **Why.** `F-11`: `/api/infra/ledger` globs and parses every `*.jsonl` on every request, then the
> client filters. Cost grows with total history.
>
> **Gate.** `tests/test_infra_routes.py::test_ledger_reads_only_its_own_file` — a spy on file opens.
>
> **Phase** 1. **Closes** `[G-28]`.
> **Scene.** none: this requirement is unit-only, and [15 §3.1](15-e2e-plan.md) says why.

---

### Where the tests actually live

The plan named **one file per requirement**; the implementation consolidated them, and this is the record
so a reviewer looking for `test_budget.py` is not left guessing:

| Planned | As built | Why |
|---|---|---|
| `test_restart_disposition.py`, `test_compaction.py`, `test_budget.py`, `test_instructions.py` | **`test_phase2.py`** (56) | four pure modules whose tests share one import block and one vocabulary; four files of six tests each is more navigation for no isolation |
| `test_skills.py` | **`test_skills_and_sheets.py`** (17) | `[R-18]` and `[R-21]` were built together and share the "three sources / real file" fixtures |
| `test_search.py`, `test_fork.py` | **`test_search_and_fork.py`** (19) | both are operations on one log, and both use the same event fixtures |
| `test_hooks.py`, `test_second_server.py`, `test_docsearch.py`, `test_schedule.py`, `test_subagent.py` | **`test_phase4.py`** (44) | one module, five policies, all "a narrowing" |
| `threads.test.ts`, `proposal.test.ts` | **`phase3.test.ts`** (25) | two pure client modules, one describe block each |

Every requirement still names a test that fails without it. **The count is lower than the plan; the coverage
is not.**

---

## Phase 1b — the state machines, made total

These six come from exhausting every machine ([02 §8](02-assessment-opengenie.md#8--six-state-machine-defects-proved-by-exhaustion)). Two
are correctness (`[R-26]`, `[R-28]`), one is a false negative in the product's headline promise
(`[R-31]`), three are honesty of the vocabulary (`[R-27]`, `[R-29]`, `[R-30]`). All six are small, and all
six are in phase 1 because they are cheap and they are the kind of defect that makes a reviewer stop
trusting a state word.

### `[R-26]` A terminal turn cannot change

> **Statement.** `Turn.finish()` refuses a transition out of a terminal status, exactly as `start()`
> refuses a transition out of a non-startable one. The timeout path reads the current status before
> finishing and does nothing when the turn already settled.
>
> **Why.** `F-12`: measured, `COMPLETED.finish(INTERRUPTED)` succeeds, and the timeout handler at
> `orchestrator.py:947` can do exactly that on a settle/timeout race. Two conflicting records then exist
> for one turn.
>
> **Gate.** `tests/test_domain.py::test_a_terminal_turn_cannot_change` — the full 8×5 matrix, asserting
> every out-of-terminal transition raises; plus `test_orchestrator_cannot_interrupt_a_settled_turn`,
> which drives the race with a fake clock.
>
> **Phase** 1. **Scene.** none: an 8×5 matrix is exactly the kind of thing a unit test proves and a
> screenshot cannot.

### `[R-27]` Every declared state is reachable, or it is not declared

> **Statement.** For each of the four state machines with a closed union (`StreamState`, `RunState`,
> `TurnStatus`, `SessionStatus`), a test computes the reachable set from the initial state and fails when
> a declared member is unreachable, naming it.
>
> **Why.** `F-13`: `closed: "offline"` is declared, has copy, and `afterFailure` cannot produce it.
> Measured by BFS over every `(status, online)` pair.
>
> **Gate.** `stream.test.ts::test_every_declared_state_is_reachable` (the BFS that produced the finding),
> plus the same shape for `RunState` and `TurnStatus` in `test_domain.py`.
>
> **Phase** 1. **Scene.** none.

### `[R-28]` A run's word comes from the field that is honest for its phase

> **Statement.** While a run's life cycle is active, the word comes from the **life cycle**; only a
> terminal life cycle lets `result_state` decide. A word and a control that contradict each other (a
> green "succeeded" beside an enabled Cancel) cannot both be on screen.
>
> **Why.** `F-14`: 24 of 60 `ACTIVE × RESULT` combinations produce a terminal word with
> `can_cancel == true`.
>
> **Gate.** `tests/test_jobs_domain.py::test_an_active_run_never_reads_as_finished` — the full grid,
> asserting `word ∈ ACTIVE_WORDS` whenever `is_active`, and `not (terminal word and can_cancel)`.
> The existing `jobs-table.json` fixture gains the grid so the TypeScript mirror is held to it too.
>
> **Phase** 1. **Scene.** `[S-16]`: a `TERMINATING` run photographed (see [15](15-e2e-plan.md)).

### `[R-29]` `QUEUED` waits; an unknown state is not a failure

> **Statement.** `QUEUED` is a waiting state. A warehouse state that is not known-waiting,
> known-success, known-cancelled or known-failed produces a **distinct** outcome with the state's own
> name in the sentence — never `FAILED`.
>
> **Why.** `F-15`: measured, `QUEUED → failed` with the error text *"the warehouse reported QUEUED"*, and
> no message at all.
>
> **Gate.** `tests/test_cellrun.py::test_queued_is_a_wait` and
> `::test_an_unknown_state_is_not_a_failure`, asserting the outcome's `state` is not `RunState.FAILED`
> and that the sentence contains the platform's word.
>
> **Phase** 1. **Scene.** none.

### `[R-30]` A reason must be the reason

> **Statement.** `retention()` reports `KEPT_UNKNOWN_STATE` for an unrecognised state regardless of
> refcount, so `KEPT_REFERENCED` means only "a turn references it".
>
> **Why.** `F-16`: measured, an unknown state with `refcount > 0` reports `KEPT_REFERENCED`.
>
> **Gate.** `tests/test_blob_retention.py::test_the_reason_for_an_unknown_state_is_its_state` — the
> unknown-state row at refcount 0, 1 and 5, asserting the disposition is the same at every refcount.
>
> **Phase** 1. **Scene.** none.

### `[R-31]` Completed work is not a gap

> **Statement.** When a requirement's gap is filled by a **completed** tool call whose name maps to that
> requirement, the turn is not `blocked`. The mapping is a closed table (notebook write → write,
> `run_sql`/`run_notebook` → run, `describe_table` → verify), and it may only *add* evidence; it can
> never mark a call verified when the call did not complete.
>
> **Why.** `F-17`: measured, two completed calls plus a correct prose answer ends `blocked` after two
> audits.
>
> **Gate.** `tests/test_supervisor.py::test_completed_work_without_a_table_is_not_blocked`, plus the
> negative: `::test_an_incomplete_call_still_blocks`, and `[E-6]`'s case (a real call, a fabricated
> summary) must still pass as verified, because the fix touches only the *missing row* condition.
>
> **Phase** 1. **Scene.** `[S-17]`: a turn whose answer omits the table, photographed as `completed`.

---

## Phase 2 — the day-two asks

### `[R-9]` A session has a write mode

> **Statement.** A session is created with one of `read-only`, `fenced` (default), `ask`. The tool
> server is started with the mode. `read-only` refuses every mutating tool with a reason;
> `fenced` behaves as today; `ask` returns a structured "needs human" result that the app turns into an
> approval. The mode is on the session detail and in the session's snapshot.
>
> **Why.** `F-8`: `NBMCP_ALLOW_WRITES=1` is a constant, so the tool server's own docstring ("mutating
> tools are behind the flag … mirrors Genie Code's approval modes but is enforced by the server")
> describes a mode the product never uses.
>
> **Gate.** `tests/test_write_mode.py` — each mode × each mutating tool, asserting refusal, execution
> or approval. `[E-8]` covers the mode change during a turn.
>
> **Phase** 2. **Closes** `[G-26]`.
> **Scene.** `[S-12]` — end to end.

---

### `[R-10]` A restart distinguishes mid-turn from idle, and an evicted session rehydrates

> **Statement.** On boot, a session that had a turn in flight becomes `blocked + requiresResume`; a
> session that was idle becomes `ready` with no agent process, provisioned on the next message. A
> `GET` for a session whose projection was evicted rehydrates it from `agent.session_snapshot` instead
> of returning 404.
>
> **Why.** `F-9`: `restore()` marks **every** non-archived session `requires_resume`, and
> `evict_archived()` `pop`s the projection while the row survives, so the read is a 404.
>
> **Gate.** `tests/test_phase2.py` (pure rule) plus `tests/test_api.py::test_an_evicted_session_still_reads`.
>
> **Phase** 2. **Closes** `[G-24]`.
> **Scene.** `[S-4]` — end to end.

---

### `[R-11]` Compaction exists and is recorded

> **Statement.** When a conversation's estimated context crosses a threshold, history is summarised,
> a `session.compacted` event is committed with the summary and the range it replaced, and the
> projection carries the summary so a replay reconstructs it. `MAX_TURNS` reads
> `settings.max_turns_per_session`.
>
> **Why.** `F-10`: `session.compacted` is in the 27-type vocabulary and emitted by nobody, and
> `settings.max_turns_per_session` has no reader.
>
> **Gate.** `tests/test_phase2.py` — the plan is pure (`compaction.plan(turns, budget) -> Plan`),
> so what is shed and what is kept is asserted without a model. Plus `test_max_turns_reads_the_setting`.
>
> **Phase** 2. **Closes** `[G-25]`.
> **Scene.** `[S-3]` — end to end.

---

### `[R-17]` Workspace instructions and `AGENTS.md` are read, and labelled

> **Statement.** Before a turn, the app reads — as the signed-in user — the workspace instructions,
> the user's instructions, and `AGENTS.md` files found by walking up from the session's folder. Each is
> injected as a block labelled with its **source** and **author**. The session's fence rules are
> appended **last** and override all of them. An unreadable file is reported in the transcript, never
> silently dropped.
>
> **Why.** `[G-5]`, `[C13]`, `[C14]`: Genie Code discovers `AGENTS.md` and offers user and workspace
> instructions. OpenGenie *writes* an `AGENTS.md` (`agent_config.py:170-182`) and reads none.
>
> **Gate.** `tests/test_phase2.py` — precedence, labelling, the unreadable case, the override
> case. `[E-12]` covers a file that contradicts the fence.
>
> **Phase** 2. **Closes** `[G-5]`.
> **Scene.** `[S-8]` — end to end.

---

### `[R-18]` User and workspace skills are loadable

> **Statement.** `dbx_skill()` with no name lists the built-in four **plus** the user's
> (`~/.assistant/skills/`) and the workspace's (`Workspace/.assistant/skills/`), each labelled by
> source. A skill body is read on demand. A workspace skill cannot be edited by a non-administrator.
>
> **Why.** `[G-6]`, `[C15]`: OpenGenie has the *mechanism* (progressive disclosure through one tool,
> `tools/…:2488-2506`) and none of the authoring that makes it useful.
>
> **Gate.** `tests/test_skills_and_sheets.py` — the index, the labels, the read, the write refusal.
>
> **Phase** 2. **Closes** `[G-6]`.
> **Scene.** `[S-8]` — end to end.

---

### `[R-21]` Spreadsheets are a text-bearing attachment family

> **Statement.** `.xlsx` and `.xls` are accepted, magic-byte checked, and converted to CSV text at
> resolution time with a cap and an explicit `truncated` note.
>
> **Why.** `[G-12]`, `[C18]`: Genie Code accepts `.xlsx`/`.xls`; OpenGenie's family table
> (`domain/blob.py:228-236`) has image, text, notebook, PDF and `OTHER`.
>
> **Gate.** `tests/test_blob_rules.py` — a real minimal xlsx fixture, the cap, the refusal for a
> corrupt file.
>
> **Phase** 2. **Closes** `[G-12]`.
> **Scene.** none: this requirement is unit-only, and [15 §3.1](15-e2e-plan.md) says why.

---

### `[R-24]` A conversation has a spend ceiling, and it stops work

> **Statement.** A session may carry a token budget. Before a turn is claimed, `budget.decide()` answers
> `allow` or `blocked` with the number and the limit. Usage is summed from the turn pins, not
> re-counted. A blocked turn does not call the model.
>
> **Why.** `[G-20]`, `[C33]`: Genie's budgets are a ceiling it says are not a cap. The turn pins
> (`llm.llm_turn_model`) already record exactly what a turn cost, so a real cap is a pure function away.
>
> **Gate.** `tests/test_phase2.py` — pure decisions, the boundary, the restart, an unset limit.
>
> **Phase** 2. **Closes** `[G-20]`.
> **Scene.** `[S-13]` — end to end.

---

## Phase 3 — the surface

### `[R-14]` Parallel conversations

> **Statement.** N sessions can be open at once, each with its own live stream and its own reducer
> state, shown as a tab strip. Switching a tab does not cancel, restart or re-provision a turn. A tab
> shows `working` / `needs you` from events it is not currently displaying.
>
> **Why.** `[G-1]`, `[C2]`, and the summit blog's own user quote: *"I run upwards of 15 parallel
> threads … managing all of that across tabs is one of the biggest sources of friction."*
>
> **Gate.** `web/src/domain/phase3.test.ts` (pure: which tab is working, from a map of cursors) plus a
> scene `[S-5]` with two live turns. The server needs **no** change: a stream is a cursor.
>
> **Phase** 3. **Closes** `[G-1]`.
> **Scene.** `[S-5]` — end to end.

---

### `[R-15]` Search inside conversations

> **Statement.** A query returns the conversations that contain it, with the matching turn and a
> snippet, and opens at that turn. The search is over committed events.
>
> **Why.** `[G-2]`, `[C4]`: the rail searches `sessionLabel(s) + s.folder`
> (`web/src/domain/sessions.ts:47-52`).
>
> **Gate.** A `tsvector` + GIN index migration and `tests/test_search_and_fork.py`; the client side in
> `sessions.test.ts`. Scene `[S-6]`.
>
> **Phase** 3. **Closes** `[G-2]`.
> **Scene.** `[S-6]` — end to end.

---

### `[R-16]` Fork and regenerate

> **Statement.** A conversation can be forked from a turn: the new session's journal contains the
> events from `seq 1` to that turn's `turn.completed`, and nothing else. It has its own id, its own
> fence and its own model pin history. Regenerate is a fork at `n-1` plus a resubmit of turn `n`.
>
> **Why.** `[G-4]`, `[C6]`: Genie Code branches a chat, `/btw`, and edits an earlier message. Here it
> is a copy of a prefix of an append-only log — the cheapest possible implementation of a hard feature.
>
> **Gate.** `tests/test_search_and_fork.py` — the prefix, the isolation, the pin history, the fence of the new
> session. Scene `[S-11]`.
>
> **Phase** 3. **Closes** `[G-4]`.
> **Scene.** `[S-11]` — end to end.

---

### `[R-22]` A proposed edit is a diff and a decision

> **Statement.** When the agent proposes a change to an open notebook, the notebook shows a per-cell
> proposal with the agent's reason; `Keep` writes it through the fence, `Reject` discards it and says
> the proposal was discarded. The original is untouched until `Keep`.
>
> **Why.** `[G-15]`, `[C24]`. Spec 006 §4 calls it "the largest remaining notebook gap" and defers it;
> this set schedules it.
>
> **Gate.** `web/src/domain/phase3.test.ts` (pure: which cells changed, what the reason is) plus a
> scene `[S-7]`.
>
> **Phase** 3. **Closes** `[G-15]`.
> **Scene.** `[S-7]` — end to end.

---

## Phase 4 — the platform

### `[R-13]` Declarative hooks

> **Statement.** A workspace may declare rules in `Workspace/.opengenie/hooks.yaml`: `on`
> (`before_tool`|`after_tool`), `match` (tool name), `when` (a predicate over the arguments), `then`
> (`refuse`|`run`), `say` (the sentence a user reads). The tool server evaluates them **after** the
> fence and **before** the call. A refusal names the rule. A rule that fails to parse is reported once
> and does not disable the fence.
>
> **Why.** `[G-21]`, and `[04 §3.1]`: Cursor and Claude Code both expose the agent loop to a platform
> team; the fence here is the natural place, and it already has the vocabulary.
>
> **Gate.** `tests/test_phase4.py` — every combination, an unparseable file, a rule that cannot be
> evaluated, a rule that tries to widen the fence (refused).
>
> **Phase** 4. **Closes** `[G-21]`.
> **Scene.** `[S-14]` — end to end.

---

### `[R-19]` Genie Ontology as a separately fenced server

> **Statement.** A session may attach a **second** tool server — Genie One MCP — which is read-only by
> construction and whose calls appear in the transcript and the evidence table like any other.
>
> **Why.** `[G-7]`, `[C11]`. The `genie` scope is already declared in `databricks.yml` and nothing
> calls it.
>
> **Gate.** `tests/test_phase4.py` — the fence is not widened, the tool budget accounts for the
> added schemas, and a refusal from Genie is reported as Genie's. `[RB-7]` records the constraint.
>
> **Phase** 4. **Closes** `[G-7]`.
> **Scene.** `[S-15]` — end to end.

---

### `[R-20]` Documentation search with citations

> **Statement.** The agent can search the product's own documentation and the Databricks documentation,
> and a citation renders as a link with the page title and the section.
>
> **Why.** `[G-9]`, `[C12]`. The repository publishes a documentation site; it is the natural corpus.
>
> **Gate.** `tests/test_phase4.py`; a rendering test in `Markdown.test.tsx`.
>
> **Phase** 4. **Closes** `[G-9]`.
> **Scene.** none: this requirement is unit-only, and [15 §3.1](15-e2e-plan.md) says why.

---

### `[R-23]` Scheduled agent turns

> **Statement.** A schedule may run a prompt in a **new** session under **the creator's** identity, and
> the result is a normal conversation the creator can open. A scheduled run that would need an approval
> is refused rather than auto-approved.
>
> **Why.** `[G-17]`, `[C27]`, `[C28]`. Genie's scheduled runs use the creator's permissions and
> auto-approve always; here the *safe* choice is available, because approvals are a first-class concept.
>
> **Gate.** `tests/test_phase4.py` — identity, the refusal, the run record, the "cannot approve"
> path. Scene `[S-9]`.
>
> **Phase** 4. **Closes** `[G-17]`.
> **Scene.** `[S-9]` — end to end.

---

### `[R-25]` A bounded subagent

> **Statement.** A subagent is a second tool server scoped **tighter** than its parent, plus a bounded
> prompt (token ceiling, wall clock, tool count). Its calls appear in the parent's transcript as one
> collapsed group, and its evidence is attributed to the parent's requirements.
>
> **Why.** `[G-22]`, `[04 §3.2]`: the reason a data agent needs subagents is *context isolation on a
> large catalog*, not parallelism.
>
> **Gate.** `tests/test_phase4.py` — the tighter scope, the ceilings, the attribution, the refusal to
> exceed the parent.
>
> **Phase** 4. **Closes** `[G-22]`.
> **Scene.** none: this requirement is unit-only, and [15 §3.1](15-e2e-plan.md) says why.

---

## The traceability table

Every requirement, its finding or gap, its phase, and its gate file. [14](14-coherence.md) checks that
each gate file exists after phase 1 lands.

| Req | Closes | Phase | Gate |
|---|---|---|---|
| `[R-1]` | `F-1` | 1 | `test_fence_parity.py`, `test_tools_fence.py` |
| `[R-2]` | `F-1` | 1 | `test_fence_parity.py` |
| `[R-3]` | `F-2` | 1 | `test_payload_window.py` (new) |
| `[R-4]` | `F-3` | 1 | `test_agent_isolation.py` |
| `[R-5]` | `F-4` | 1 | `test_journal_cost.py` (new) |
| `[R-6]` | `F-4`, `F-5` | 1 | `test_delta_coalescing.py` (new) |
| `[R-7]` | `F-6` | 1 | `test_api.py` |
| `[R-8]` | `F-7` | 1 | `test_dead_code.py` (new) |
| `[R-12]` | `F-11` | 1 | `test_infra_routes.py` |
| `[R-9]` | `F-8` | 2 | `test_write_mode.py` (new) |
| `[R-10]` | `F-9` | 2 | `test_phase2.py` (new) |
| `[R-11]` | `F-10` | 2 | `test_phase2.py` (new) |
| `[R-17]` | `[G-5]` | 2 | `test_phase2.py` (new) |
| `[R-18]` | `[G-6]` | 2 | `test_skills_and_sheets.py` (new) |
| `[R-21]` | `[G-12]` | 2 | `test_blob_rules.py` |
| `[R-24]` | `[G-20]` | 2 | `test_phase2.py` (new) |
| `[R-14]` | `[G-1]` | 3 | `phase3.test.ts` (new) |
| `[R-15]` | `[G-2]` | 3 | `test_search_and_fork.py` (new) |
| `[R-16]` | `[G-4]` | 3 | `test_search_and_fork.py` (new) |
| `[R-22]` | `[G-15]` | 3 | `phase3.test.ts` (new) |
| `[R-13]` | `[G-21]` | 4 | `test_phase4.py` (new) |
| `[R-19]` | `[G-7]` | 4 | `test_phase4.py` (new) |
| `[R-20]` | `[G-9]` | 4 | `test_phase4.py` (new) |
| `[R-23]` | `[G-17]` | 4 | `test_phase4.py` (new) |
| `[R-25]` | `[G-22]` | 4 | `test_phase4.py` (new) |
| `[R-26]` | `F-12` | 1 | `test_domain.py` (extend) |
| `[R-27]` | `F-13` | 1 | `stream.test.ts` (extend), `test_domain.py` |
| `[R-28]` | `F-14` | 1 | `test_jobs_domain.py` (extend), `jobs-table.json` |
| `[R-29]` | `F-15` | 1 | `test_cellrun.py` (extend) |
| `[R-30]` | `F-16` | 1 | `test_blob_retention.py` (extend) |
| `[R-31]` | `F-17` | 1 | `test_supervisor.py` (new) |

**Counts (as built):** 31 requirements, **21 gate files new**, **7 existing files extended**, 0 requirements without a
level of proof. Counted from [11 §6](11-implementation-plan.md#6--the-test-map), which lists every file and
what it proves.

Next: [09 · Seven lenses](09-lenses.md).
