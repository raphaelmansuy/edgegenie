# 001 · OpenGenie assessed: against Genie Code, and against the best coding agents

**Status:** assessment + specification, 11 November 2026.
**Folder name:** `001-opengenie-assessment` (the request said `assesment`; corrected, since a
directory name is permanent and every link in this repository would carry the typo).
**Scope:** the product as it exists in `apps/coding-agent` at commit `2063af3`, measured; the
Databricks Genie Code documentation as published on **9 November 2026**; and the three leading
general coding agents as documented on **12 October 2026**. No claim in this set is from memory —
[01](01-method-and-evidence.md) records where every number comes from and how to re-derive it.
**Audience:** the product owner, the engineer who will implement it, and a reviewer who wants to
know what is actually true before approving the work.

---

## The one paragraph

OpenGenie is a governed coding agent: one Databricks App, one child ACP agent per conversation, one
fenced MCP tool server per conversation, and a durable Postgres journal under both. It makes three
promises — **the model is a setting**, **writes stay inside a fence**, **done means proven** — and the
first two are real in the code while the third is real *and* unusual: no market coding agent matches
a claim against the tool calls that actually happened. Against **Genie Code** it wins on model
freedom, per-token cost control, and auditability, and loses on the surface area of the product:
no parallel threads on screen, no user extensibility (workspace instructions, user skills, MCP
marketplace, memory), no git-aware loop, no completions, no accept/reject diff, no scheduled agent,
no chat sharing. Against **Claude Code, Codex and Cursor** it loses on almost every mechanics of the
coding loop (worktrees, subagents, hooks, sandboxed shell, background sessions) and wins on the one
thing they structurally cannot do: run the tool call *as the signed-in user* against Unity Catalog,
and prove afterwards which call produced which claim. The assessment also found **seventeen defects the
product's own documentation says do not exist**, including a fence that fails *open* when a session
has no schema, a tool that can emit invalid JSON, and a journal that writes gigabytes per turn.

**Three of those eleven are one finding each in a phase, not a rewrite.** Phase 1 is two weeks and it
makes the product's own claims true; nothing else starts until it lands.

---

## What this folder is

| # | Document | Answers |
|---|---|---|
| 01 | [Method and evidence](01-method-and-evidence.md) | What was measured, how, on which commit, with which test baselines and which dated sources |
| 02 | [OpenGenie, measured](02-assessment-opengenie.md) | What the product is, in numbers, and the **seventeen findings** `[F-1]`–`[F-17]` |
| 03 | [Against Genie Code](03-comparison-genie-code.md) | Capability by capability, with the documentation's own words, and a verdict per row |
| 04 | [Against the best coding agents](04-comparison-best-agents.md) | Claude Code / Codex / Cursor, and what "best for data engineering" actually means |
| 05 | [Gaps and improvements](05-gaps-and-improvements.md) | What is missing, ranked by value and cost; what to build, what to refuse |
| 06 | [Wireframes](06-wireframes.md) | ASCII: screens, components, layouts, navigation, every state |
| 07 | [Diagrams](07-diagrams.md) | **Every state machine, exhausted** — 14 machines, 26 Mermaid diagrams, each table reproduced by a command |
| 08 | [Requirements](08-requirements.md) | `[R-*]` — what must be true when the work is done |
| 09 | [Eight lenses](09-lenses.md) | The same work seen by PO, UI/UX, full-stack, database, system design, O(n), AI engineer, and a **verification engineer** who owns "is this proven?" |
| 10 | [Architecture](10-architecture.md) | Where each new rule lives, why there, and the DRY/SOLID argument |
| 11 | [Implementation plan](11-implementation-plan.md) | Phases, files, tests, order, gates |
| 12 | [Edge cases](12-edge-cases.md) | Every failure that can be named, its mitigation, its test |
| 13 | [Roadblocks](13-roadblocks.md) | `[RB-*]` — what is in the way, grounded in code, and the way past each |
| 14 | [Coherence check](14-coherence.md) | The spec against the code, line by line, before implementation |
| 15 | [E2E plan](15-e2e-plan.md) | Scenes, screenshots, pass criteria |
| 16 | [Outcome](16-outcome.md) | **What shipped**, what it cost, and what is deliberately not done |
| — | [E2E screenshots](e2e/screenshots/README.md) | Five scenes, each inspected; the two defects the pictures found |

