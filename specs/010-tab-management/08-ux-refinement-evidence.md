# UX refinement evidence

Implemented and reviewed on 9 November 2026. The final frontend run passed **571 tests across 54 files** and the TypeScript/production build. Browser verification passed **7 application UX groups plus 18 tab groups** in Chromium and WebKit. Two saved visual iterations contain **25 screenshots each**; all 50 were opened and visually inspected. The refreshed **22 tab regression screenshots** were also individually inspected. Three preserved before screens support the assessment.

Traceability: [acceptance and implementation](07-ux-refinement.md), [tab validation and 22-image review](06-validation.md), [edge-case matrix](05-test-matrix.md), [architecture](03-architecture.md), [reading map](README.md).

## Before and after

The assessment screens are [Home](e2e/screenshots/ui-refinement/before/home.png), [desktop](e2e/screenshots/ui-refinement/before/desktop.png) and [mobile](e2e/screenshots/ui-refinement/before/mobile.png). Each was visually reviewed. The assessment found mobile Save interception at 375/390px, a 481px main pane at 1480px with four panels, menu focus staying on its trigger, six tabs becoming one after reload, and a mobile composer around 201px high.

The final browser checks establish:

- Save receives real pointer taps at 320, 375, 390 and 760px; each successful request reaches a local fixture and retains edited text.
- At 1480px the default main pane exceeds 800px. Opening Context yields Navigator and retains more than 700px. Saved user layout preferences remain honored.
- The narrow composer is under 125px at all four tested widths; all three primary Home tasks are fully visible.
- Ordered documents, active route and closed history survive reload; a pasted document URL takes precedence.
- Ask, document, layout and theme menus use consistent keyboard/focus behavior. Live theme changes preserve the editor node/text and update its background.
- Every captured state has no document-wide horizontal overflow, body scroll, clipped popup or popup hit-test obstruction. Error feedback remains visible.

## Inspection-driven iterations

Iteration 1 was captured and inspected before accepting the UI. It exposed clipped Home actions on narrow/short screens, truncated advanced descriptions, competing hover/focus emphasis, and a light CodeMirror surface inside the newly dark shell. Iteration 2 corrected the layout density, description wrapping, hover styling and editor theme compartments. The document menu also gained the actual review reason so compact status icons remain understandable. The complete second set was recaptured and visually inspected; no further blocking visual defect was observed in these states.

Every link below points to a retained PNG. Review covered the complete screen, spacing, typography, hierarchy, label fit, theme, overlays, feedback and interaction targets. Partial inactive tabs and truncated long names are deliberate; the tab picker exposes full references. These are manual visual reviews supported by geometry/focus assertions, not pixel-diff baselines.

| Screen | First capture | Final capture | Inspection result |
|---|---|---|---|
| 01-home-desktop | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/01-home-desktop.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/01-home-desktop.png) | Three primary tasks; quiet assistant introduction; useful editor width. |
| 02-home-workflows | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/02-home-workflows.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/02-home-workflows.png) | Iteration 1 truncated descriptions; iteration 2 wraps descriptions and retains every advanced workflow. |
| 03-desktop-editor | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/03-desktop-editor.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/03-desktop-editor.png) | Readable notebook identity, primary Save, neutral review/compute status; no forced four-pane squeeze. |
| 04-context-on-demand | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/04-context-on-demand.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/04-context-on-demand.png) | Context opens as requested; Navigator yields; document retains useful space. |
| 05-ask-keyboard | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/05-ask-keyboard.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/05-ask-keyboard.png) | Visible focused action; full menu fits and does not cover its trigger. |
| 06-document-actions | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/06-document-actions.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/06-document-actions.png) | Secondary actions grouped; full review explanation available; keyboard focus distinct from pointer hover. |
| 07-layout-menu | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/07-layout-menu.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/07-layout-menu.png) | Panel checkmarks and focus/reset actions readable and reachable. |
| 08-focus-editor | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/08-focus-editor.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/08-focus-editor.png) | Editor becomes the primary surface; panel controls remain available. |
| 09-theme-menu | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/09-theme-menu.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/09-theme-menu.png) | System/Light/Dark explicit selection; compact trigger replaces permanent segmented chrome. |
| 10-desktop-dark | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/10-desktop-dark.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/10-desktop-dark.png) | Iteration 1 exposed a white CodeMirror surface after theme change; iteration 2 updates editor in place with consistent dark colors. |
| 11-working-set-restored | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/11-working-set-restored.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/11-working-set-restored.png) | Ordered open documents and active selection visible after reload; selected tab revealed. |
| 12-mobile-390-home | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/12-mobile-390-home.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/12-mobile-390-home.png) | Iteration 1 clipped primary actions; iteration 2 shows all three above compact composer. |
| 12-mobile-390-editor | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/12-mobile-390-editor.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/12-mobile-390-editor.png) | Filename, Save and menu visible; compact composer leaves editing space. |
| 12-mobile-390-actions | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/12-mobile-390-actions.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/12-mobile-390-actions.png) | Menu bounded in viewport; review reason and all four actions readable. |
| 13-mobile-375-dark-home | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/13-mobile-375-dark-home.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/13-mobile-375-dark-home.png) | Iteration 2 reduces hero/spacing so all three primary actions fit; dark hierarchy remains clear. |
| 13-mobile-375-dark-editor | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/13-mobile-375-dark-editor.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/13-mobile-375-dark-editor.png) | Reachable primary Save; consistent dark editor; compact input and model control. |
| 13-mobile-375-dark-actions | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/13-mobile-375-dark-actions.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/13-mobile-375-dark-actions.png) | Dark menu, readable explanation and clear keyboard focus; no handle overlap. |
| 14-mobile-320-home | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/14-mobile-320-home.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/14-mobile-320-home.png) | All three primary actions visible in iteration 2 at smallest tested width; advanced content remains scrollable. |
| 14-mobile-320-editor | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/14-mobile-320-editor.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/14-mobile-320-editor.png) | Save takes priority; long identity truncates; action targets remain inside the toolbar. |
| 14-mobile-320-actions | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/14-mobile-320-actions.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/14-mobile-320-actions.png) | All menu actions fit with viewport gutters; review reason remains available despite compact toolbar. |
| 15-tablet-landscape-home | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/15-tablet-landscape-home.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/15-tablet-landscape-home.png) | Iteration 2 uses three columns; all primary tasks visible in short landscape viewport. |
| 15-tablet-landscape-editor | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/15-tablet-landscape-editor.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/15-tablet-landscape-editor.png) | Tabs, toolbar and editor fit with compact composer and a single scope note. |
| 15-tablet-landscape-actions | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/15-tablet-landscape-actions.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/15-tablet-landscape-actions.png) | Readable Save feedback; menu fully bounded above the composer. |
| 16-mobile-error-feedback | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/16-mobile-error-feedback.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/16-mobile-error-feedback.png) | Wrapping save error remains visible below the toolbar; dirty document and Save remain usable. |
| 17-webkit-mobile-menu | [Iteration 1](e2e/screenshots/ui-refinement/iteration-01/17-webkit-mobile-menu.png) | [Iteration 2](e2e/screenshots/ui-refinement/iteration-02/17-webkit-mobile-menu.png) | Settled WebKit paint shows dark Ask menu, initial focus and correct overlay layering. |

