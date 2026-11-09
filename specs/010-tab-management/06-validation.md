# Validation and evidence

Implemented and locally verified on 9 November 2026. The final run has **18 passing browser acceptance groups**, **22 retained screenshots**, **571 passing frontend tests across 54 files**, a successful TypeScript/production build, four aligned ASCII wireframes and three parsed Mermaid diagrams. Firefox and live Databricks verification remain unavailable as described below.

The tab suite and all 22 screenshots were refreshed and visually reviewed after the application improvements. [08 UX evidence](08-ux-refinement-evidence.md) adds seven acceptance groups, two saved 25-screen visual iterations and current recovery behavior.

Traceability: [requirements](01-requirements.md), [matrix](05-test-matrix.md), [implementation plan](04-implementation-plan.md), [source architecture](03-architecture.md), [5 WHY](README.md).

## Executable evidence

- [Browser suite](../../apps/coding-agent/web/scripts/tabs-e2e.mjs) and its [machine-readable report](e2e/report.json): real App routing, CodeMirror, React events, native pointer capture and layout; deterministic HTTP fixtures. Full Chromium journey plus WebKit navigation/reorder/picker checks.
- [Pure order tests](../../apps/coding-agent/web/src/domain/tabs.test.ts): permutations, retained object references/revisions, invalid/stale moves, neighbor selection and collision-free DOM IDs.
- [Gesture lifecycle tests](../../apps/coding-agent/web/src/hooks/useTabDrag.test.ts): control/secondary-pointer exclusion, blur cancellation, source removal, pending touch cleanup, capture release and animation-frame cleanup.
- [Keyboard registry tests](../../apps/coding-agent/web/src/domain/keys.test.ts): portable physical Control+Tab and the existing shared shortcut contracts.
- [Wireframe checker](../../apps/coding-agent/web/scripts/verify-tab-wireframes.mjs): all four simple ASCII grids have equal row widths and aligned borders. The existing link checker validates the document graph; the real Mermaid parser accepts the sequence, ER and state diagrams.

From the repository root:

```sh
npm test --prefix apps/coding-agent/web
npm run build --prefix apps/coding-agent/web
npm run verify:spec-tabs --prefix apps/coding-agent/web
TAB_E2E_SKIP_FIREFOX=1 npm run e2e:tabs --prefix apps/coding-agent/web
```

For full browser coverage on a host where all engines launch, omit `TAB_E2E_SKIP_FIREFOX`. The suite starts/stops a dedicated localhost Vite process unless `APP_URL` is supplied. Browser fixtures intercept only `/api/` paths, never Vite's `/src/api/` modules. Matching browser binaries must be installed. Diagram parsing was also run using the repository's `verify-spec-mermaid.mjs` with `MERMAID_PATH=/tmp/mmd/node_modules/mermaid/dist/mermaid.core.mjs`; Mermaid remains a documentation-only tool and is not an app dependency.

The production build retains its non-blocking warning about chunks over 500 kB. `git diff --check` is clean. No backend schema or API contract changed.

## Requirement coverage

| Contract | Executed checks |
|---|---|
| TM-01 | Notebook/file/table identities; duplicate basenames; very long/Unicode labels; punctuation ID collisions; single-row stable widths |
| TM-02 | Vertical wheel translation, horizontal trackpad input, controls, live edge state, zoom exclusion, no body scroll; touch swipe preserves order |
| TM-03 | Hidden selection, reselecting the same active document from picker, pane shrink/expand, first/last keyboard reveal |
| TM-04 | Pointer reorder preserves active ID and exact editor node/text; edge autoscroll and visible boundary marker; threshold, Escape, outside drop, pointercancel, source removal; pen and touch |
| TM-05 | Keyboard, right-click/Shift+F10 and visible Tab actions button; native emulated touch taps move a tab without dragging |
| TM-06 | Search by path/name, no-result state, keyboard result activation, Escape and invoking-control focus return; popup hit testing |
| TM-07 | Active/inactive/middle close; adjacent fallback; close shortcut; close others/right/all; final close Home focus; reopen at previous position; canonical path deduplication |
| TM-08 | Home/End/wrapping arrows; Control+Tab in both directions; panel labelling; disabled edge moves; no asynchronous editor focus theft |
| TM-09 | Unsaved notebook text and editor mount survive drag; immediate file close flushes draft; reopen offers explicit Restore; no implicit workspace save |
| TM-10 | Light/dark; 1480px desktop, 760px landscape/tablet, 390px mobile; reduced motion; denied document read remains movable/closable; gesture cleanup tests |

The report records **zero browser runtime errors**, **zero unhandled API fixtures** and **zero workspace mutation requests**. The read-equivalent fence-check POST is explicitly allowed; no save/delete/run request is permitted by the suite.

## Visual inspection log

Every retained PNG below was opened and visually inspected after the final capture. Review covered the complete screen and the tab strip/popup: label readability, active/focus distinction, control fit, close-button inset, drop marker, layering, spacing, theme and recovery state. Partial inactive tabs at viewport boundaries and ellipsized long names are intentional overflow behavior. These are manual visual reviews, not pixel-diff baselines or claims of market-wide superiority.

