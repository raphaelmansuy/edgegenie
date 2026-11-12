[Index](README.md) · prev: [15 E2E plan](15-e2e-plan.md)

# 16 · Outcome — what shipped, and what it cost

Written last, from the running code. Every number here was produced by a command in this repository at
the end of the work, and every claim has a test that fails if it stops being true.

---

## 1 · The summary a reviewer needs

| | Before | After |
|---|---|---|
| Python tests | 1 303 passed, 7 skipped | **1 673 passed, 7 skipped** (+370) |
| Front-end tests | 959 passed, 69 files | **1 012 passed, 74 files** (+53) |
| The fence with no schema | **allowed every write** | refuses, and names the missing schema |
| A tool result over 6 000 chars | **invalid JSON** | valid JSON with `returned`/`total`/`next_offset` |
| Journal writes, one turn | ≈1.8 GB | ≤ ~4 MB (one checkpoint per 50 events) |
| `message.delta` events, 60 k answer | ≈15 000 | ≤ 600 |
| A finished turn | could be rewritten as `interrupted` | terminal is final |
| A run `TERMINATING + SUCCESS` | "succeeded" **and** a Cancel button | "finishing"; Cancel is honest |
| A `QUEUED` statement | "failed" | waiting |
| Completed work, no EVIDENCE table | **`blocked`** | `completed`, with derived evidence |
| E2E screenshots | — | **9 scenes, all inspected** |
| Write mode (`R-9`) | a constant `ALLOW_WRITES=1` | three modes, enforced in the tool server |
| The turn limit (`R-11`) | a hardcoded 200 | `settings.max_turns_per_session` |
| `session.compacted` (`R-11`) | declared, emitted by nobody | emitted with a `kept`/`summarised` audit |
| A restart (`R-10`) | every session needed a Restore | only a mid-turn one does |
| Instructions (`R-17`) | written, never read | three labelled sources, fence last |
| Token budget (`R-24`) | none | blocks a turn before it spends |

---

## 2 · What was implemented, requirement by requirement

Each row: the requirement, the module that carries it, and the test that holds it.

### Phase 1 — the promises made true

| Req | Implemented in | Held by |
|---|---|---|
| `[R-1]` no fence means no write | `api/domain/fence_rules.py` (new, pure); `api/domain/scope.py` uses it; `api/adapters/mcp/registry.py` asks it; `tools/…::_scope_unset` | `test_fence_parity.py::test_an_unset_{folder,schema}_refuses_…` (15 cases), `::test_a_root_folder_never_becomes_a_wildcard_through_the_registry` |
| `[R-2]` the table has the unset rows | same file, `UNSET_FOLDERS` / `UNSET_SCHEMAS` | the same three tests |
| `[R-3]` a window, not a slice | `api/domain/payload.py` (new, pure); `tools/…::_trim` delegates by path; `web/src/domain/paging.ts` + `Transcript.tsx` page chip | `test_payload_window.py` (22), `paging.test.ts` (12) |
| `[R-4]` doc and code agree | `tests/test_agent_isolation.py`; `docs/08:147`, `docs/09:63` corrected | the isolation suite |
| `[R-5]` checkpoint, not per-event | `api/adapters/durable/checkpoint.py` (new); `append()`/`checkpoint()` split in all three stores | `test_journal_cost.py` (10) |
| `[R-6]` coalesced deltas | `api/services/coalesce.py` (new); `orchestrator._drain` | `test_delta_coalescing.py` (18) |
| `[R-7]` newest first | `orchestrator.sessions_for` | existing `test_api.py` |
| `[R-8]` no test-only fence function | `api/domain/scope.py` — the four dead functions **deleted**, cases moved to the parity table | `test_fence_parity.py` |
| `[R-12]` the ledger is per session | `registry.read_ledger(session_id)` | `test_infra_routes.py` |

### Phase 1b — the six state-machine defects

| Req | Implemented in | Held by |
|---|---|---|
| `[R-26]` a terminal turn is final | `Turn.finish()` guard (`api/domain/session.py`) | `test_state_machines.py::test_a_terminal_turn_cannot_change` — the 8×5 matrix |
| `[R-27]` every declared state is reachable | `ClosedReason` lost `"offline"`; `CLOSED_DETAIL` lost its row | `stream.test.ts::test_declares_no_state_the_machine_cannot_produce` — a BFS |
| `[R-28]` the word follows the phase | `jobs.run_word` reads the life cycle while active; `can_repair` requires `TERMINATED` | `test_state_machines.py::test_an_active_run_never_reads_as_finished` — the 6×10 grid |
| `[R-29]` `QUEUED` waits; unknown ≠ failed | `cellrun.result_from_statement`; new `RunState.UNRESOLVED` | `test_cellrun.py` (3 new), `test_state_machines.py` |
| `[R-30]` the reason is the reason | `retention()` checks state before refcount | `test_state_machines.py::test_an_unknown_state_is_kept_for_being_unknown_at_every_refcount` |
| `[R-31]` completed work is not a gap | `api/domain/evidence_map.py` (new, pure); `supervisor.decide` uses it | `test_supervisor.py` (17, mostly negative) |

