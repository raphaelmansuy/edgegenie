# 15 · Implementation status and validation

13 November 2026. The implementation now spans P0–P6. **The full release gate is not complete.**
The implementation map is expanded in [16-gap-assessment.md](16-gap-assessment.md);
[17-first-principles-closure.md](17-first-principles-closure.md) records the latest fixes and external app-availability blocker.
The new phases remain opt-in until the live app-path qualification below passes. This record supersedes
an earlier P0-only status report. Existing uncommitted changes for specs 012 and 013 were preserved.

## Actual target and identity

The requested app is `coding-agent` in workspace `dbc-cb61f1e1-bd8e.cloud.databricks.com`, workspace ID
7474647158015570. CLI profile `opengenie-dev` verified `raphael.mansuy@gmail.com` before fixtures were
seeded. The requested `dbxnb` identity/warehouse tools were unavailable; the CLI supplied the fallback.
The warehouse is Serverless Starter, `50b601f08d1a858d`; it was stopped at the initial inspection. Later,
the pipeline grader used this warehouse for its isolated schema and output checks.

The live app was ACTIVE at inspection, serving commit
`d2d4754e05f15dc06f41d57fdeaaa8b9ae6415e8`. **This checkout has not been synced or deployed.** Local
qualification used the actual OpenCode **1.18.19**, real served models and user credentials. No agent
code was run as the app service principal. Live mutations were confined to named disposable exam or
E2E fixtures; successful fixtures were cleaned up. Logs below identify the remaining grader checks.

## Implementation map

| Plan area | Implemented and wired | Qualification or work still required |
|---|---|---|
| P0 trust | Shared fail-closed path/SQL/verdict policy; traversal/root rejection; canonical `/Workspace` alias; minimal child environment; exact agent pin and lockfile; isolated cwd/HOME; escaped nonce context; owner checks; ACP permission/usage/diff/error mapping; bounded frames and waits; rejection ends without audit; no agent app-SP fallback; live-scope verifier | Actual pinned-agent model requests offered only `todowrite`; `skill`/`task` were absent. Original app-path baseline and timed real-agent fault matrix remain release checks. |
| P1 changes | Encrypted entity ledgers on memory/SQLite/Postgres; asset read/change/run/remove ports; registry; app-owned Toolbox and credential-free MCP facade; exact argument-bound grants; Review/Plan/Auto; revision/SHA cell and range operations; one native approval surface; Changes/diff/conflict/undo; editor refresh and draft preservation; typed operation schemas | Lifecycle responsibilities are split into provisioning/session/turn modules. Accepted turn, journal, snapshot and retry receipt now share a transaction; legacy SQLite ledgers import once into that database. All services pass adapter-import and asset-kind-dispatch checks. Native Query in-place edits and private-draft writes are deliberately gated. |
| P2 operations | Submit-once durable handles; native idempotency; observer/backoff and coalesced heartbeat; native cancellation; credential expiry as Unobserved; bounded result pages; wake once and continuation cap; restart recovery; keep-alive; Runs/stop UI with identity/last observation | Native SQL recovery now uses deterministic durable intent and exact tagged-source history lookup, qualified with dropped native/app acknowledgements and one submit. Native I/O shares a configured global admission pool (default eight); large active-operation populations still need load qualification. Separate run identity remains disabled; its verifier/runner ports and fail-closed boot/build/deployment declaration checks now implement task 2.6’s S13 fallback. The browser recovery test uses deterministic native runners, not a ten-minute live job. |
| P3 assets | Capability-filtered per-kind registry and dispatch checks; native/as-code jobs and pipelines; conditional pipeline writes; task/repair/status results; reviewed app/instance lifecycle; saved Query create/cleanup adapters; table metadata and bounded search; system observations for runs, tasks, lineage, usage and query history; attach/Fix; resources and revision-guarded cleanup | Bounded app-log ingestion and checksum-pinned CLI packaging are implemented; packaged live authentication failed twice and is not qualified. Job/pipeline bundles passed actual CLI validation. SQL-created tables now have durable resource receipts, explicit no-undo and reviewed identity/data-version guarded cleanup, qualified live. Full deployed lifecycle exams remain. |
| P4 proof/cost | Invocation-first records and result digests; explicit IDs; verified/supported/unverified/contradicted; numeric contradictions; exact later revision or successful operation floor; budget before pass/dispatch; usage uncertainty and currency checks; separate kit/app score paths; six new mission definitions M9–M14 | Full existing + new suite through the product on at least two models, and baseline comparison, remain. Monetary estimates require configured bounds; unknown usage fails closed. New mission reference validation is recorded separately below, not presented as model scores. |
| P5 scale | 100 ms/2 KiB text coalescing; transition snapshots; owner-indexed paged lists; lazy hydration/process spawn; archived eviction; SSE fast path with replay/gap fallback; separate PG read connection; turn index; bounded 30-turn browser pages and 20-row result pages; ledger paging; bounded reconcile/export cache | On-demand per-session storage reporting and guarded logical cascade are implemented. All history remains reachable with at most 30 turns mounted. Full crash-injection and high-population load qualification remain. |
| P6 parity | Bounded user-token instruction/AGENTS/skill discovery; untrusted preferences below safety rules; bundled skills; agent/template/skill slash commands; typed elicitation with answer/skip/cancel/expiry; advertised resume; notices/config/compaction | Full pinned-agent conformance recording across every advertised feature remains a release check. |

