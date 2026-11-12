[Index](README.md) · prev: [14 Coherence check](14-coherence.md)

# 15 · E2E plan

Scenes, screenshots, pass criteria. `[S-n]` is defined here once.

The rule, inherited from this repository's own convention: **a screenshot without an assertion taken
before it is decoration.** Every scene names what is asserted, then captures, then a human looks at the
picture. The two defects that pattern found in spec 014 ("six defects, three of which passed their
assertions first") are the argument for keeping it.

---

## 1 · What can be driven, and what cannot

| Surface | Drivable here | How |
|---|---|---|
| The API and the fence | **yes** | `pytest`, the `.venv`, and a fake agent — no workspace, no network |
| The shell and the wireframes | **yes** | the built front end against `APP_AGENT_MODE=fake`, `web/scripts/*-e2e.mjs` |
| The journal's cost | **yes** | `test_journal_cost.py` counts writes against a fake cursor |
| A live workspace (Unity Catalog, a warehouse, a job) | **only with a token** | `scripts/dev-token.sh`; scenes that need it are marked **live** |
| Genie Code, Claude Code, Codex, Cursor | **no** | compared from documentation only ([03](03-comparison-genie-code.md), [04](04-comparison-best-agents.md)) |
| The exam suite's score | **yes, at cost** | `exams/run_exam.py`; a gate for phase 2, not a scene |

A scene that needs a live workspace says so, and it is skipped — not silently passed — when there is no
token. That distinction is written into each scene's pass criteria, because "the test did not run" has
twice in this repository been read as "the test passed" (`specs/014/12-outcome.md` records a 401 counting
as a pass).

---

## 2 · The scenes

### `[S-1]` The fence refuses, in three ways, and says why — phase 1

**Asserts, before the picture:**
1. a session with `schema: null` gets a refusal naming the missing schema;
2. a session with `folder: "/"` gets a refusal naming the missing folder;
3. a session inside the fence can write, and the same statement outside it is refused with the folder
   in the sentence.

**Driven by.** `pytest tests/test_fence_parity.py -k unset` (no browser) plus a scene that sends the three
prompts to the fake agent so the refusals appear in a transcript.

**Screenshot.** `[S1-fence-refusal.png]` — the dock showing the three refusals, each with its reason.

**Pass.** Three refusals, three distinct sentences, and **no** "allowed" in the log. A refusal that says
*"not allowed"* without naming which of the two is missing fails the scene: `[R-1]` requires the sentence.

---

### `[S-2]` A truncated list is a window the agent can page — phase 1

**Asserts.** A 200-table payload returns `returned < total` with a `next_offset`; paging to the end
reconstructs the original array exactly; every page parses as JSON.

**Driven by.** `pytest tests/test_payload_window.py`, and a scene against a **live** workspace with a
schema of >100 tables where the agent is asked *"how many tables are in X"*.

**Screenshot.** `[S2-paged-listing.png]` — the tool card showing *"38 of 200"* and the second call.

**Pass.** The agent's final answer states the **total**, not the page size. That is the whole point: an
agent that reports 38 has been lied to by the tool, and the scene fails.

---

### `[S-3]` A turn's cost, in the journal — phase 1

**Asserts.** One `INSERT INTO agent.session_snapshot` per 50 events; bytes written per turn under 1 MB
for a 60 k answer; the projection after replay from a checkpoint equals the projection after replay from
zero.

**Driven by.** `pytest tests/test_journal_cost.py` (unit) and `tests/test_delta_coalescing.py` (the ≤600
events assertion), then **the same turn replayed through the running app** and compared to a saved
projection fixture.

**Screenshot.** `[S3-stream-throughput.png]` — the transcript with a long answer, and the terminal showing
the write counter. The picture is evidence of *fluidity*, which the counter cannot show; the counter is
evidence of the number, which the picture cannot show. Both are captured.

**Pass.** Both numbers under budget, **and** the assistant dock followed the stream to the end without a
visible stutter at 1440 px.

---

### `[S-4]` A restart tells three different truths — phase 2

**Asserts.** A session mid-turn restores as `needs you` with the interrupted turn listed; a session that
was idle restores as `ready` and accepts a message; an archived session that was evicted still reads from
the journal.

**Driven by.** `pytest tests/test_restart_disposition.py` plus a scripted scene: start a turn, `SIGTERM`
the server mid-stream, restart it, screenshot the rail.

**Screenshots.** `[S4a-after-restart-rail.png]`, `[S4b-idle-ready.png]`, `[S4c-evicted-reads.png]`.

**Pass.** Three visually distinct states, and the idle one has **no** Restore button. The failure this
scene exists to catch is the fix that handles only the mid-turn case — the picture would then show two
identical red banners.

---

### `[S-5]` Three conversations at once — phase 3

**Asserts.** Three sessions stream concurrently; switching a tab does not restart or cancel a turn;
a tab with a pending approval says so **in the strip**, without being opened.

**Driven by.** `threads.test.ts` (pure) plus a scene with `APP_AGENT_MODE=fake` and
`APP_MAX_CONCURRENT_AGENTS=3`, sending to three sessions and photographing the strip mid-stream.

**Screenshot.** `[S5-three-threads.png]`.

**Pass.** Two tabs show `working`, one shows `needs you`, and the strip is legible at 1440 px and at
1024 px. `[E-18]` (a thread archived under the user) is exercised by reaping one mid-scene: its tab must
render *"The server no longer has this session"* and not vanish.

---

### `[S-6]` Search finds the word, at the turn — phase 3

**Asserts.** A query returns the conversations containing it, the turn index, and a snippet; opening a
result lands at that turn; a **redacted** secret produces no match (`[E-19]`).

**Driven by.** `pytest tests/test_search.py` plus a scene with three seeded conversations.

**Screenshot.** `[S6-search.png]`.

**Pass.** A result for a word that appears **only in a turn**, not in a title — which is the whole
difference from today's rail search.

---

### `[S-7]` A proposal is a decision, not an edit — phase 3

**Asserts.** The proposed cells are marked; `Reject` leaves the notebook byte-identical; `Keep` writes
inside the fence and the transcript records the write; a dirty document **holds** the proposal (`[E-21]`);
accepting a stale proposal returns `409` with both versions (`[E-22]`).

**Driven by.** `proposal.test.ts` plus a scene on a notebook.

**Screenshots.** `[S7a-proposal.png]`, `[S7b-after-keep.png]`, `[S7c-dirty-held.png]`.

**Pass.** The original file's bytes are unchanged after `Reject` (a hash comparison, not a visual check).

---

### `[S-8]` The agent is told what the team configured — phase 2

**Asserts.** Workspace instructions, personal instructions and `AGENTS.md` appear as three separately
labelled blocks; the session's scope block is **last**; an unreadable file is reported, not dropped;
an instruction that contradicts the fence does not change what a write does (`[E-12]`).

**Driven by.** `pytest tests/test_instructions.py` plus a scene with a seeded
`Workspace/.assistant/instructions.md`.

**Screenshot.** `[S8-instructions-provenance.png]`.

**Pass.** Three labels with three distinct sources, and a write attempted under a permissive instruction
is still refused.

---

### `[S-9]` A scheduled turn uses the creator's permissions and refuses to approve — phase 4

**Asserts.** The run creates a **new** session under the creator's identity; a prompt that needs an
approval is refused rather than auto-approved; the run appears in the creator's conversation list.

**Driven by.** `pytest tests/test_schedule.py` plus a scene with a one-minute schedule on the fake agent.

**Screenshot.** `[S9-scheduled-run.png]`.

**Pass.** The refusal names the approval that would have been needed. This is the one place this product
must be **worse** than Genie Code on purpose: Genie's scheduled tasks "always" auto-approve, and that is
the wrong default for a product whose selling point is governance.

---

### `[S-11]` A fork is a copy of the prefix, and nothing else — phase 3

**Asserts.** Forking at turn 4 produces a session whose journal contains events `seq 1` to that turn's
`turn.completed` and **no** later event; the new session has its own id, its own fence and its own pin
history; a fork at a turn that ended `blocked` keeps that state and its evidence gap (`[E-20]`).

**Driven by.** `pytest tests/test_fork.py` plus a scene: four turns on the fake agent, fork at turn 3,
open the new conversation.

**Screenshots.** `[S11a-fork-menu.png]`, `[S11b-forked-transcript.png]`.

**Pass.** The new transcript ends at turn 3, the rail shows two conversations with the same title prefix,
and the fork's model pin list has exactly three entries. A fourth entry fails the scene: it would mean the
fork copied history it should not have.

---

### `[S-12]` A write mode is a decision the user made — phase 2

**Asserts.** `read-only` refuses every mutating tool with a reason; `fenced` executes inside the fence and
refuses outside; `ask` returns a needs-human result that renders as an inline approval; a mode changed
mid-turn applies to the **next** turn (`[E-8]`), and the running turn's mode is stated on screen.

**Driven by.** `pytest tests/test_write_mode.py` plus a scene: a session in `read-only` asked to create a
table, then switched to `fenced` and asked again.

**Screenshots.** `[S12a-read-only-refused.png]`, `[S12b-fenced-approved.png]`,
`[S12c-mode-in-header.png]`.

**Pass.** The refusal in `[S12a]` names the mode, not just the folder — "read-only" is a decision the user
made and the sentence must reflect that. A refusal that only says "outside the fence" fails the scene: it
is the wrong reason.

---

### `[S-13]` A budget stops work before it spends — phase 2

**Asserts.** A session with a limit and 90% consumed accepts one more turn; a session at 100% blocks the
next turn **without a model call**; the message carries the number and the limit; the per-turn model table
still shows every turn, including the one that was blocked (`[E-13]`, `[E-23]`).

**Driven by.** `pytest tests/test_budget.py` plus a scene with a deliberately small limit on the fake
agent.

**Screenshots.** `[S13a-budget-blocked.png]`, `[S13b-model-per-turn.png]`.

**Pass.** No model request is made for the blocked turn — asserted with a counting fake, not inferred from
the UI. The picture shows the sentence; the counter proves the spend did not happen.

---

### `[S-14]` A hook refuses, and cannot be talked out of it — phase 4

**Asserts.** A rule in `Workspace/.opengenie/hooks.yaml` refuses a matching statement; the refusal quotes
the rule's own `say` sentence; an unparseable rule file is reported once and the fence still works; a rule
cannot widen the fence (`[E-5]`); a hanging `then: run` action is killed (`[E-16]`).

**Driven by.** `pytest tests/test_hooks.py` plus a scene with a seeded rules file and a `DELETE FROM
main.gold…` prompt.

**Screenshot.** `[S14-hook-refusal.png]`.

**Pass.** The agent's next attempt uses a different statement — it adapted rather than repeating. The
picture shows the rule's sentence; the transcript shows the adaptation.

---

### `[S-15]` A second, read-only server does not widen the fence — phase 4

**Asserts.** With Genie attached, a write is still refused by the same fence; the tool budget shown in the
UI accounts for both servers separately; an event from the second server is attributed to it in the
evidence table.

**Driven by.** `pytest tests/test_second_server.py` plus a scene (live, if a Genie space exists).

**Screenshot.** `[S15-two-servers.png]`.

**Pass.** The tool count in the dock is **two numbers**, not one sum. A single summed number fails the
scene: it would hide which surface a tool came from, and the fence story depends on that distinction.

---

### `[S-10]` The wireframes are the screens — every phase

**Asserts.** Each frame in [06](06-wireframes.md) corresponds to a real screen at the stated width, and
the widths are `layout.ts`'s.

**Driven by.** A script that photographs the eleven screens at 1440 / 1024 / 820 and compares the
**structure** (which panes, in which order, at which width) to the frame. Not pixel comparison: the
assertion is that the frame is not describing a screen that does not exist.

**Screenshots.** `[S10-<frame>-<width>.png]` × 11 × 3.

**Pass.** Eleven screens exist, each at three widths, with no horizontal overflow and the centre column
never below 480 px.

---

### `[S-16]` An active run never reads as finished — phase 1

**Asserts.** For each `ACTIVE` life cycle with a `result_state` present, the page shows the **life-cycle**
word and Cancel, never a terminal word. The row that produced `F-14`
(`TERMINATING + SUCCESS → "succeeded"` beside an enabled Cancel) is the one photographed.

**Driven by.** `test_jobs_domain.py::test_an_active_run_never_reads_as_finished` (the full 6 × 10 grid),
then a scene with a mocked `TERMINATING` run payload.

**Screenshot.** `[S-16-terminating-run.png]`.

**Pass.** The word is "finishing", not "succeeded", **and** the Cancel control is present. A picture with
either one alone fails the scene: the defect was the pair.

---

### `[S-17]` Work that was done is not reported as blocked — phase 1

**Asserts.** Two completed calls plus a correct prose answer, with **no** evidence table, ends
`completed` and the two calls are visible in the transcript. The same shape with an **incomplete** call
still ends `blocked`.

**Driven by.** `test_supervisor.py::test_completed_work_without_a_table_is_not_blocked`, then a scene
against the fake agent with a scenario that omits the table.

**Screenshot.** `[S-17-no-table-completed.png]`.

**Pass.** The mission header says "Achieved" or "Ready for review", never "Blocked", and the two tool
cards are on screen. The **negative** case is asserted too, because a fix that makes everything `done`
would pass the first half.

---

## 3 · The scene table

| Scene | Phase | Needs live workspace | The failure it exists to catch |
|---|---|---|---|
| `[S-1]` | 1 | no | a refusal that does not say which of two fences is missing |
| `[S-2]` | 1 | **yes** (for the agent half) | an agent reporting a page size as a total |
| `[S-3]` | 1 | no | a fixed cost that only looks fixed in a unit test |
| `[S-4]` | 2 | no | a restart fix that handles one of two cases |
| `[S-5]` | 3 | no | a tab that cancels work when it is not visible |
| `[S-6]` | 3 | no | a search that only finds titles |
| `[S-7]` | 3 | no | a "reject" that still wrote |
| `[S-8]` | 2 | no | configured context that looks like the user's words |
| `[S-9]` | 4 | no | a scheduled run that approves itself |
| `[S-10]` | all | no | a wireframe describing a screen that does not exist |
| `[S-11]` | 3 | no | a fork that copied history it should not have |
| `[S-12]` | 2 | no | a refusal that names the wrong reason |
| `[S-13]` | 2 | no | a budget that blocks *after* spending |
| `[S-14]` | 4 | no | a hook the agent can retry past |
| `[S-15]` | 4 | **yes** (for the Genie half) | a second server that silently widens the fence |
| `[S-16]` | 1 | no | an active run painted as finished beside a live Cancel |
| `[S-17]` | 1 | no | a supervisor fix that makes everything `done` |

---

## 3.1 · Which requirement is proved by which scene

Every requirement names a unit test in [08](08-requirements.md); this table says which one is also proved
**end to end**, and which are unit-only on purpose.

| Requirement | Scene | Why this level |
|---|---|---|
| `[R-1]` `[R-2]` | `[S-1]` | a refusal must be visible in a transcript, not only in a table |
| `[R-3]` | `[S-2]` | the failure was an agent answering from a fragment — only an agent turn shows it |
| `[R-4]` | — | a fact about a process's environment; a `pytest` assertion is the whole truth |
| `[R-5]` `[R-6]` | `[S-3]` | a cost claim needs both a counter and a picture of the stream |
| `[R-7]` | `[S-4]` (rail) | the order is visible in the rail, and that is where it was wrong |
| `[R-8]` | — | reachability of a function; a unit test is exact and a scene adds nothing |
| `[R-9]` | `[S-12]` | the mode must be *named* on screen, or it is a hidden constant again |
| `[R-10]` | `[S-4]` | three states, three pictures |
| `[R-11]` | `[S-3]` (long turn) | compaction is visible as a turn that continues past the window |
| `[R-12]` | — | a file-open count; unit only |
| `[R-13]` | `[S-14]` | the rule's sentence must reach the user |
| `[R-14]` | `[S-5]` | three concurrent streams |
| `[R-15]` | `[S-6]` | a word that appears only in a turn |
| `[R-16]` | `[S-11]` | the transcript must *end* where the fork was taken |
| `[R-17]` `[R-18]` | `[S-8]` | provenance is a rendering claim |
| `[R-19]` | `[S-15]` | two budgets, two surfaces |
| `[R-20]` | — | a citation's shape; unit only, plus `Markdown.test.tsx` |
| `[R-21]` | — | an attachment family; unit only |
| `[R-22]` | `[S-7]` | "reject did not write" is a hash comparison *and* a picture |
| `[R-23]` | `[S-9]` | a scheduled run's identity is only provable by running one |
| `[R-24]` | `[S-13]` | the spend must be shown not to have happened |
| `[R-26]` | — | an 8x5 terminal matrix; a screenshot adds nothing |
| `[R-27]` | — | reachability; unit only |
| `[R-28]` | `[S-16]` | the contradiction is a visible pair |
| `[R-29]` | — | a state mapping; unit only |
| `[R-30]` | — | a reason string; unit only |
| `[R-31]` | `[S-17]` | the false `blocked` is what a user reads |
| `[R-25]` | — | a tighter scope and a ceiling; unit only, until a real catalog search exists |

**Seven requirements are unit-only on purpose**, and the table says why. A scene whose only job is to
photograph something a test already proves exactly is a maintenance cost with no evidence value — that is
the same argument spec 014 used when it refused to screenshot a graph the test already parsed.

---

## 4 · How to run them

```bash
cd /Users/raphaelmansuy/Github/03-working/opengenie/apps/coding-agent

# 1. the unit layers — no browser, no workspace
.venv/bin/python -m pytest -q
( cd web && npx vitest run )

# 2. the app, with the fake agent: every scene that does not need a workspace
APP_AGENT_MODE=fake APP_MAX_CONCURRENT_AGENTS=3 \
  .venv/bin/python -m uvicorn api.main:app --port 8071 &

# 3. the scenes
cd web
APP_URL=http://127.0.0.1:8071 node scripts/shell-e2e.mjs
APP_URL=http://127.0.0.1:8071 node scripts/dock-e2e.mjs

# 4. a live workspace, for [S-2]'s agent half only
cd ../..
scripts/dev-token.sh 8062 &
APP_URL=http://127.0.0.1:8062 node apps/coding-agent/web/scripts/parity-e2e.mjs
```

**Every scene writes its screenshots to `e2e/screenshots/` in this folder**, and each one is opened and
looked at before the phase is called done. That is not ceremony: in spec 014, three defects passed their
assertions and were visible only in the image.

---

## 5 · What a reviewer should not expect here

| Not in this plan | Why |
|---|---|
| A pixel-diff baseline | the shell is resizable and themed; a structural assertion is honest, a pixel diff is a maintenance tax that gets disabled |
| A load test at 1 000 concurrent users | `[RB-11]` says the ceiling is one writer; a load test would measure the ceiling, not the product |
| A cross-browser matrix | the app is served inside a Databricks App in one browser family; a matrix would be a claim about a deployment nobody runs |
| A Genie Code side-by-side | it cannot be driven from here ([01 §4](01-method-and-evidence.md#4--the-limits-of-this-assessment)) |

---

## 6 · The final gate, in one block

```bash
cd /Users/raphaelmansuy/Github/03-working/opengenie

# the product
( cd apps/coding-agent && .venv/bin/python -m pytest -q && cd web && npx vitest run )

# the specification
cd apps/coding-agent/web
node scripts/verify-spec-ascii.mjs ../../../../specs/001-opengenie-assessment
NODE_PATH=/tmp/mmd/node_modules JSDOM_PATH=/tmp/mmd/node_modules/jsdom/lib/api.js \
  MERMAID_PATH=/tmp/mmd/node_modules/mermaid/dist/mermaid.core.mjs \
  node scripts/verify-spec-mermaid.mjs ../../../../specs/001-opengenie-assessment
```

Expected: **1 303 + N passing**, **959 + M passing**, **22 blocks / 11 boxes with 0 problems**, **13
diagrams with 0 failures**. Anything else is a phase that is not done.
