# 17 · First-principles gap closure

13 November 2026. Reassessment against the eleven principles in [00](00-five-whys-first-principles.md)
and the open gates in [16](16-gap-assessment.md). **Release qualification is still incomplete.**

## What was actually missing

The previous pass established broad feature coverage, but some projections did not preserve the
underlying facts. A nonzero CLI exit became a permission denial; compaction updates became anonymous
messages; an initial command catalogue could be dropped; an ungraded benchmark could become a model
failure. Those are implementation defects even when representative tests pass.

First principles require identity and native effects to remain authoritative, protocol values to keep
their identity and patch semantics, work and buffers to stay bounded, and scores to include only
observations that were actually graded. More retries or more test counts cannot replace those rules.

| Principle | Gap closed | Evidence |
|---|---|---|
| FP-1 identity; FP-3 observed evidence | Log errors now distinguish access refusal, interactive-auth redirect, TLS failure, native service outage, handshake failure and unknown client failure. Only fixed messages, category and HTTP status leave the adapter; no raw CLI error is exposed. Readable app metadata remains available when logs fail. | Thirteen app-log contracts; [approved native check](e2e/app-logs-principles.json) |
| FP-5 bounded work; FP-10 bounded buffers | Log stderr is drained concurrently while retaining at most 4 KiB. An oversized error cannot deadlock or leak its body. Agent stderr now drains chunks rather than requiring a newline, keeping at most 200 fragments of 4 KiB. | Large-error contract; real child emitting a 20 MB unbroken stderr line still initializes and reports a bounded useful error |
| FP-6 speak the protocol | Runtime advertises implemented notices/compaction extensions and forwards initial `availableCommands` from setup instead of waiting for a later notification that may never arrive. | Actual stdio setup contract checks advertised values and delivered command event |
| FP-6 protocol values; FP-10 bounded work | Compactions upsert by ID, preserve first-seen sequence/turn/order, append summary chunks, implement omission/null/replacement semantics, keep chunk metadata separate from entity metadata, and cap entities/content. They render as inspectable cards. Notices keep severity and detail. | Reducer contracts; [parity E2E](e2e/parity-principles-final.json) through HTTP/stdio ACP/SQLite/SSE, including replay and keyboard-expanded mobile summaries |
| FP-5 poll instead of blocking | The retained `wait_seconds` SQL option no longer disappears silently. The reply states the requested and effective wait (zero), identifies clamping, and directs polling. Wait preference does not change native operation identity. Invalid values fail before submission. | Two nonblocking-wait regressions |
| FP-11 measure the product | Setup, identity and grader exceptions now produce `valid: false`, zero denominator and no percentage. They cannot lower a model score as if a mission had been graded. Completed grader checks still determine actual model scores. | Three benchmark-validity contracts |
| FP-2 changes; FP-3 evidence | The corrected asset E2E checks attachment references that the public API actually exposes. Private resolved context stays private; owner-bound HTTP contracts separately prove its delivery. | [Fourteen-screen asset E2E](e2e/assets-principles.json) now passes after the retained failed harness attempts |

The SQL policy was not widened to accept unsupported statements merely to improve a model score.
No app service-principal execution, permission fallback or native mutation retry was introduced.

## What the live observation establishes

The user explicitly approved **one** additional read-only log check after automatic review enforced
the working agreement's two-failure stop. That check used the bundled, checksum-pinned CLI and the
same verified user, `raphael.mansuy@gmail.com`. It returned **HTTP 503 on the log connection**.
No raw logs were retained and no alternate identity was used.

A separate read-only app-status request returned:

- App: `coding-agent` in the requested workspace.
- Compute state: **STOPPED**.
- Platform message: **“App compute was stopped due to workspace or account status.”**
- Active deployment status: absent.

These observations identify an external availability dependency. They do not establish that a user
permission is missing. The app now reports `SERVICE_UNAVAILABLE` for that recorded HTTP status. It
was not started, redeployed or given new grants. See [native status](e2e/app-state-principles.json).
The earlier “bundled authentication failure” diagnosis in historical records is superseded by these
observations; successful native log ingestion on the current stopped app remains unverified.

## What remains

1. Restore the workspace/account condition and app availability before deployed log and live-app
   qualification. No further log attempt is authorized by the single-check approval.
2. Complete the original plus new product exam suite on two models and measure regression/noise.
   The original pre-change baseline was not recorded and cannot be fabricated retroactively. Existing
   Maverick M9 6/12 and gpt-oss M9 12/12 remain unchanged; no new model score is claimed here.
3. Complete real-agent timed timeout/wait, live credential rotation, long native-run recovery,
   200-turn native resume and all advertised-feature recordings. The new parity E2E uses a scripted
   protocol fixture and must not be described as a real-model conformance recording.
4. Complete the exhaustive crash/load and WCAG release matrix. The new summary region is keyboard
   scrollable; that targeted correction and inspected screenshots are not a full WCAG certification.
5. Qualify any separate execution identity through S13 before enabling it. The plan explicitly permits
   the currently implemented port/check fallback; no separate runner is silently substituted.

## Validation and inspection

The final full gate passed **891 Python tests (19 skipped), 642 frontend tests, and TypeScript**;
see [first-principles-check.log](e2e/first-principles-check.log).
The production frontend build passed. Asset E2E passed fourteen captures; parity E2E passed four final
captures, with three earlier parity captures retained. Every one of the **346 retained PNGs** was
individually opened and inspected. [The inventory](e2e/screenshot-inspections.json) records exact hashes.

The parity inspection found a scrollable summary region needing keyboard focus. It now has a focusable
region and a browser check that expands the mobile summary with Enter; its final screenshot was
inspected again. Failed/intermediate captures and earlier exam outcomes remain available.