## Executed checks and traceability

| Contract | Executed evidence |
|---|---|
| UX-01 | Center-point Save hit tests and actual fixture-backed taps at four widths; no mobile floating handles |
| UX-02 | Default/explicit pane widths, Navigator/Context mutual yielding, Focus editor and Reset layout |
| UX-03 | Menu component tests: disabled skipping, reverse entry, wrap, typeahead, Escape, outside dismissal, exactly-once action. Browser: Enter, arrows, End, Escape, Tab dismissal, theme/layout actions; portal fit/occlusion on every capture |
| UX-04 | Storage unit tests: metadata only, canonical dedupe, namespace isolation, corrupt/version/invalid input, size bounds and storage exceptions. Browser: reorder/reload/active selection, close/reload/reopen, pasted URL precedence |
| UX-05 | Composer height below 125px; editor text preserved; mobile/tablet screenshots; Home actions completely in view |
| UX-06 | Real fixture Save receipt, unchanged edited text, visible failure alert, neutral compute indicator, permission explanation in menu |
| UX-07 | Exactly three Home tasks, advanced workflows still available, Ask focuses composer; responsive visual review |
| TM-01–10 | Refreshed [18-group report](e2e/report.json) and [22-image visual log](06-validation.md#visual-inspection-log) |

The [application browser suite](../../apps/coding-agent/web/scripts/ui-refinement-e2e.mjs) and [tab suite](../../apps/coding-agent/web/scripts/tabs-e2e.mjs) share [HTTP fixtures](../../apps/coding-agent/web/scripts/ui-fixtures.mjs). Reports: [iteration 1](e2e/ui-refinement-iteration-01.json), [iteration 2](e2e/ui-refinement-iteration-02.json). Final reports record zero browser runtime errors and zero unhandled API requests. The tab suite records zero mutation requests. The UX suite records four successful Save requests served entirely by its local fixture; its rejected-save fixture tests visible error feedback. No live workspace write was performed.

Run from the repository root:

```sh
npm test --prefix apps/coding-agent/web
npm run build --prefix apps/coding-agent/web
TAB_E2E_SKIP_FIREFOX=1 npm run e2e:tabs --prefix apps/coding-agent/web
UI_ITERATION=iteration-02 npm run e2e:ux --prefix apps/coding-agent/web
npm run verify:spec-tabs --prefix apps/coding-agent/web
```

Both browser scripts manage a dedicated localhost Vite server unless APP_URL is set. Matching Playwright browser binaries are required. The build retains its existing non-blocking chunk-size warning. Documentation links, four ASCII wireframes and three Mermaid diagrams are checked separately.

## Validation limits

Firefox launch failed twice as detailed in [06](06-validation.md#limits-and-remaining-manual-checks), so it was explicitly skipped. Databricks identity/warehouse tools were unavailable; live permissions, real saves and remote execution remain unverified. Screen-reader speech, physical devices, virtual keyboard behavior and extreme OS text scaling need target-device validation. This pass does not deploy the application or prove market-wide superiority. “Best UX” remains a quality objective supported here by specific improvements and reproducible checks.
