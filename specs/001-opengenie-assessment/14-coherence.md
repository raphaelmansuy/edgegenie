[Index](README.md) · prev: [13 Roadblocks](13-roadblocks.md) · next: [15 E2E plan](15-e2e-plan.md)

# 14 · Coherence check: the spec against the code

Every claim this set makes about the existing code, checked against the file, **before a line is
written**. This is the step that turns a plausible plan into a buildable one, and the step this
repository's own spec 014 made mandatory.

Three verdicts per row:

* **✓ agrees** — the code says what the spec assumes.
* **✗ contradicts** — the spec was wrong and was corrected here. The correction is named.
* **⚠ risk** — the code permits it but nothing enforces it, so the plan must add the enforcement.

A set that reaches this table with no ✗ has not been read carefully. **Twelve contradictions were found
and corrected**, and they are listed first because they are the ones a reviewer should check.

Baselines, re-run for this document ([01 §1.2](01-method-and-evidence.md#12-the-baselines-run-for-this-assessment)):
`pytest -q` → **1303 passed, 7 skipped**; `vitest run` → **959 passed, 69 files**.

---

## The twelve contradictions, and what changed

| # | The spec assumed | The code says | The correction |
|---|---|---|---|
| **C1** | `_check_sql_scope` returns `None` "when the schema is empty" | it returns `None` when `WRITE_SCHEMAS` is **falsy** — `if not WRITE_SCHEMAS: return None` at `:377-378`. An empty *string* in the env parses to an empty *list*, so the two cases coincide — but the wording matters: the guard is on the list, not on the schema | `[F-1]` states it as "no writable schema configured", and `[R-1]`'s test drives the **list**, not the string |
| **C2** | the registry's folder prefix bug is `folder.rstrip("/") + "/"` producing `"/"` | exactly that (`registry.py:63-65`), **and** `Scope.for_session` already guards it (`scope.py:59`, `if folder.strip("/")`) | the finding stands and is *sharper*: the app learned this lesson and the registry re-introduced it one layer down. `[R-1]` moves the rule into `fence_rules.require_folder` so there is one guard |
| **C3** | `check_path` is wired and the SQL/job/app checks are not | correct — but `check_path` is wired **twice** (`/workspace/fence` at `:754`, `/workspace/save` at `:782`), which the spec did not say | §A records both call sites; `[R-8]` is about the other four |
| **C4** | `_snapshot()` has `version: 1` and `restore()` raises on anything else | correct (`orchestrator.py:168-169`) — and **`Session(**row["session"])` would raise `TypeError` on an unknown key**, which is a *second* failure path the spec had not seen | `[RB-3]`'s "columns, not JSON" is now justified by two failures, not one |
| **C5** | `MAX_TURNS = 200` is hardcoded and `settings.max_turns_per_session` has no reader | correct on both counts (`orchestrator.py:64`, `config.py:100`). But `settings.max_tools` (`config.py:101`) is **also** unread | `[F-10]` names both. `[R-11]` wires `max_turns_per_session`; `max_tools` is recorded as a third unread setting and left alone, since the 28-tool budget is a test, not a setting |
| **C6** | `session.compacted` is emitted by nobody | correct: it appears at `events.py:37`, in `events.ts:13,24`, and in `event-parity.json` — and `rg '"session.compacted"' api` finds **only** the declaration | `[F-10]` stands; `[R-11]` adds the producer, and the plan adds `test_every_event_type_has_a_producer` so this cannot recur |
| **C7** | the front end has 959 assertions | it has **959 tests** and **1 594 `expect(`** calls; `docs/08:681` calls them assertions | recorded in [02 §7](02-assessment-opengenie.md#7--documentation-drift). The set quotes tests, not assertions |
| **C8** | `web/src/domain/reduce.ts` is the reducer | the file does not exist; `reduce()` is at `events.ts:169` | [02 §7](02-assessment-opengenie.md#7--documentation-drift) records the doc drift; **every citation in this set points at `events.ts`** |
| **C9** | "the agent does not hold a workspace token" (docs 08, 09) | `orchestrator.py:578` sets it on the child, and `agent_config.py:63` interpolates it as `apiKey` | `[F-3]` is a finding about **the documentation**, and `[R-4]` requires the claim and the code to be reconciled with a test either way |

| **C10** | the turn machine was assumed to guard its terminal states, because `start()` guards its source | `finish()` guards only the **target** (`session.py:113-121`), so all 8 statuses may finish as any of 5 terminals | `F-12` promotes this from an assumption to a **finding with a requirement** (`[R-26]`), and the 8×5 matrix becomes a test |
| **C11** | `ClosedReason` was assumed to describe the machine, since `describe()` switches over it exhaustively | `afterFailure` can never produce `"offline"` (`stream.ts:74-82`), so one member is dead and the exhaustive switch looks total over a state that cannot occur | `[R-27]` requires a **reachability** test, not a coverage test — a union is not a proof |
| **C12** | `run_word(life_cycle, result)` was assumed to read `result` only when it exists, and `result` was assumed to exist only when terminal | the platform sends `result_state` on `TERMINATING` (and the code reads it whenever present), so 24 of 60 `ACTIVE × RESULT` cells show a finished word beside a live Cancel | `[R-28]` makes the word a function of **both** axes; the grid, not a sample, becomes the fixture |

The three that change the plan are **C4** (the migration must be columns), **C9** (the security story
must be restated) and **C12** (a shared fixture gains a grid). The rest sharpen the findings without
changing a phase.

---

## A · The fence

| Claim | File:line | Verdict |
|---|---|---|
| `_check_sql_scope` returns `None` when no schema is configured | `tools/databricks_notebook_mcp.py:375-378` | ✓ **C1** |
| it refuses when it cannot identify a write target | `tools/…:379-381` | ✓ and this is the fallback `[E-3]` pins |
| `_check_path_scope` rejects `..` before the prefix test | `tools/…:421-426` (the comment names spec 013's own `E-27`) | ✓ correct, do not touch |
| `_check_path_scope` treats an empty prefix list as unrestricted | `tools/…:427-429` (`if WRITE_PATHS and not any(...)`) | ✓ **`F-1`** |
| `WRITE_PATHS` / `WRITE_SCHEMAS` parse comma lists | `tools/…:355-356` | ✓ |
| the registry passes `schema or ""` and `folder.rstrip("/") + "/"` | `api/adapters/mcp/registry.py:64-65` | ✓ **C2** |
| the registry passes `NBMCP_ALLOW_WRITES=1` unconditionally | `registry.py:63-65` | ✓ **`F-8`** |
| `Scope.for_session` keeps an empty folder empty | `api/domain/scope.py:56-61` (with the comment about the wildcard) | ✓ the app is right |
| `_inside` returns `False` for an empty or root folder | `scope.py:84-96` | ✓ the app is right |
| `check_sql` answers `ASK` for a destructive statement anywhere | `scope.py:214-223` | ✓ |
| `check_sql` answers `ASK` when the target cannot be placed | `scope.py:230-237` | ✓ |
| `check_path` is called from two routes | `api/routers/api.py:754`, `:782`, `:1214` | ✓ **C3** — three routes, not two |
| `check_sql`/`check_job`/`check_app`/`check_instance` have no production caller | `scope.py:204,255,263,274`; `rg` → definitions + `tests/` only | ✓ **`F-7`** |
| the parity test's cases all set a folder and a schema | `tests/test_fence_parity.py:21-23,63-140` | ✓ and it is why `F-1` escaped |
| the parity table has an intentional app/tool disagreement for a destructive statement inside the fence | `tests/test_fence_parity.py:105-110` | ✓ good; `[R-9]`'s `ask` mode is how the tool side gains the human |
| the two runtimes cannot share a module | `tests/test_fence_parity.py:1-8`; `registry.py:86-92` spawns a separate interpreter | ✓ **`[RB-1]`** |

## B · The tool server and payloads

| Claim | File:line | Verdict |
|---|---|---|
| `MAX_CHARS` defaults to 6 000 | `tools/…:67` | ✓ |
| `_trim` byte-slices and appends a notice | `tools/…:279-284` | ✓ **`F-2`**, measured unparseable |
| `_trim` is the return path of 20+ tools | `tools/…` — 20 call sites | ✓ |
| `read_notebook` has an explicit `next_offset` | `tools/…:668-690` | ✓ **and this is the contract `[R-3]` generalises**: the repo already solved it for two tools |
| `grep_notebook` has an explicit `no_matches` with a hint | `tools/…:757` | ✓ same |
| `_retry` does not retry a POST except 429/503 | `tools/…:287-296` | ✓ and it is why `dbx_run_job` carries an idempotency token (`:1279`) |
| the `core` profile is 28 names and a test holds it | `tools/…:75-88`; `tests/test_tools_fence.py:220-227` | ✓ |
| the UI label is held to the server's set | `tests/test_tools_fence.py:295-310` | ✓ |
| 41 tools are defined, 13 outside `core` | measured: `def dbx_*` → 41, `_CORE` → 28 | ✓ |
| a tool that left `core` must be named by a skill | `tests/test_tools_fence.py:229-250`; `DEPARTED` | ✓ and `[R-18]` must not break it |

## C · The journal and the stream

| Claim | File:line | Verdict |
|---|---|---|
| `commit()` upserts the **whole** snapshot per event | `api/adapters/durable/postgres.py:58-74` | ✓ **`F-4`** |
| the snapshot is written and the event appended in **one** transaction, then published | `postgres.py:62-73` | ✓ the order is the durability guarantee; `[R-5]` must preserve it |
| every commit takes one process-wide asyncio lock | `postgres.py:62` (`self._lock`) | ✓ and this is the throughput point `[RB-11]` makes |
| `since()` pages with `LIMIT` | `postgres.py:80-84` | ✓ |
| a slow viewer is dropped and forced to replay | `api/adapters/memory/broadcast.py:26-31` | ✓ |
| the snapshot whitelists its fields | `orchestrator.py:144-155` | ✓ and it is why `[R-9]`/`[R-24]` add **columns**, not fields |
| `restore()` raises on an unknown version | `orchestrator.py:168-169` | ✓ **C4** |
| `restore()` marks every non-archived session `BLOCKED + requires_resume` | `orchestrator.py:185-190` | ✓ **`F-9`** |
| `evict_archived()` pops the projection | `orchestrator.py:402-409` | ✓ |
| `get()` raises `KeyError` and the router answers 404 | `orchestrator.py:260-264`; `routers/api.py:208-213` | ✓ **`F-9`** |
| nothing rehydrates a session on read | `rg 'def get\(' → _live[session_id]` only | ✓ |
| the state machine permits `blocked -> ready` | `api/domain/session.py:51` | ✓ so `[R-10]` adds no state |
| the SSE handler re-reads `since(seq)` after each wake | `routers/api.py:392-400` | ✓ the "queue is a wake-up" rule |
| `?after=` and `Last-Event-ID` are both honoured | `routers/api.py:376-378` | ✓ |
| the client resets its cursor per page load | `web/src/hooks/useSessionStream.ts:166` | ✓ and `[R-14]` must keep this per **session** |
| `append()` caps at 200 000 and is O(n) per delta | `web/src/domain/events.ts:160-167,218` | ✓ **`F-5`** |
| the mapper emits one event per chunk | `api/adapters/acp/mapper.py:108-112` | ✓ |
| `_drain` emits every item | `orchestrator.py:1055` | ✓ |
| there is no coalescing anywhere | `rg 'coalesc' api` → none | ✓ `[R-6]` is new code, not a setting |
| `sessions_for` sorts by `s.id` | `orchestrator.py:266-276` | ✓ **`F-6`** |
| an id is `uuid4().hex[:16]` | `orchestrator.py:455` | ✓ measured: five ids, not descending |
| `read_ledger` globs every file | `api/adapters/mcp/registry.py:137-164` | ✓ **`F-11`** |
| the ledger route returns all of it | `api/routers/jobs.py:112-120` | ✓ |

## D · Identity, tokens and the agent child

| Claim | File:line | Verdict |
|---|---|---|
| `_child_env` sets `DATABRICKS_TOKEN` on the child | `orchestrator.py:570,578` | ✓ **`F-3`** |
| the runtime merges `spec.env` into the child's environment | `api/adapters/acp/runtime.py:45,57` | ✓ |
| `opencode.json` interpolates it as the provider key | `api/adapters/acp/agent_config.py:63,162` | ✓ **C9** |
| two pages say the opposite | `docs/08-architecture.md:147`; `docs/09-security.md:63` | ✓ **`F-3`** |
| the builtins are denied in the config | `agent_config.py:31,166` | ✓ |
| the ACP handshake declares `fs: false, terminal: false` | asserted by `tests/test_agent_isolation.py` (two layers) | ✓ so the design is safe **today** |
| the tool server reads the token from a `0600` file per call | `tools/…:_token()`; `orchestrator.py:618-648` | ✓ |
| a second token file exists for the app's SP | `orchestrator.py:650-666`; `adapters/databricks/sp_token.py` | ✓ |

## E · Models, cost and compaction

| Claim | File:line | Verdict |
|---|---|---|
| 13 models over 4 providers in the seed | `seed/llm_models.yaml` — measured: 13 ids, providers `databricks, openai, anthropic, google_vertex` | ✓ |
| the turn is pinned before the prompt and never rewritten | `orchestrator.py:889,902-921` | ✓ |
| `llm.llm_turn_model` records the pin | `migrations/001_llm_schema.sql:124-138` | ✓ so `[R-24]` can sum cost without a new source |
| a switch during a turn applies to the next turn | `orchestrator.py:680-709` | ✓ **`[E-8]`, `[E-23]`** |
| limits carry an evidence grade | `llm_model.limit_evidence` CHECK in `:34-59`; `domain/llm/limits.py` | ✓ **`[E-24]`** |
| `session.compacted` is declared and never emitted | `events.py:37`; `events.ts:13,24`; `event-parity.json` | ✓ **`F-10`** |
| `MAX_TURNS` is a constant | `orchestrator.py:64` | ✓ |
| `settings.max_turns_per_session` has no reader | `config.py:100`; `rg` → the definition only | ✓ **C5** |
| `settings.max_tools` has no reader either | `config.py:101`; `rg` → the definition only | ✓ **C5**, newly found |
| `MAX_CONTINUATIONS = 5`, `MAX_AUDITS = 2` | `api/domain/supervisor.py:46-47` | ✓ both are product decisions with comments |
| the parity fixture is the front end's source of truth | `tests/test_event_parity.py:39-47` | ✓ and `[R-11]`/`[R-22]` must update it |

## F · The front end

| Claim | File:line | Verdict |
|---|---|---|
| the reducer is `reduce()` in `events.ts` | `web/src/domain/events.ts:169` | ✓ **C8** |
| `MAX_ANSWER` is 200 000 | `events.ts:160` | ✓ |
| there is one stream per page | `web/src/App.tsx:246` — one `useSessionStream(active)` | ✓ **`[R-14]`** |
| the rail searches title and folder | `web/src/domain/sessions.ts:47-52` | ✓ **`[R-15]`** |
| the day-grouping is correct and separate | `sessions.ts:35-45` | ✓ do not touch |
| `StreamState` names `cursor-ahead` as terminal | `stream.ts:26-34` | ✓ **`[E-17]`** |
| `diff.ts::minimalChange` has one caller, which maps a remote edit | `editor/diff.ts:6`; caller `editor/codemirror.ts` | ✓ and it is **not** an accept/reject proposal — `[R-22]` is new |
| `DocKind` has 8 members | `domain/docs.ts:10` | ✓ |
| the composer has 12 slash commands | `domain/commands.ts:9-22` | ✓ |
| `layout.ts` keeps `CENTRE_MIN` at 480 | `layout.ts:41`, `:110-160` | ✓ and F10 is drawn at 820 px accordingly |
| `blob.ts` mirrors `blob.py`'s limits | `web/src/domain/blob.ts:12-14`; `api/domain/blob.py:28-29,30` | ✓ so `[R-21]` must change both |
| attachment families are image/text/notebook/pdf/other | `api/domain/blob.py:228-236` | ✓ **no xlsx** |
| notebook structural undo exists, content undo is CodeMirror's | `web/src/components/NotebookEditor.tsx:144-207` | ✓ |
| CodeMirror has `autocompletion()` with no async source | `web/src/editor/codemirror.ts:149` | ✓ so `[G-19]`'s refusal is grounded |

## G · The contract between the two halves

| Claim | Where | Verdict |
|---|---|---|
| the event vocabulary is held by a JSON fixture plus a test | `tests/test_event_parity.py`, `web/src/domain/event-parity.json` | ✓ and it compares **declarations**, which is why `F-10` survived |
| the fence is held to one table across two runtimes | `tests/test_fence_parity.py` | ✓ for the cases it contains ⚠ **the empty cases are missing** |
| `MAX_ATTACHMENTS` is one number in two places | `api/domain/context.py:21`, `api/domain/blob.py:30`, `web/src/domain/blob.ts:14` | ⚠ **three** places, and `test_blob_rules.py` asserts only the Python pair. `[R-21]` must not add a fourth |
| `TOOL_COUNT_CORE` is held to `_CORE` | `tests/test_tools_fence.py:295-310` | ✓ the model `[R-18]` should copy |
| the error contract is one mapping | `api/routers/api.py:_dbx_errors` | ✓ reused by every route in this plan |

## G2 · The state machines, transition by transition

Every machine was enumerated against the code, not read. The command for each is in
[07 §16](07-diagrams.md#16--reproducing-every-proof).

| Claim | File:line | Verdict |
|---|---|---|
| `_ALLOWED` has 6 states, 1 absorbing (`archived`), 0 unreachable | `api/domain/session.py:42-52` | ✓ measured |
| `blocked → failed` is forbidden both ways | `session.py:51` | ✓ deliberate: a question is not broken machinery |
| `start()` guards its source (`QUEUED`, `INTERRUPTED`) | `session.py:108-111` | ✓ |
| `finish()` guards only its **target** | `session.py:113-121` | ✓ **`F-12`**, measured over 8×5 |
| the timeout handler finishes a turn by id, after unwinding | `orchestrator.py:946-948` | ✓ the reachable path for `F-12` |
| `ClosedReason` declares 4 members | `web/src/domain/stream.ts:25-33` | ✓ |
| `afterFailure` returns `reconnecting` for every offline case | `stream.ts:74-82` | ✓ so `closed:offline` is unreachable — **`F-13`**, BFS-proved |
| `describe()` is a `switch` with no `default` | `stream.ts:119-143` | ✓ total over 8 states, all 8 produce words |
| `MISSION_STATES` is a `Record` of 14 | `mission.ts:120-135` | ✓ 14 declared, 14 reachable, 0 without copy |
| `missionView` precedence: archived > recovery > waiting > turn | `mission.ts:140-151` | ✓ |
| the connection cannot change the mission state | `mission.ts:150` (`paused` only) | ✓ the inversion spec 012 fixed |
| `achieved` requires **all** proof verified | `mission.ts:108-112` | ✓ |
| supervisor: 4 verdicts, `MAX_CONTINUATIONS=5`, `MAX_AUDITS=2` | `supervisor.py:16-19,46-47` | ✓ |
| the verdict grid covers 9 scenarios | `supervisor.py:77-112` | ✓ measured; `F-17` is row 4 |
| `RUN_LIFE_CYCLE` = 9, `ACTIVE` = 6, `TERMINAL` = 3 | `jobs.py:28-63` | ✓ |
| `run_word` prefers `result` whenever present | `jobs.py:213-216` | ✓ **`F-14`**, 24 of 60 cells contradict |
| `can_cancel == is_active` | `jobs.py:267-270` | ✓ so a terminal word and a Cancel coexist |
| `pipeline_word` prefers the **update** | `jobs.py:232-241` | ✓ correct — the model for the run fix |
| `RunState` = 5, `result_from_statement` is total | `cellrun.py:28-34,126-162` | ✓ total, and `F-15` is in the fallthrough |
| `refused` is not an error state | `cellrun.py:165-167` | ✓ |
| `retention` checks refcount **before** state | `retention.py:75-88` | ✓ **`F-16`**, measured |
| both reaper rules are total with a `Why`/`Disposition` | `reaper.py:66-88`, `projection.py:67-84` | ✓ every input named, none raises |
| `StepState` = 4, `done` requires a non-empty proof field | `scaffold.py:26-29,94` | ✓ |
| `ModelState` = 6, `unknown` is usable | `llm/model.py:89-101` | ✓ |
| the approval token is 120 s, and every failure is a plain `False` | `approval.py:34,53-64` | ✓ measured over 8 inputs |

## H · The environment

| Claim | Check | Verdict |
|---|---|---|
| Python tests pass | `pytest -q` → **1303 passed, 7 skipped in 17.77s** (and again in 31.06s) | ✓ green in every run |
| front-end tests pass | `vitest run` → **959 passed, 69 files** in 4 of 5 runs; 1 unnamed failure once | ⚠ **one flaky test**, recorded in [01 §1.2](01-method-and-evidence.md#12-the-baselines-run-for-this-assessment). Phase 1 must find and fix it |
| the ASCII verifier passes on this set | `verify-spec-ascii.mjs` → **22 blocks, 11 boxes, 0 problems** | ✓ |
| the mermaid verifier parses this set | `verify-spec-mermaid.mjs` → **26 diagrams, 0 failing** | ✓ |
| every internal link and anchor resolves | 16 documents, GitHub slug rule, **0 broken, 0 unresolved** | ✓ |
| every `[F-]`/`[R-]`/`[RB-]`/`[E-]`/`[S-]`/`[L-]`/`[G-]` citation is defined exactly once | script over all 16 documents | ✓ 0 undefined, 0 unused |
| the wireframes are generated, not hand-drawn | `tools/build_wireframes.py`; the file says so | ✓ so a box cannot drift |
| the exam suite is the regression gate for `[R-17]`/`[R-18]` | `exams/run_exam.py`, `site/claims.py` | ✓ and `claims.py` runs today: CL-1 100% (37/37, 3 runs) |

---

## What the coherence check found that the plan had missed

Five additions, each now a numbered requirement, edge case or roadblock rather than a note in prose.

1. **`settings.max_tools` is a second unread setting** (C5). Not a bug — the tool budget is a test, not
   a knob — but the spec must say so, or a reader will "fix" it and break the budget.
2. **`Session(**row["session"])` is a second failure path on a snapshot version bump** (C4). This is
   what makes "columns, not JSON" the *only* safe migration choice rather than a preference.
3. **`MAX_ATTACHMENTS` already lives in three places, not two** (§G). `[R-21]` adds a family, so the plan
   needs a test that all three agree — otherwise the fourth place is the one that drifts.
4. **`check_path` is wired three times, not once** (C3). `[R-8]`'s reachability test must not count "one
   caller" as "wired"; it must count **distinct routes**.
5. **The parity test compares declarations, not producers** (§G). That is why `session.compacted` and
   `F-10` survived a green suite. `[R-11]` adds `test_every_event_type_has_a_producer`, and it belongs to
   the plan's phase 2, not to a wish.

---

## The claims this set makes that the code will *not* settle

Stated so no one mistakes them for verified.

| Claim | Why the code cannot settle it | Where it is flagged |
|---|---|---|
| "≈1.8 GB per turn" | depends on the agent's chunk size, which is not measured here | [01 §2.2](01-method-and-evidence.md#22-executed-a-scale-computed-from-a-real-object) states it as shape + order of magnitude |
| "Genie Code has X" | documentation, not observation, and it ships weekly | [03](03-comparison-genie-code.md) marks `[doc]` per row; sources dated in [01 §3](01-method-and-evidence.md#3--the-external-sources-with-their-dates) |
| "Claude Code has 33 hook events" | a third-party comparison read on 2026-10-12 | [04 §2.1](04-comparison-best-agents.md#21-the-coding-loop) marks the source |
| "the exam score does not regress" | requires running the exam suite, which costs model calls | [11 §3](11-implementation-plan.md) makes it a gate, not an assumption |
| "a loopback proxy costs one hop" | unmeasured here; `ug` does it, which is evidence it works and no evidence of the latency | `[RB-4]` |
| "no market agent ships per-claim evidence" | a negative claim about four products | [04 §5](04-comparison-best-agents.md#5--the-one-sentence-answer-to-how-does-it-compare-with-the-best-coding-agent-for-data-engineering) states it as a judgement, with the basis named |

---

## The gate

Before phase 1 begins, this table must be re-checked against a fresh `git log -1`, because a claim
verified at `2063af3` is a claim about `2063af3`.

```bash
cd /Users/raphaelmansuy/Github/03-working/opengenie/apps/coding-agent
git -C /Users/raphaelmansuy/Github/03-working/opengenie log --oneline -1     # expect 2063af3 or record a new one
.venv/bin/python -m pytest -q
( cd web && npx vitest run )

# the four claims that matter most, re-measured
rg -n "if not WRITE_SCHEMAS" tools/databricks_notebook_mcp.py      # F-1, line 377
rg -n 'env\["DATABRICKS_TOKEN"\] = user_token' api/services/orchestrator.py   # F-3, line 578
rg -n "return text\[:MAX_CHARS\]" tools/databricks_notebook_mcp.py # F-2, line 284
rg -n "key=lambda s: s.id" api/services/orchestrator.py            # F-6, line 274

# the two spec verifiers
node web/scripts/verify-spec-ascii.mjs ../../specs/001-opengenie-assessment
NODE_PATH=/tmp/mmd/node_modules JSDOM_PATH=/tmp/mmd/node_modules/jsdom/lib/api.js \
  MERMAID_PATH=/tmp/mmd/node_modules/mermaid/dist/mermaid.core.mjs \
  node web/scripts/verify-spec-mermaid.mjs ../../specs/001-opengenie-assessment
```

If any of the four `rg` commands returns nothing, the finding it names has been fixed since this set was
written — which is the best possible outcome, and the plan should drop that step rather than re-fix it.

Next: [15 · E2E plan](15-e2e-plan.md).