**Citation grammar.** `[F-n]` is a finding, defined once in [02](02-assessment-opengenie.md). `[R-n]`
a requirement, defined once in [08](08-requirements.md). `[RB-n]` a roadblock, defined once in
[13](13-roadblocks.md). `[E-n]` an edge case, defined once in [12](12-edge-cases.md). `[S-n]` a scene,
defined once in [15](15-e2e-plan.md). `[L-n]` a lens section of [09](09-lenses.md). A bracketed id
used anywhere and not defined in its home document is a bug in this set.

---

## The verdict, in four sentences

1. **OpenGenie is not a Genie Code clone and should stop describing itself as one.** Its README opens
   with "the Databricks coding agent, on the model you choose", which is accurate and narrower than
   "on par" (spec 006's title). The parity work that matters is done; the parity work that remains is
   the *product surface around the agent*, not the agent.
2. **Its defensible advantage is governance plus evidence, not features.** Per-user Unity Catalog
   identity on every tool call, a durable append-only journal, and a supervisor that refuses to call a
   turn finished until each requirement has a completed tool call behind it. Measured in this repo:
   that loop took a fixed model from 19% to 94% on the same tasks. No market agent ships it as a
   first-class concept.
3. **Its largest risk is not a missing feature; it is that three of its written guarantees are false
   in the code** — the agent *does* receive the user's workspace token; the tool-server fence *opens*
   when a session has no schema; and a truncated tool result is not valid JSON. Each is `[F-1]`,
   `[F-2]`, `[F-3]` and each is fixable in a phase, not a rewrite.
4. **The plan is four phases and one refusal.** Fence and payload correctness first (they are safety),
   then the durable-journal scaling work (it is a wall at ~10 conversations/day), then the surface
   that closes the real Genie Code gaps (instructions, skills, threads, diff accept), and one explicit
   refusal — **do not** build inline completions, connectors, or Genie Migrate; they are other
   products, and the cost is not a UI.

---

## The findings, in one table

Every row was produced by reading this checkout and running it, not from the documentation. Detail,
evidence and re-derivation are in [02](02-assessment-opengenie.md). `F-1`–`F-11` came from reading the
request path; `F-12`–`F-17` came from **exhausting every state machine** ([02 §8](02-assessment-opengenie.md#8--six-state-machine-defects-proved-by-exhaustion)).

| # | Finding | Where | Kind |
|---|---|---|---|
| **F-1** | **The tool-server fence fails open when a session has no schema.** `NBMCP_WRITE_SCHEMAS=""` makes `_check_sql_scope` return `None` ("no restriction"), while the app's `check_sql` says `ASK`. And `NBMCP_WRITE_PATHS` is computed as `folder.rstrip("/") + "/"`, so `folder="/"` and `folder=""` both become `"/"`, which every absolute path matches. Measured: the tool server allows `/Users/victim/x.py`; the app asks. | `tools/databricks_notebook_mcp.py:355-356,375-392,416-431`; `api/adapters/mcp/registry.py:64-65`; `api/domain/scope.py:204-243` | **defect** |
| **F-2** | **A truncated tool result is not JSON.** `_trim` slices the serialised text at `MAX_CHARS` and appends a notice. Measured on a 200-table `list_tables` payload: the result is unparseable (`Invalid control character at char 6000`). This is the *same class* as the silent-truncation defect the repository already documents at §4.8/§4.9 of `docs/genie-code-replacement-spec.md` — fixed there for `read_notebook`/`grep_notebook`, never fixed here. | `tools/…:279-284`; measured with a 200-row payload | **defect** |
| **F-3** | **The agent process receives the user's workspace token.** `_child_env` sets `env["DATABRICKS_TOKEN"] = user_token` and `AcpAgentRuntime.start` passes it to the child. `docs/08-architecture.md:147` and `docs/09-security.md:63` both state the opposite ("the agent does not hold a workspace token", "never receives"). The fence still holds because the agent's builtins are denied in two layers, but the written guarantee is false and one config change away from being a hole. | `api/services/orchestrator.py:570-589`; `api/adapters/acp/runtime.py:45`; `docs/08:147`, `docs/09:63` | **defect (doc ↔ code)** |
| **F-4** | **The journal writes the whole snapshot on every event.** `commit()` upserts `body = snapshot` *and* appends the event, per delta. A 60 k-character answer is ~15 000 `message.delta` events; each carries a ~121 KB snapshot. Measured: ≈1.8 GB written per turn, ≈18 GB per ten-turn conversation. O(n²) in answer length. There is no delta coalescing anywhere (`_drain` emits every event; the mapper emits one event per chunk). | `api/adapters/durable/postgres.py:58-74`; `api/services/orchestrator.py:1042-1068`; `api/adapters/acp/mapper.py:108-112` | **defect** |
| **F-5** | **The browser copies the whole answer on every delta.** `append()` rebuilds the string per delta with a 200 000-character cap, so a long answer is O(n²) in the tab as well — the client mirror of `F-4`. | `web/src/domain/events.ts:160-167,218` | **defect** |
| **F-6** | **Conversations are listed in random order.** `sessions_for` sorts by `s.id`, and an id is `uuid4().hex[:16]`. The docstring says "newest first"; the day-grouping works, the order inside a day does not. | `api/services/orchestrator.py:266-276`; `Session(id=uuid4().hex[:16])` at `:455` | **defect** |
| **F-7** | **The app-side fence for SQL, jobs, apps and instances has no production caller.** `check_sql`, `check_job`, `check_app`, `check_instance` are called by tests only; the only fence in the request path is the tool server's, which is `F-1`. `check_path` *is* wired (`/workspace/fence`, `/workspace/save`). So "two implementations held to one table" is one implementation in the path. | `api/domain/scope.py:204-283`; `rg 'check_sql\('` → `api/domain/scope.py` (def) + `tests/` only | **defect** |
| **F-8** | **Writes are unconditionally on.** The registry starts every tool server with `NBMCP_ALLOW_WRITES=1`, so the tool docstring's "read-mostly by default" and the product's "ask a human" story hold only for the ACP agent's own permission prompts. A SQL write inside the schema executes with no human gate. | `api/adapters/mcp/registry.py:63`; `tools/…:22-24,66` | **defect** |
| **F-9** | **A server restart requires a manual Restore on every conversation, and an evicted conversation is a 404.** `restore()` marks every non-archived session `BLOCKED + requires_resume=True`; `evict_archived()` pops the projection and `get()` raises `KeyError` → 404, although `agent.session_snapshot` still holds the row. Nothing rehydrates. | `api/services/orchestrator.py:176-190,392-410`; `api/routers/api.py:208-212` | **gap** |
| **F-10** | **There is no context compaction.** `session.compacted` is in the event vocabulary (27 types) and emitted by nothing, so a long conversation has no mechanism to shed history before it hits the model's window; `MAX_TURNS=200` is the only limit, and it is a hardcoded constant while `settings.max_turns_per_session` exists with **no reader**. | `api/domain/events.py:37`; `api/services/orchestrator.py:64,859`; `api/config.py:100` (unused) | **gap** |
| **F-12** | **`finish()` has no source-state guard**, so a settled turn can be rewritten: measured, a `COMPLETED` turn finishes as `INTERRUPTED`, and the timeout handler does exactly that on a settle/timeout race | `api/domain/session.py:113-121`; `api/services/orchestrator.py:947` | **defect** |
| **F-13** | **`closed: "offline"` is declared and unreachable.** `afterFailure` returns `reconnecting` for every offline case, so the member, its copy, and its row in the table are dead | `web/src/domain/stream.ts:25-34,74-76,116` | **defect** |
| **F-14** | **An active run with a `result_state` reads as finished**, with Cancel enabled: measured, 24 of 60 `ACTIVE × RESULT` cells give a green "succeeded" **and** a Cancel button | `api/domain/jobs.py:212-216,265-270` | **defect** |
| **F-15** | **A `QUEUED` statement is reported as failed** — "the warehouse reported QUEUED", with no error message — because the fallthrough is `FAILED` | `api/domain/cellrun.py:145-162` | **defect** |
| **F-16** | **`KEPT_REFERENCED` also means "unknown state"**: the refcount is checked before the state, so a reason a test asserts is not the reason | `api/domain/retention.py:75-88` | **defect** |
| **F-17** | **An agent that did the work but omitted the evidence table is `blocked`**: measured, 2 completed calls + a correct prose answer → `blocked` after 2 audits, with the calls in the transcript | `api/domain/supervisor.py:87-112` | **defect** |

Two more of the same kind are recorded for completeness in [02 §7](02-assessment-opengenie.md#7--documentation-drift): both docs pages name a
`web/src/domain/reduce.ts` that does not exist (the reducer is in `events.ts`), and `docs/08` calls
959 front-end *tests* "959 assertions" (the suite has 1 594 `expect(` calls).

`F-12`–`F-17` were produced by **exhausting** every state machine rather than reading it: each
transition was attempted against the real code, and the resulting matrices are in
[07 · Diagrams](07-diagrams.md), which supersedes a diagram with the transitions the code actually
permits. The one-line summary of the six is that the vocabulary and the code disagree in five places and
the product's headline promise produces a false negative in the sixth.

---

## What is not wrong

Stated because the plan must not disturb it, and because a reader who only reads the findings would
conclude the product is broken. It is not.

| Works, and is measured | Where |
|---|---|
| **1 303 Python tests, 7 skipped, pass in 17.8 s**; **959 front-end tests in 69 files pass in 14.4 s** — run for this assessment on this commit | `apps/coding-agent/.venv/bin/python -m pytest -q`; `cd web && npx vitest run` |
| The tool budget is **28** and a test fails if the set drifts or if the UI label disagrees with it | `tests/test_tools_fence.py:220-310` |
| The event vocabulary is **27** names and a Python test holds the TypeScript union and a JSON fixture to it | `api/domain/events.py:37`; `tests/test_event_parity.py` |
| The fence is held to **one table across two runtimes** for the cases the table contains | `tests/test_fence_parity.py:63-140` |
| Every turn pins the model it used, before the prompt, and never rewrites it | `api/services/orchestrator.py:902-921`; `llm.llm_turn_model` |
| The approval for a human save is a stateless HMAC bound to path **and** version, with a TTL | `api/domain/approval.py` |
| The reaper, the projection eviction and the blob sweep are **pure rules** with a `Why`/`Disposition` value so a test asserts *why* | `api/domain/reaper.py`, `projection.py`, `retention.py` |
| Streaming is SSE with **the journal as truth and the queue as a wake-up**, so a reconnect is a replay and a slow viewer heals | `api/routers/api.py:365-410` |
| The shell's geometry is one pure module with the centre column never below 480 px | `web/src/domain/layout.ts:41,110-160` |

---

## Reading order

**If you have ten minutes:** [02 §5](02-assessment-opengenie.md#5--the-eleven-findings-from-the-request-path) (the findings from the request path; the other six are in §8 of the same document), then
[05](05-gaps-and-improvements.md) (what to do about them), then [11](11-implementation-plan.md) (the order).

**If you are approving the work:** [13 Roadblocks](13-roadblocks.md) first — it decides the
architecture — then [14 Coherence](14-coherence.md) — it decides whether the plan is buildable — then
[08 Requirements](08-requirements.md) for the acceptance test.

**If you are implementing:** [10 Architecture](10-architecture.md) → [11 Plan](11-implementation-plan.md)
→ [12 Edge cases](12-edge-cases.md) → [15 E2E](15-e2e-plan.md).

**If you are comparing products:** [03](03-comparison-genie-code.md) and [04](04-comparison-best-agents.md),
which separate "cannot" from "does not yet" from "should not".

---

## The five principles this assessment rests on

1. **Measure the code, not the documentation.** Four of the seventeen findings are places where the
   documentation is more confident than the code. Every number here has a command behind it in
   [01](01-method-and-evidence.md).
2. **Separate the three kinds of gap.** *Cannot* (a platform rule: `jobs` is not a grantable user
   scope). *Does not yet* (a surface: instructions, threads, diff accept). *Should not* (inline
   completions, connectors, Genie Migrate — each is a product, not a feature). A roadmap that mixes
   them promises work nobody can finish.
3. **Safety defects outrank features.** `F-1` and `F-2` are the reason phase 1 exists and nothing
   else starts until it lands. A product whose promise is "writes stay inside the fence" cannot ship
   a fence that opens when a session has no schema.
4. **Cost is a feature of the design, not a report.** `F-4` and `F-5` make the journal's cost
   quadratic in answer length. That is not a billing issue; it is the thing that will make the app
   slow at the scale where it becomes valuable.
5. **Every improvement must be provable in this repository.** A requirement with no test in [11](11-implementation-plan.md)
   and no scene in [15](15-e2e-plan.md) is a wish, and it is not in [08](08-requirements.md).