Services use ports and domain policy rather than importing adapters; adapter selection lives in the
composition root. Tool names, schemas, asset registration and edit interpretation have shared sources.
The legacy tool aliases have a removal gate and a date no earlier than 2027-02-13.

The 30-day undo retention now removes expired previous-content rows in bounded batches at startup and
maintenance. Audit and resource rows are retained. Fired/cancelled wake-ups are pruned in bounded batches; a
durable consumed-continuation receipt stays with the operation, including migration of legacy fired
rows. Guarded owner+administrator logical cascade and operator storage reporting are implemented; retained migration backups and other backups require separate retention handling. Archive remains a flag and never silently deletes native
resources.

## Local and real validation

| Check | Result |
|---|---|
| `make -C apps/coding-agent check` | **891 Python passed, 19 skipped; 642 frontend passed in 61 files; TypeScript passed** |
| Disposable local PostgreSQL contracts | **67 passed in the latest sequential rerun**, including migrations, journal/recovery, encrypted ledgers, CAS, change/undo, previous-content retention and legacy wake-up receipt migration |
| Frontend production build | Passed; existing chunk-size advisory remains |
| Trust/permission browser flow | Passed across three iterations, including rejection without automatic retry and narrow screens |
| Review/change/budget browser flow | `work-final`: 12 screenshots, passed |
| Native approval/as-code/attach/resources/cleanup/stop | `assets-gap-final`: 14 screenshots, passed; native rejection now has a neutral declined icon and no false failure warning |
| PostgreSQL operation flow | `operations-gap-final`: 6 screenshots, passed; all tabs closed, one server continuation, process restart and pruning, rearm refused, native handle retained, cancellation |
| Elicitation | `questions-final`: 5 screenshots, passed; answer by keyboard, skip, cancel, restart expiry, mobile |
| Editor | `editor-final`: 4 screenshots, passed; dirty buffer retained, incoming-source warning, local draft restored, clean editor refreshed from ledger event |
| 10/1,000/10,000 stored sessions | Boot/list loaded no stored transcript and spawned no agent. Measured 27/20/23 ms in the local contract run |
| 200-turn browser recovery | `scale-window-02`: 5 screenshots, passed; actual durable HTTP/SSE replay, all 200 turns reachable with at most 30 mounted, results paged by 20 rows, reset/mobile. Worst observed main-thread task **56 ms**; p95 scroll frame **17.3 ms** |
| Two real models, read-only capability mission | Maverick and gpt-oss-120b completed through actual app/ACP/MCP after evidence-schema corrections; these are **not full exam scores** |
| Real 60-cell notebook change and undo | `live-edit-09`: passed using served gpt-oss-120b; no write before review, exactly cell 37 changed, other 59 raw cells byte-identical, read-back verified, undo byte-identical. Final state Ready for review preserves Supported grades |
| M9 grader | Live do-nothing 4/10; reference 10/10; fixture cleaned |
| M11 pipeline grader | Live do-nothing 1/10; reference 10/10; isolated pipeline/schema fixture cleaned |
| M13 saved Query grader | Live do-nothing 0/10; reference 10/10; native parent-path alias corrected and exact owned fixture cleaned |
| M14 cleanup grader | Live do-nothing 5/10; reference 10/10; real change/resource services created, reviewed and deleted only the isolated notebook; sentinel preserved |
| M10 repair and M12 long-run graders | Live do-nothing 5/10 and 1/10; each reference 10/10; isolated job/notebook fixtures cleaned |
| Final real-model app exam M9 | gpt-oss **12/12**, Maverick **6/12** and blocked after two audits. The model printed edits as text; no edit was executed or falsely shown as achieved. This is an open release qualification result, retained with screenshots in `exam-invocation-final`. |
| Native SQL acknowledgement loss | `sql-recovery-live-02.json`: actual user SELECT; both native acknowledgement and app handle deliberately lost; both stores reopened; history recovered the same statement and actual result; **one submit**. Backend fault injection, not a model or browser exam |
| Live SQL-created table lifecycle | `live-table-01` and resumed `live-table-03`: one native create/resource, no undo, review writes nothing, exact native absence after cleanup. Latest model mission remained blocked; lifecycle pass is separate |
| Storage reporting | `storage-04`: four desktop/mobile/failure/recovery captures passed |
| Actual built-in deny probe | `native-tool-negative.json`: OpenCode 1.18.19/gpt-oss-120b requests offered only `todowrite`; no `skill` or `task` |
| Actual bundle validation | Job and pipeline handler output: zero warnings, zero deploy calls |
| Named catalogue parameters | Metadata-first capped native SELECT accepted malicious-looking text as a bound STRING |
| Live scopes | Requested app scopes matched the bundle; checkout still not deployed |
| `git diff --check` | Passed at the latest check |

