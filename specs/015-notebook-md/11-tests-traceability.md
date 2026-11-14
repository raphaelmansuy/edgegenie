# 11 — Test strategy, E2E scenarios and traceability

[Index](README.md) · Requirements: [03](03-requirements.md#requirements)
· Risks: [09](09-edge-cases.md#register) · Phases: [10](10-implementation-plan.md#phases)
· Release: [12](12-decisions-rollout.md#release-and-rollback)

## Test groups

All groups below are **planned**, not executed results. Tests assert user/source invariants and
observable outcomes; avoid tests that merely duplicate the same formatting/parser implementation.
Existing regression tests remain required. Specifications have their own [validation record](VALIDATION.md).

| Group | Test layer and meaningful assertion | Requirements | Phase |
|---|---|---|---|
| T01 | Component + E2E: nonediting cells are styled, empty cells are not editors, read-only renders, selection does not edit | MD-01, MD-02, MD-03, MD-13, MD-14 | P2, P3 |
| T02 | Pure formatting + real editor: selection offsets, single Undo, last character flush, toolbar focus and IME | MD-02, MD-03, MD-11, MD-14 | P3 |
| T03 | DOM + visual: six visual heading levels and semantic context, body/list spacing, theme contrast | MD-01, MD-04, MD-13, MD-18 | P2, P6 |
| T04 | Parser + DOM golden corpus: nesting, ordered starts, task state, quotes, breaks, tables/escaped pipes/alignment | MD-05, MD-07 | P2 |
| T05 | Math/renderer: money/code exclusions, valid MathML, invalid/huge TeX and forged marker fallback without crash | MD-06, MD-10, MD-18 | P2 |
| T06 | URL policy + browser: scheme normalization, relative/fragment navigation, unsafe HTML/URL inert, link click never edits | MD-03, MD-08, MD-10 | P2, P3 |
| T07 | Media component + HTTP fixture: placeholder/alt first, explicit load, 401/403/missing/offline/limits, no tracker request on render | MD-09, MD-15, MD-18 | P2, P5 |
| T08 | DOM + browser: exact fenced-code Copy, table/code local scroll, clipboard refusal, no SQL/run request | MD-06, MD-07, MD-18 | P2, P6 |
| T09 | Keyboard + manual AT: command/edit chords, toolbar entry/arrows/exit, dialog focus, announcements, heading/math reading | MD-03, MD-11, MD-18 | P3, P6 |
| T10 | Client/server save integration: source snapshot, semantic round-trip, one save, typing while saving, conflict/denial/reload outcomes | MD-02, MD-12, MD-14 | P1, P3 |
| T11 | Agent-update integration: clean adoption vs dirty preservation; correct cell render revision; no focus/scroll stealing | MD-12, MD-14, MD-16 | P3, P6 |
| T12 | Async lifecycle/state model + browser: reorder/convert/delete/collapse/tab switches; stale result rejection; listener/cache disposal | MD-01, MD-12, MD-14, MD-15 | P3, P4, P5 |
| T13 | Cross-surface regressions: chat streaming prefixes, file preview, read-only notebook; no CSS or parser-policy drift | MD-05, MD-06, MD-13 | P2, P6 |
| T14 | TS/Python golden + API tests: byte/code-point/cell caps ±1, completeness propagation, original metadata, permission revocation | MD-02, MD-12, MD-14, MD-17 | P1 |
| T15 | Security/network assertions: active HTML/URLs/agent text inert, caller identity enforced, caches isolated, no alternate principal | MD-08, MD-09, MD-10, MD-16 | P1, P2, P5 |
| T16 | Outline/anchor model + E2E: duplicate labels, Unicode, reorders and obsolete targets map to current cell | MD-04, MD-14 | P5 |
| T17 | Production-build instrumentation: scaling, node/depth/cache limits, one metadata pass, unchanged parse counts, media bounds | MD-09, MD-15 | P4, P5, P6 |
| T18 | Responsive/visual/print: narrow content, 200% zoom, reduced motion, two themes, no print writes/network | MD-01, MD-07, MD-18 | P6 |
| T19 | Generated parser/event inputs: every prefix, malformed Unicode/PUA/fences, deep nesting, mixed events; always progress or bounded fallback | MD-02, MD-05, MD-06, MD-10, MD-15, MD-17 | P2, P4, P6 |
| T20 | Release smoke + manual review: default styled reading and labeled controls survive served build and flag rollback | MD-01, MD-13, MD-18 | P6 |

The authoritative edge-to-test mapping is [09](09-edge-cases.md#register); do not maintain a second
handwritten list of risk IDs here. The package [validate.py](validate.py) checks that every risk and
requirement points to defined test IDs. This checks documentation coverage, not product behavior.

## E2E scenarios

Build a new `web/scripts/notebook-markdown-e2e.mjs` against a production frontend build and local
fake-agent server. Reuse the safe environment isolation in
[mission-test-server.mjs](../../apps/coding-agent/web/scripts/mission-test-server.mjs).
Use notebook route fixture patterns from
[notebook-e2e.mjs](../../apps/coding-agent/web/scripts/notebook-e2e.mjs), inspected lines 1–115;
do not copy its older broad environment inheritance into the new runner.

| Scenario | User journey and assertions | Groups |
|---|---|---|
| SC01 | Open Bakehouse notebook; title/prose are styled; code unchanged; source syntax absent from ordinary prose; zero writes/runs | T01, T03, T08 |
| SC02 | Edit, type final character, click Bold/Undo, Show preview, return to Edit; exact source/selection/history retained | T02, T09, T10 |
| SC03 | Empty/new/read-only/collapsed cells; Edit only when permitted; Expand returns styled content | T01, T12, T14 |
| SC04 | Rich syntax fixture: six headings, nested lists, quotes, aligned/escaped table, fences and math; safe Copy | T03, T04, T05, T08 |
| SC05 | Select prose, activate link by keyboard/pointer, cancel link dialog, use toolbar by arrows; no accidental mode/run transition | T02, T06, T09 |
| SC06 | Rapid preview/theme/tab/collapse/reorder/delete with held parser/media promises; obsolete completion changes nothing | T12, T17 |
| SC07 | Save twice while first response held, type while saving; then version conflict, permission denial and reload failure | T10, T14 |
| SC08 | Agent writes to clean document, then to dirty document; latest content renders only after existing reconciliation/decision | T11, T15 |
| SC09 | P0 image placeholder makes zero requests; P1 explicit load tests good/denied/missing/oversized/offline and identity switch | T07, T12, T15 |
| SC10 | Malicious HTML/URLs/PUA/TeX and malformed prefixes; no page errors, script/tool/SQL requests, unexpected popups or uncaught promises | T05, T06, T15, T19 |
| SC11 | 399/400/401-cell and exact byte/character fixtures; partial source is styled where possible and visibly read-only; Save cannot lose tail | T14, T17 |
| SC12 | Outline duplicate/changed heading navigation, narrow rails/dock, zoom, dark/reduced motion and print; anchors/focus stay correct | T03, T09, T16, T18 |

For P0, SC09 asserts placeholders only and SC12 excludes the disabled P1 outline actions. Record
those as capability-specific not-enabled cases, not failed product tests or silent skips.

## Fixture and request discipline

- Build fixtures from source strings; preserve their exact expected cell-source values independently
  of the parser under test. One golden JSON corpus is consumed by TS/Python round-trip tests.
- Fixture responses include explicit document version and completeness reasons; hold/release save,
  external-update and media responses to test both race orders. Assert no dirty/source change on Preview.
- Route known local APIs only; fail on unexpected requests. In read/preview scenarios, forbid message,
  notebook run, SQL, tool, save and external image calls. Allow only initial document/auth fixture reads
  and necessary static assets. Never allow an exception merely because the UI “looks right.”
- Use synthetic identity, paths and data. Do not execute screenshot SQL or real business queries.
  A deployed read-only smoke may inspect the served bundle/UI. A write/export smoke requires an
  explicitly designated disposable scratch notebook and existing permissions; permission denial stops it.
- Clipboard denial has a fixture; do not suppress browser errors globally. Capture `pageerror`,
  console errors, failed expectations and request logs with secrets/source contents redacted.

## Matrix and evidence

Run core DOM/parser/state suites across all configured surface adapters. Browser matrix:

| Axis | Required coverage |
|---|---|
| Engine | Chromium and WebKit for core reading/edit/toolbar/source-save flows; Firefox smoke when supported by CI |
| Layout | 1440px full shell; 860px split surface; 390px viewport; explicit 320px notebook content container |
| Appearance | Light and dark; reduced motion; 200% zoom/reflow; print media |
| Access | Writable, read-only and permission-revoked-during-edit |
| Content | Screenshot-derived synthetic title/prose; rich grammar; malformed/unsafe; exact limits; 400-cell workload |
| Observation | Fast and held responses; offline/reconnect; lazy module failure; navigation before completion |

Use pairwise combinations for the large matrix plus full combinations for high-risk boundaries:
read-only × empty/nonempty × narrow/dark; IME × preview/save; stale completion × delete/navigation;
truncation × save; agent update × dirty source. Manual checks include screen-reader heading/MathML
reading, toolbar navigation, touch targets and focus after dialog dismissal.

Evidence during implementation: `e2e/report.json`, `screenshots/`, request/error logs, performance
samples/counters and reviewed visual differences. Report tested commit, browser/device, counts of
pass/fail/not-enabled and links to requirements. Assert behavior before taking screenshots. Do not
publish screenshots as proof of round-trip safety, security, or timing bounds.

Proposed commands after implementation: `npm test`, `npm run build`, `make check`, and
`node scripts/notebook-markdown-e2e.mjs`; add a named package script when that runner exists.
Run the existing notebook/editor/agent suites appropriate to the changed boundaries. The spec-only
change does not claim these future commands have passed.