| Screenshot | Inspection result |
|---|---|
| [01 Readable tabs](e2e/screenshots/01-readable-tabs-light.png) | Pass: bounded labels, inset close control, quiet selected accent; document fully loaded |
| [02 Drag insertion](e2e/screenshots/02-drag-insertion.png) | Pass: dim source, visible insertion line, preserved dirty notebook |
| [03 Reordered editor](e2e/screenshots/03-reordered-dirty-editor.png) | Pass: moved active tab and dirty dot; notebook text stays visible |
| [04 Keyboard menu](e2e/screenshots/04-accessible-tab-actions.png) | Pass: focused action, clear separators and disabled reopen; no clipped menu rows |
| [05 Last tab overflow](e2e/screenshots/05-overflow-last-tab.png) | Pass: long/Unicode names, selected last tab, disabled right edge and hidden count |
| [06 Document picker](e2e/screenshots/06-open-document-picker.png) | Pass: 12-document count, readable paths, independent scrolling; Context handle no longer covers search/count |
| [07 Path filter](e2e/screenshots/07-picker-filtered-path.png) | Pass: duplicate filename resolved by full directory path |
| [08 No results](e2e/screenshots/08-picker-no-results.png) | Pass: clear empty state, retained query and bounded panel |
| [09 Edge drag](e2e/screenshots/09-edge-autoscroll.png) | Pass: insertion line remains visible at strip edge while source scrolls away |
| [10 Adjacent close](e2e/screenshots/10-adjacent-close-and-recovery.png) | Pass: successor notebook fully loaded; draft recovery offer remains visible |
| [11 File recovery](e2e/screenshots/11-restored-plain-file-draft.png) | Pass: restored bytes, dirty indicator and existing save action agree |
| [12 Desktop dark](e2e/screenshots/12-wide-dark.png) | Pass: active tab and disabled scroll states remain distinguishable |
| [12 Dark picker](e2e/screenshots/12-wide-dark-picker.png) | Pass: readable search/paths, visible active row, clean overlay above edge handle |
| [13 Landscape](e2e/screenshots/13-tablet-landscape.png) | Pass: selected tab and all four navigation controls fit the narrow editor |
| [13 Landscape picker](e2e/screenshots/13-tablet-landscape-picker.png) | Pass: result area scrolls; header, search and footer remain in viewport |
| [14 Mobile light](e2e/screenshots/14-mobile-light.png) | Pass: selected label/close and fixed controls remain usable at 390px |
| [14 Mobile picker](e2e/screenshots/14-mobile-light-picker.png) | Pass: viewport-clamped panel, full search input, readable path rows |
| [15 Mobile dark](e2e/screenshots/15-mobile-dark.png) | Pass: theme-consistent active tab and overflow affordances |
| [15 Mobile dark picker](e2e/screenshots/15-mobile-dark-picker.png) | Pass: active row, focus outline and all picker content remain legible |
| [16 Touch reorder](e2e/screenshots/16-touch-reorder.png) | Pass: coarse-pointer close targets and a clear insertion line |
| [16 Touch actions](e2e/screenshots/16-touch-actions.png) | Pass: visible tap-only action trigger, comfortably spaced menu rows, bounded overlay |
| [18 WebKit](e2e/screenshots/18-webkit.png) | Pass: selected/focused package tab, loaded editor, overflow controls and labels |

## Improvements driven by testing and inspection

1. Corrected the trailing-padding reveal delta so the right scroll button disables at the true edge.
2. Removed pointer interception by invisible skip links while retaining keyboard focus visibility.
3. Raised tab popovers above panel edge handles and added hit testing for the overlap region.
4. Prevented a lazily loaded file editor from stealing focus during tab keyboard navigation.
5. Added explicit same-active-document reveal, avoiding React state bailout leaving selection hidden.
6. Added a visible actions trigger so touch users can reorder with taps alone.
7. Clamped the drop marker to the strip viewport so autoscrolling cannot hide destination feedback.
8. Waited for document and CodeMirror readiness before retaining screenshots of settled states.

## Limits and remaining manual checks

- **Firefox unavailable:** the initial launch lacked the matching binary; after installing the matching Firefox 159 binary, launch failed with `Could not find profile folder`. Verification stopped after those two failures, following AGENTS.md. The final run explicitly skips and records Firefox; no Firefox screenshot is claimed.
- **Databricks unavailable:** `dbxnb_dbx_whoami` and `dbxnb_dbx_list_warehouses` were not exposed in this session. Identity and running warehouse remain unverified. UI fixtures do not establish live workspace behavior, permissions or real saves. The denied-read scenario is a fixture and triggers no workaround.
- **Human accessibility/device checks:** screen reader speech, physical touch/stylus devices, OS browser-key reservations and very large OS font settings still need manual checks on target devices. Automated keyboard/focus/ARIA and emulated pointer coverage do not replace them.
- **Persistence policy:** [07 UX refinement](07-ux-refinement.md) supersedes the initial page-lifetime-only policy with bounded, account/workspace-scoped sessionStorage metadata recovery. Draft recovery still uses the existing local-storage policy, including quota/private-mode limits and eviction. No cross-device synchronization is added.
- **Scope:** single editor group; no split groups, pin/preview semantics or OS-window tear-off. No production deployment or market-wide November 2026 comparison was performed.