The default Python gate skips database cases when DSNs are absent; the PostgreSQL run above explicitly
supplies disposable DSNs and runs sequentially. New mission definitions use native state checks and
programmatic references; an app score is recorded only by `run_exam.py --via app`. The benchmark driver
never approves arbitrary owner decisions. Review/irreversible actions require a person, even in an exam.

## Screenshot inspection and iteration

All **346 retained PNG screenshots** under [e2e/screenshots](e2e/screenshots) were individually opened
with the image viewer. Desktop and narrow layouts were checked for readable content, correct state,
visible decision controls, source/result distinction and overflow. Assertions also check page errors,
accessible controls and horizontal page bounds. This is evidence for the captured states, not a claim
of perfection or a complete accessibility audit of every application screen.

Examples of the inspection/fix/retest loop:

- Rejection originally drew a failure card and Retry; it now ends neutrally without an audit retry.
  A later native-permission screenshot exposed a second false tool failure; its recorded call now
  remains declined even when a late protocol frame says failed.
- Native approvals originally duplicated the product decision. One linked change/run surface now
  records exact argument-bound authority and applies once.
- A live model supplied `cell_index` and omitted `base`; tool-specific schemas now publish the required
  operation fields. Invalid proposals return validation failure rather than fabricating a user denial.
- Applying an agent change originally left open editor source stale. Ledger events refresh clean
  source; dirty buffers and restored drafts remain local until the user chooses.
- A no-execution constraint incorrectly exempted a requested source edit from proof. It now restricts execution while retaining the edit proof floor; printed tool syntax cannot count as an actual invocation.
- A repaired job reused the original run handle. The repair now has a composite native identity and waits for its exact history entry, preserving the original run and successful task.
- Long workspace paths obscured real mission titles; the title now uses the notebook basename while
  preserving the full request and path.
- A remembered Auto preference invalidated a Review harness run. The live harness now explicitly
  sets Review and asserts Needs approval before saving its first screenshot.
- Live iteration 08 applied and read back the exact revision, then falsely blocked descriptive
  Supported evidence. Iteration 09 finishes Ready for review after structural effect proof without
  upgrading Supported claims to Verified. Both the failed screenshots and successful rerun remain.
- Linked native approvals now keep the pending decision state in either event order while showing
  only the product change card.
- The 200-turn scenario checks history reset on conversation changes and waits for complete replay
  before taking the final mobile screenshot. Intermediate and failed iteration images remain retained.

Failed attachment harness iterations, the recovered table lifecycle and the bundled log refusal are recorded explicitly in [16](16-gap-assessment.md).

Capture manifests are in [e2e](e2e). The inspection inventory records screenshot hashes so later image
replacement does not silently inherit an earlier inspection.

## Reproduce

```bash
make -C apps/coding-agent check
npm --prefix apps/coding-agent/web run build
ITERATION=review npm --prefix apps/coding-agent/web run e2e:agent
ITERATION=work-review npm --prefix apps/coding-agent/web run e2e:agent-work
ITERATION=assets-review npm --prefix apps/coding-agent/web run e2e:agent-assets
ITERATION=questions-review npm --prefix apps/coding-agent/web run e2e:agent-questions
ITERATION=editor-review npm --prefix apps/coding-agent/web run e2e:agent-editor
ITERATION=scale-review npm --prefix apps/coding-agent/web run e2e:agent-scale
# Point only at a disposable local PostgreSQL database:
AGENT_E2E_PG_DSN="$TEST_AGENT_PG_DSN" ITERATION=pg-review \
  npm --prefix apps/coding-agent/web run e2e:agent-operations
# Identity-verified real local app, user token and enabled phase flags required:
APP_URL=http://127.0.0.1:8071 ITERATION=live-review \
  npm --prefix apps/coding-agent/web run e2e:agent-live-edit
# Native SELECT-only acknowledgement-loss fault injection, verified user CLI profile required:
EXAM_DATABRICKS_PROFILE=opengenie-dev \
  apps/coding-agent/.venv/bin/python apps/coding-agent/scripts/agent-sql-recovery-e2e.py
python3 exams/run_exam.py --via app --app-url http://127.0.0.1:8071 \
  --missions M9 --model databricks/databricks-gpt-oss-120b --batch agent014
```

Build before browser tests; do not replace `web/dist` while tests are serving it. No broad live release,
full two-model app exam, or new production deployment is claimed by these local and fixture checks.


Latest reassessment: [17 · First-principles gap closure](17-first-principles-closure.md) supersedes the
earlier log-authentication diagnosis and records additional protocol, liveness and benchmark fixes.
