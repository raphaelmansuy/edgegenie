# Acceptance and edge-case matrix

Contract: [01](01-requirements.md). Expected UI: [02](02-interaction-design.md). Implementation: [04](04-implementation-plan.md). Results: [06](06-validation.md).

| Case | Requirements | Mitigation / automated assertion |
|---|---|---|
| No documents / one document / last close | TM-07/08 | No empty strip; final close returns labelled Home surface; focus remains usable |
| Many long labels, duplicate basename, special Unicode IDs | TM-01/06/08 | Stable widths, truncation, directory suffix, full reference in picker; collision-free ID tests |
| Wheel in both axes and shift-wheel; zoom modifier | TM-02 | Strip moves without body scrolling or changing selection; ctrl/meta-wheel not intercepted |
| Open/activate hidden first/last, shrink and expand pane | TM-03/10 | Container reveals selection; controls update on scroll and ResizeObserver |
| Drag left/right, first/last and same slot | TM-04 | Pure permutation, no duplicate IDs; marker and committed order; no-op identity preserved |
| Hold at overflow edge | TM-04 | rAF keeps scrolling with stationary pointer; current geometry determines destination |
| Escape, pointercancel, outside drop, lost capture, removed source | TM-04/10 | No commit; no stuck drag class or frame |
| Click close vs drag threshold | TM-04/07 | Close button never initiates reorder; subthreshold motion remains click |
| Touch swipe vs hold; pen | TM-02/04/05 | Swipe scrolls; hold activates reorder; menu tap alternative; same pointer lifecycle |
| Move via keyboard/menu at boundaries | TM-05/08 | Disabled edge actions, same move function; live announcement and focus |
| Picker search name/path/empty/no matches | TM-06 | Keyboard-select result updates route and binding; dismiss returns focus; scrollable results |
| Active/inactive/middle/shortcut/bulk close | TM-07 | Right then left neighbor; close inactive preserves active; drafts retained; no workspace delete |
| Reopen repeated and already-open IDs | TM-07 | Former position, capped history, canonical dedupe; shortcut registry entry |
| Reorder dirty file/notebook | TM-09 | Same viewer node, exact editor text, no save/mutation request |
| Type then close before 150ms | TM-09 | Cleanup flush persists latest bytes; reopen offers recovery |
| Light/dark, narrow 390px, landscape 760px, reduced motion | TM-01/10 | Screenshots and geometry checks; no document-wide overflow; controls visible |
| Browser errors / denied document read | TM-10 | No uncaught errors; error-state tab still movable/closable |

The application-level cases UX-01–07, including mobile Save hit delivery, panel space, menu focus, reload recovery, compact composition, Home entry points and live theme changes, are specified in [07](07-ux-refinement.md) and mapped to executed checks in [08](08-ux-refinement-evidence.md).

Tests use deterministic API fixtures at the browser boundary, preserving real App routing, React handlers, CodeMirror and layout. They do not establish live Databricks identity, real workspace persistence, NVDA/VoiceOver speech quality or native OS touch-device fidelity. Screenshots and a per-image visual review are required in [06](06-validation.md).