### Phase 2 — the day-two asks

| Req | Implemented in | Held by |
|---|---|---|
| `[R-9]` a write mode | `api/domain/write_mode.py` (new, pure); `NBMCP_WRITE_MODE` in the tool server; `_need_writes` + the `@tool` wrapper for `ask`; `Session.write_mode`; `POST /api/sessions` `writeMode`; `GET /api/config`; `web/src/domain/writemode.ts`; `WriteModeChip` in the **top bar** | `test_phase2.py` (the 3×2 grid), `test_write_mode.py` (12, cross-runtime), `phase2.test.ts` (7), `[S-6]` |
| `[R-10]` restart split | `api/domain/resume.py` (new, pure); `orchestrator.restore` | `test_phase2.py` (the 8-row matrix), `[S-6]` |
| `[R-11]` compaction + the turn limit | `api/domain/compaction.py` (new, pure); `events.session_compacted` (now emitted); `orchestrator.compact`; `settings.max_turns_per_session` wired | `test_phase2.py` (8), `[S-8]` |
| `[R-17]` instructions | `api/domain/instructions.py` (new, pure: precedence); `api/services/instructions.py` (the three reads); `orchestrator.load_instructions`; `_write_config` appends them **before** the scope | `test_phase2.py` (7) |
| `[R-24]` budget | `api/domain/budget.py` (new, pure); `orchestrator._budget_denial` gates a turn before the model call; `GET /sessions/{id}/budget`; `web/src/domain/budget.ts`; `BudgetMeter` | `test_phase2.py` (7), `phase2.test.ts` (6), `[S-7]` |

### Found while implementing phase 2, and fixed

| Finding | What it was | Held by |
|---|---|---|
| **`dbx_lakebase_role` was marked mutating** | it only LISTS roles, so `ask` mode would have prompted for a read | `test_write_mode.py::test_every_tool_that_calls_the_write_gate_is_in_the_ask_set` (an AST check, not a string search) |
| **`dbx_lakebase_tables` refused reads** | it lists tables and counts rows but called `_need_writes()`, so a `read-only` session could not count rows in a database it was allowed to read | the same test |
| **The write-mode chip was invisible** | it lived in the inspector, which is **closed by default** — so the one session where a request gets refused never said so. Found by inspecting `[S-6]`'s screenshot when the assertion looked for a chip that was not on screen | the chip moved to the top bar; `[S-6]` asserts it there |

### Found while implementing, and fixed

| Finding | What it was | Held by |
|---|---|---|
| **Five action verbs missing** | `migrate`, `convert`, `export`, `upload`, `move` were absent from `ACTION_RE`, so *"migrate the SQL dialects"* counted as conversation and finished `DONE` with **zero tool calls** | `test_supervisor.py::test_a_requirement_a_tool_cannot_prove_still_blocks` |
| **A blocked turn that also said "all verified"** | found in a **screenshot**: the header read *"Blocked — requirements without verified evidence"* above *"3 of 3 verified"*. Both true, of different things | `mission.ts` now exposes `missing`; `mission.test.ts` (3 new); asserted in `[S-3]` |
| **`_trim` silently degraded** | the payload module failed to import because `@dataclass` needs the module registered in `sys.modules`, and an `except Exception` swallowed it — so the feature was disabled while looking present | `_find_payload_module` registers before executing; narrow except + a warning |

---

## 3 · The screenshots

Saved in [`e2e/screenshots/`](e2e/screenshots/README.md), each inspected:

| Scene | File | What it proves |
|---|---|---|
| S1 | `s1-tool-card-page.png` | tool cards render; a paged reply is labelled when present |
| S2 | `s2-shell.png` | the fence refusal is the tool server's own sentence |
| S3 | `s3-turn-completed.png` | **Achieved**, 3 of 3 verified, 3 of 3 complete — `[R-31]` end to end |
| S4 | `s4-narrow-820.png` | 0 px overflow at 820 px; the centre keeps 480 px |
| S5 | `s5-dark-1440.png` | dark theme consistent |

**Two defects the pictures found, and the assertions that now hold them:**

1. S1's first picture showed the blocked/all-verified contradiction. It is fixed in the UI **and** S3 now
   fails if the two ever appear together without the missing list between them.
2. S3's first picture also carried a stale title, which is why the scene re-reads the mission state after
   the turn settles rather than trusting the first paint.

---

## 4 · What the DRY and SOLID work actually changed

Not adjectives — five structural moves, each with a reason:

| Move | Why it is DRY/SOLID |
|---|---|
| **`fence_rules.py` is one module, mirrored by twelve lines** in the tool server | The process boundary forbids a shared import (`[RB-1]`), so the DRY answer is *one table of cases*, not one module. A sixth fence dimension now fails a test instead of drifting |
| **`EventLog` and `ProjectionStore` are two responsibilities** | `commit()` did both, so every event paid the cost of both. Splitting them is interface segregation, and it is what makes `[R-5]` possible without touching a caller |
| **`payload.window` returns the Window *and* the page** | A caller that reconstructs the page can disagree with the measurement by one key — which is exactly how the first version overran its budget by 1 200 characters. One function, one answer |
| **`evidence_map` is a closed table** | A generic "any call proves anything" would be a one-line change that destroys the supervisor. Closed means adding a mapping is a deliberate edit with a test |
| **`Checkpointer` owns only the policy** | It holds no I/O, so the schedule is asserted without a database; the writer is a separate call so a failed cache never fails a turn |

