# Edge cases, mitigation and tests

Contracts: [product](01-product.md). Behavior: [UX/UI](03-ux-ui.md). Mechanism: [architecture](04-architecture.md). Results: [validation](07-validation.md), [browser artifacts](e2e/README.md).

| ID | Edge case / risk | Mitigation | Verification |
|---|---|---|---|
| T-01 | Active turn followed by queued work | Foreground running/auditing wins; queue count stays separate | Unit + real server E2E M-02 |
| T-02 | No running turn / empty session | Latest terminal or first queued; useful starting view | Unit/component + fixture browser M-01 |
| T-03 | Historical selection during new events | Pin explicit selection; current shortcut clears pin | Component + fixture browser M-03 |
| T-04 | Last completed lacks evidence | Ready for review; last completed available, no achieved label | Unit + real server E2E M-04 |
| T-05 | Verified boolean references absent/failed/different tool | Source matching required; warning and source details | Unit/component + fixture browser M-04/06 |
| T-06 | Plan absent, empty, unknown status, unfinished at completion | Honest absence/count; unknown neutral; never auto-complete | Unit/component + fixture browser M-05 |
| T-07 | Earlier failed call then successful recovery | Surface failed-call count even if evidence proves requirements | Unit + fixture browser M-04/06 |
| T-08 | Offline or reconnect while agent runs | Updates paused + last-known state; shared controls disabled | Unit + real server offline/reconnect E2E M-08 |
| T-09 | Approval waits while viewer leaves | Existing inline decisions, no auto-approval; history never inherits approval | Unit + real server permission E2E M-08 |
| T-10 | Server restart / interrupted work | Existing explicit restore, saved progress and disabled input | Unit + real server restart E2E M-08 |
| T-11 | Cancel queued/active work; stop API failure | Shared RunStatus action errors visible; no speculative state changes | Real server stop + component error feedback M-08 |
| T-12 | Archived session | Read-only mission; composer disabled; no lifecycle mutations | Unit + fixture browser M-08 |
| T-13 | Output reused across missions | Run artifactsOf on selected turn only | Unit + real server open/return navigation M-06/09 |
| T-14 | Generated file steals overview | Explicit Open result; existing write refresh preserved | Real server output scenario + browser navigation M-09 |
| T-15 | Long multiline request, paths, unicode, huge answer | Wrapped text, full request disclosure, bounded Markdown/plain fallback | Component + narrow browser screenshots M-07/10 |
| T-16 | Keyboard-only navigation / focus loss | Native picker, ARIA tabs with roving focus, native details, focus ring | Component + browser keyboard assertions M-07/10 |
| T-17 | Theme contrast, 320px, tablet, narrow centre, 1920px | Existing tokens, container query layout, internal scroll | Browser geometry + contrast + per-image visual inspection M-10 |
| T-18 | SSE replay duplicate/out-of-order metadata | Existing cursor dedup; no second stream; session-keyed screen | Stream regression tests for late metadata preserving plan/duration/blockers/audit, plus reload/reconnect E2E M-11 |
| T-19 | Action needs permission or connected service | Respect server failure; no workspace workaround | Existing API boundary tests; local fixtures only M-08/11 |
| T-20 | No exact stored duration/model | Omit duration; use recorded turn model, honest model fallback | Unit/component M-04/10 |

The finite test matrix covers identified failure classes, not all possible future model behavior or browser implementations. Fixture screenshots prove presentation; real local ACP tests prove actual app wiring. Neither proves a live Databricks write, live LLM quality, production Lakebase availability or user-study satisfaction. No third attempt after the same tool fails twice; report blockers directly.
