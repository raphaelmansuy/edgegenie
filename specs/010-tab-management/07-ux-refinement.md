# Application UX refinement

Follow-up to the [requirements](01-requirements.md), [interaction design](02-interaction-design.md) and [validation](06-validation.md). The assessment found a mobile Save obstruction, cramped editing width, inconsistent Ask-menu keyboard behavior, lost open tabs after reload, oversized mobile composition and competing Home actions. This pass improves the surrounding application and preserves the tab work.

## Principles and acceptance

- UX-01: primary actions remain visible and pass pointer hit testing at 320, 375, 390 and 760px; panel handles cannot intercept Save.
- UX-02: Context starts closed. Explicitly opening Context or Navigator makes the other yield when all panes would leave less than 640px for the editor. Pane intent, grid tracks and toggle states stay in agreement.
- UX-03: Ask, Document actions, Layout and Theme share one portal-based ActionMenu with initial focus, arrows, Home/End, typeahead, Escape, Tab dismissal and invoking-control focus return.
- UX-04: restore ordered open-document metadata, active selection and bounded closed history after reload, scoped by authenticated user/workspace/origin in sessionStorage. URL selection wins. Corrupt, blocked or full storage never breaks editing. No content, credentials or grants are stored here.
- UX-05: the document composer uses a compact layout on narrow screens, retains attachment/upload/error states and keyboard sending, and allows the editor more height.
- UX-06: document identity and Save have priority; secondary actions move into a menu. Critical feedback remains visible outside the constrained bar. Pending save review uses neutral, explanatory text. Compute targets do not imply a verified connection before a run.
- UX-07: Home presents Open a document, Create a notebook and Ask the assistant. Existing advanced workflows/settings remain available through progressive disclosure. Avoid duplicate introductory suggestions and persistent theme-selection chrome.

## Implementation and verification

[ActionMenu](../../apps/coding-agent/web/src/components/ActionMenu.tsx) owns menu interaction; [workingset](../../apps/coding-agent/web/src/domain/workingset.ts) owns metadata serialization; App owns identity, route precedence, pane intent and document selection. Existing server save fences remain authoritative. There is no backend schema migration or new runtime dependency.

The [browser suite](../../apps/coding-agent/web/scripts/ui-refinement-e2e.mjs) shares [API fixtures](../../apps/coding-agent/web/scripts/ui-fixtures.mjs) with tab tests. It verifies actual pointer delivery to Save, menu focus, pane width, metadata restoration, responsive layouts and clear error feedback. The [test plan](05-test-matrix.md) and [original implementation plan](04-implementation-plan.md) remain applicable to the tab interactions.

[Visual evidence](08-ux-refinement-evidence.md) records preserved before screens, each saved iteration, inspection findings, changes and final checks. “Best UX” is treated as a quality objective, not an unverified market ranking.

## 5 WHY applied to the whole screen

1. Why improve the surrounding application? Good tabs cannot compensate for an obstructed Save action.
2. Why was Save obstructed? Competing panels and floating handles consumed the editor's finite space.
3. Why did work feel crowded? Primary actions, secondary actions and introductory suggestions competed at equal priority.
4. Why did navigation feel unreliable? Menu focus and reload recovery did not match the continuity users expect from an editor.
5. Why this implementation? Preserve the working context, reserve space for the task, and share interaction behavior so every screen follows the same rules.

First principles: width, height and attention are finite; document content, identity and position are separate concerns. A visible control must receive input. An unverified connection must not look verified. Recovery metadata must not confer authority. These principles extend the [original rationale](README.md).

## Professional review decisions

| Lens | Implemented decision | Verification |
|---|---|---|
| Product owner | Three explicit Home tasks; retain advanced workflows; reliable Save and reload continuity | UX-01/04/07 |
| Full stack developer | App coordinates identity/route, menus depend on callbacks, editor compartments update in place | UX-02/03/04; same editor node and text across theme changes |
| Database expert | Versioned metadata only; canonical references; 100 open/20 closed limit; origin/workspace/account namespace | Storage tests; no schema or permission bypass |
| UX designer | Latest panel request wins when crowded; keyboard focus follows the menu; explicit draft recovery remains | UX-02/03; TM-09 regression |
| UI designer | Primary Save, quiet review/compute indicators, consistent menus and light/dark surfaces | All saved screens inspected |
| Frontend designer | Container-driven toolbar priority, compact responsive composer, viewport-clamped portals | 320/375/390/760px fit and hit tests |
| Marketing and growth | Clear Open/Create/Ask entry points; descriptive copy; no fabricated conversion or competitor claims | UX-07, visual review |

## Implemented plan and edge cases

1. Move secondary document actions into the shared menu; keep Save and errors outside clipping/overlap regions.
2. Start Context closed for new layouts; honor saved preferences; coordinate explicit panel choices using current available width. Existing grid math remains the authority.
3. Add the shared ActionMenu keyboard/portal contract, then replace Ask, Layout and Theme behavior with it. One behavior owner prevents divergent fixes.
4. Isolate versioned metadata serialization; hydrate only after authenticated identity is known; guard initial writes until recovery finishes. Merge the initial routed document without duplication. Explicit URLs outrank saved selection; account changes clear the prior in-memory working context.
5. Compact Home/document composition on narrow screens, preserve explicit attachment and error rows, and prioritize three primary Home actions.
6. Capture each target state, inspect the full screen, fix observed defects, recapture and rerun affected checks. Run the tab suite, full frontend tests/build and specification checks after the final UI pass.

| Edge case | Mitigation and executed check |
|---|---|
| Save under floating handle | Hide mobile handles; real center-point hit test and fixture-backed Save tap at four widths |
| Long title and narrow toolbar | Reserve Save/Ask/menu; truncate identity last; full reference available through tab tooltip/picker |
| Error competes with controls | Separate wrapping alert below the bar; 375px dark error screenshot |
| Disabled menu actions / reverse entry | Skip disabled items; ArrowUp enters last; unit tests cover arrows, typeahead, Escape and dismissal |
| Popup near viewport edge | Clamp to viewport, own scroll area and popover layer; geometry and occlusion assertions on every capture |
| Many panes / explicit panel request | Close the competing side panel if necessary; assert editor width and visible toggle state |
| Corrupt/incompatible/blocked/full storage | Validate version and references; canonical dedupe; storage exceptions become empty recovery/no-op writes; unit tests |
| Reordered set / closed history / pasted URL | Browser reload and reopen assertions retain order; pasted reference becomes active and joins saved set |
| Different workspace/account | Separate storage namespace; unit tests prove isolation; App discards previous account working metadata |
| Large working set | Store at most 100 open references and 20 closed entries; unit tests. Beyond 100, reload restores the first 100; this is an explicit bound |
| Live theme switch | Reconfigure editor compartments without remount; assert same node, same text and matching surface color |
| Unknown compute / pending save review | Neutral indicator until connected; authoritative fence reason remains available; browser style assertion and visual review |
| Small/short Home viewport | All three primary actions fully in view at tested sizes; advanced content scrolls in Home; compact composer |

DRY/SOLID: shared menus and API fixtures replace duplicated interaction code; pure recovery serialization remains independent from routing and editor buffers. Existing tab move/close operations, theme tokens, editor compartments, layout math and server save fences are reused. New behavior introduces no runtime dependency or backend API.