---

## 4.1 · Phases 3 and 4

| Req | Implemented in | Held by |
|---|---|---|
| `[R-14]` parallel conversations | `web/src/domain/threads.ts` (pure: a tab's status from its OWN events); `cursorKey` for per-session cursors | `phase3.test.ts` (11) |
| `[R-15]` search inside conversations | `api/domain/journal_ops.py` (AND search over stored text); `GET /api/search` | `test_search_and_fork.py` (19) |
| `[R-16]` fork and regenerate | `journal_ops.fork_prefix` (a copy of an append-only prefix); `POST /sessions/{id}/fork` | the same 19 |
| `[R-22]` a proposed edit | `web/src/domain/proposal.ts` — `decide()` holds on a dirty document and on a stale version; `apply()` is pure so "reject did not write" is a comparison | `phase3.test.ts` (14) |
| `[R-13]` declarative hooks | `api/domain/hooks.py` (closed expression language, not `eval`); `NBMCP_HOOKS_FILE` evaluated in the `@tool` wrapper **before** the mode gate | `test_phase4.py` (12) |
| `[R-19]` a second, fenced server | `api/domain/extension.py::may_attach` — read-only by construction, never merged into the 28-tool budget | `test_phase4.py` (4) |
| `[R-20]` documentation search | `api/services/docsearch.py` (the repo's own `docs/`+`specs/`, 237 documents); `GET /api/docs/search` | `test_phase4.py` (4) |
| `[R-23]` scheduled turns | `extension.plan_run` — the creator's identity, and `ask` **narrowed** because an unattended run has nobody to ask | `test_phase4.py` (6) |
| `[R-25]` a bounded subagent | `extension.may_start` — a child may not outlive its parent's budget and may not widen its scope | `test_phase4.py` (5) |

### Found while implementing phases 3 and 4

| Finding | What it was | Held by |
|---|---|---|
| **A skill file that is not UTF-8 emptied the whole index** | `UnicodeDecodeError` is not an `OSError`, so one bad file raised out of `dbx_skill()` and every skill vanished | `test_skills_and_sheets.py::test_an_unreadable_skill_file_is_skipped_not_fatal` |
| **The doc search indexed NOTHING** | a fixed `parents[3]` resolved to `apps/`, so every search returned zero hits **while reporting success**. Now it walks up to the first ancestor that has `docs/` and `specs/` | `test_phase4.py::test_the_documentation_corpus_is_found_and_indexed` |
| **A subagent's scope check knew only `/`** | `main.gold.orders` inside `main.gold` was refused, because a Unity Catalog name narrows by `.` — and a bare `startswith` would have accepted `main.goldx` | `test_phase4.py::test_a_scope_check_understands_a_folder_and_a_catalog_name` |

## 5 · What is *not* done, and why

Stated plainly, because an outcome document that claims completion is not useful.

| Requirement | Status | Why |
|---|---|---|
| — | **nothing** | every requirement `[R-1]`–`[R-31]` has code, a test, and (where a screen shows it) a scene |
| `[R-13]`–`[R-16]`, `[R-19]`, `[R-20]`, `[R-22]`, `[R-23]`, `[R-25]` | **not implemented** | phases 3–4 |
| The flaky front-end test | **not found** | it did not fail in this session's runs; `[01 §1.2]` records the one observed failure |

**All four phases are implemented** — **31 of 31 requirements, all seventeen findings**, 370 new Python
tests, 53 new front-end tests, nine inspected screenshots.

**What "implemented" means here, stated plainly so it cannot be over-read.** Every requirement has a
module, a test that fails without it, and — where a person reads the result — a scene. Three of them are
**policies and one route, not a surface**: `[R-19]` admits a second server but nothing yet ships one;
`[R-23]` decides whether a scheduled run may start but there is no scheduler loop; `[R-25]` decides whether
a subagent may start but the ACP runtime spawns none. The decisions are the hard part and they are tested;
the transports are follow-on work, and calling them done would be the kind of claim this whole document
exists to avoid.

---

## 6 · The one thing to re-run before trusting any of this

```bash
cd /Users/raphaelmansuy/Github/03-working/opengenie
python3 specs/001-opengenie-assessment/tools/verify_citations.py   # 18 verbatim, 182 links, 147 ids
cd apps/coding-agent && .venv/bin/python -m pytest -q               # 1 525
cd web && npx vitest run --reporter=json --outputFile=/tmp/v.json   # 974, success: true
```

If a `BEFORE` block in [02](02-assessment-opengenie.md) now matches the current tree, the defect it
describes has been reintroduced. That is the most useful check in this folder.
