# Long-running session evidence

[Specification](../README.md) · [UX](../05-ux-ui.md) · [edge-case matrix](../07-edge-cases-tests.md) · [operations and live limits](../08-operations.md).

Reproduce from `apps/coding-agent/web` with `npm run build && npm run e2e:long-running`, or `make -C apps/coding-agent long-running` from the repository root. The script launches an isolated local FastAPI server, uses the real ACP stdio adapter with deterministic fixtures, writes to an actual SQLite journal, runs Chromium, closes all viewers, disconnects/reconnects the browser, restarts the application, and restores its recorded agent conversation. It does not mock HTTP responses or execute live Databricks mutations.

The machine-readable [report](report.json) identifies the run and captured states. Every screenshot is in [screenshots](screenshots/). Final visual inspection and gate results are recorded below after the completed run.

## Iteration record

The first browser pass exposed two permission controls for the same action: an inline card and the older modal sheet. The screenshot was visually inspected, and the application was changed to use one inline decision component in the dock and full conversation. The session permission option was corrected to match the agent-offered `allow_always` option. The suite is rerun against the rebuilt application after that correction.

## Validation scope

These are real local lifecycle journeys with a scripted agent; they prove browser/server/journal wiring and visual behavior, not live model correctness or Databricks authorization. Real Lakebase IAM, Databricks App host replacement, durable OpenCode native storage, and Unity Catalog checks require the environment described in [the rollout runbook](../08-operations.md#validation-boundaries).

## Final visual inspection

All 13 final screenshots were individually opened and inspected. The [inspection manifest](visual-inspection.json) records each image's SHA-256 and review finding, so a later recapture cannot silently inherit this review.

| Screenshot | Final review |
|---|---|
| [01-server-running-light.png](screenshots/01-server-running-light.png) | Server execution, copied return link, readable persistent status and matching running history. |
| [02-offline.png](screenshots/02-offline.png) | Offline observation copy and disabled mutation controls; saved context stays readable. |
| [03-reconnected.png](screenshots/03-reconnected.png) | Same turn resumes observation with its plan and no duplicate message. |
| [04-return-after-page-close.png](screenshots/04-return-after-page-close.png) | Fresh viewer shows completed plan, full answer and ready-for-review status. |
| [05-queued-work.png](screenshots/05-queued-work.png) | Two distinct prompts and explicit queue count; no interleaving. |
| [06-stopped-queue.png](screenshots/06-stopped-queue.png) | Both prompts stopped; history immediately agrees with the status card. |
| [07-waiting-for-approval.png](screenshots/07-waiting-for-approval.png) | One inline decision card, offered scope and waiting status; no modal overlay. |
| [08-return-and-approve.png](screenshots/08-return-and-approve.png) | Recorded decision resolves the waiting state; full answer visible. |
| [09-server-restarted.png](screenshots/09-server-restarted.png) | Restore action and disabled composer; partial plan preserved and uncertainty explained. |
| [10-agent-restored.png](screenshots/10-agent-restored.png) | Restore action clears; composer enabled; interrupted prompt is not replayed and has no blind Retry action. |
| [11-wide-dark.png](screenshots/11-wide-dark.png) | Full replayed answer and semantic dark-theme status; no clipped controls. |
| [12-narrow-light.png](screenshots/12-narrow-light.png) | Conversation uses the available width; inspector yields and return link stays visible. |
| [13-mobile-dark.png](screenshots/13-mobile-dark.png) | 390px conversation, compact two-row toolbar, readable status and return link; inspector stays closed. |

Observed issues were corrected iteratively: duplicate approval modal; incorrect session permission option; a default inspector obscuring mobile return controls; a grid column wider than the phone viewport; delayed active-session status in history; an unsupported assurance about external changes after interruption; an unsafe blind Retry shortcut on interrupted work; and screenshots captured before history finished replaying. The phone toolbar now uses two rows, and the replay assertion waits for the answer itself.

## Final local release gates

| Gate | Result |
|---|---|
| Backend regression, with isolated Postgres databases | 628 passed, 1 live Lakebase test skipped |
| Frontend regression | 553 tests passed across 50 files |
| TypeScript and production Vite build | Passed; existing large-bundle advisory remains |
| SQLite/Postgres journal lifecycle | Actual commit, restart and exclusive owner tests passed |
| Browser lifecycle suite | 9 journey groups passed, 13 screenshots, zero browser runtime errors |
| Document references | 9 top-level documents, 80 internal links checked |
| Mermaid parsing | 4 diagrams parsed successfully |
| ASCII wireframes | 3 generated fixed-width grids checked for aligned rows |
| Focused Python unused-code check and git whitespace check | Passed |

The backend run emitted dependency deprecation and subprocess cleanup warnings in the existing test harness. No failing assertion remains. No deployment or live Databricks/Lakebase smoke test was performed.

Backend command: `TEST_SESSION_PG_DSN=<isolated-journal-db> TEST_PG_DSN=<isolated-migration-db> apps/coding-agent/.venv/bin/python -m pytest -c apps/coding-agent/pyproject.toml apps/coding-agent/tests -q -n 4`. Both databases were created solely for this run. The generic live Lakebase integration test remains opt-in and was skipped because no live endpoint was supplied.
