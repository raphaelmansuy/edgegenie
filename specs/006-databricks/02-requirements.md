# 02 · Requirements

[Index](README.md) · prev: [01 Audit](01-current-state-audit.md) · next: [03 Architecture](03-architecture.md)

Every requirement has an id, a reason, and a way to know it is met. The id prefixes are stable so
code and tests can cite them.

| Prefix | Area |
|---|---|
| `AD-` | Assistant dock (placement, focus, states) |
| `FX-` | Focus and binding |
| `MC-` | Model control |
| `FL-` | Files browser |
| `PS-` | Persistence |
| `NB-` | Notebook surface (only what the dock must touch) |
| `UX-` | Cross-cutting experience rules |

---

## Assistant dock — `AD`

| id | Requirement | Why | Acceptance |
|---|---|---|---|
| **AD-1** | With a document open, the conversation is rendered and visible at every width ≥ 820 px. | [01 N1](01-current-state-audit.md#n1-the-conversation-is-not-on-screen-when-a-document-is-open) — measured 0 turns today. | `turnsRenderedWithDocOpen ≥ 1` in `dock-audit.mjs` at 1600/1180/1024/900. |
| **AD-2** | The dock is a grid zone in `wide` mode (a real column), and an overlay drawer in `mid`/`narrow`. | [00 P2](00-why-first-principles.md#p2-two-surfaces-that-must-be-watched-together-cannot-share-a-slot) | Column present at 1600 with width in `[ASSISTANT_MIN, ASSISTANT_MAX]`; `position: fixed` + `.is-drawer` at 1024/760. |
| **AD-3** | `⌘J` toggles the dock at every width, and the key is printed in the dock header and the shortcut sheet. | [00 P3](00-why-first-principles.md#p3-below-some-width-two-at-once-is-a-lie-so-one-is-an-overlay-the-user-summons) | e2e: press `⌘J` at 1600 (column hides/shows) and at 760 (drawer opens/closes); `⌘/` lists it. |
| **AD-4** | The dock never opens by itself: not on load, not on resize, not when a document opens. | [00 P3](00-why-first-principles.md#p3-below-some-width-two-at-once-is-a-lie-so-one-is-an-overlay-the-user-summons) | e2e: resize 1600→760 with a document open; the drawer is closed. |
| **AD-5** | The dock works with **no session**: it shows suggestions and accepts a first prompt, creating a session with the current focus. | [01 N1](01-current-state-audit.md) — the inspector is suppressed until a session exists ([`App.tsx:276`](../../apps/coding-agent/web/src/App.tsx)). | e2e: fresh load, click a suggestion in the dock, a session is created and the turn streams into the dock. |
| **AD-6** | The dock header states its binding in words (`in context: <doc>`, and the cell when one is chosen). | Parity with Genie Code's `in context:` chip [observed]. | e2e: open a notebook, assert the chip text; choose a cell, assert it names the cell. |
| **AD-7** | The dock has exactly four states — `empty`, `streaming`, `asking`, `failed` — each of which names a next action. | [06 §4](06-ux-wireframes.md) | Vitest: a pure `dockState()` returns one of four for every combination of session/turn/approval/error; e2e screenshots each. |
| **AD-8** | An approval raised by a turn submitted from the dock is shown in the dock, with the same three outcomes as the sheet. | The sheet is modal and covers the code the approval is about. | e2e: trigger a write outside the folder; the dock shows the approval; "Deny" reaches `POST /api/approvals`. |
| **AD-9** | The dock can be resized by dragging its edge, with the same bounds and persistence as every other zone. | [001 SH-G3](../001-perfect-shell/README.md) | `layout.ts` gains `assistantWidth`; `columns()` includes it; reload keeps the width. |
| **AD-10** | Below 820 px the dock covers the document, and closing it returns focus to the element that opened it. | Focus must not be lost in a drawer. | e2e: `⌘J`, `Esc`, assert `document.activeElement` is the top-bar toggle. |

## Focus and binding — `FX`

| id | Requirement | Why | Acceptance |
|---|---|---|---|
| **FX-1** | `Focus` is `{ docId, cellId? }`, is a domain value, and is the only source of "what this conversation is about". | [00 P1](00-why-first-principles.md#p1-a-conversation-has-a-subject-and-the-subject-is-data) | `web/src/domain/focus.ts` with unit tests; no component infers a subject from viewport state. |
| **FX-2** | Changing the open document changes the dock's binding and does **not** clear the transcript. | AD-1. | e2e: open two documents in turn; the turn count is unchanged, the chip changes. |
| **FX-3** | Choosing a cell sets `cellId`; clearing the selection clears it. | [01 N5](01-current-state-audit.md#n5-two-controls-in-a-notebook-do-nothing) — `ask` must be real. | Vitest on `focus.ts`; e2e via the cell's `ask` button. |
| **FX-4** | A prompt sent from the dock carries the binding as attachments, exactly once each. | Duplicate context wastes tokens and confuses the model. | Unit test on `binding.ts`; the request body has one entry per binding. |
| **FX-5** | A conversation started from the dock records its binding server-side, so a reload restores it. | [PS-1](#persistence-ps). | `session_binding` row asserted via `/api/sessions/{id}`. |
| **FX-6** | The `@` picker searches the **focused root** (the folder of the open document, else the session folder, else home). | [01 E7](README.md#what-is-wrong-today-in-one-table) — today it searches home only. | `api.search(q, root)` is called with the computed root; e2e searches for a file outside home and finds it. |

## Model control — `MC`

| id | Requirement | Why | Acceptance |
|---|---|---|---|
| **MC-1** | The current model is visible at every width from 760 to 1600 px, with no shortcut required. | [01 N3](01-current-state-audit.md#n3-the-model-control-disappears-below-1100-px). | `modelChipVisible: true` at 1600/1180/1024/900/760. |
| **MC-2** | There is exactly one picker component; the top bar and the composer render it with different triggers. | [005 08 Lenses](../005-llm-models/08-lenses.md) DRY argument; two pickers already drifted once. | A single `ModelPicker` import; no second model list in the codebase. |
| **MC-3** | The composer exposes the model inline, so choosing one does not require leaving the message box. | Genie Code offers no model choice; the advantage must be *reachable*. | e2e: click the composer's model control, pick a model, the turn uses it. |
| **MC-4** | A model can be chosen **before** a session exists, and that choice becomes the new session's model. | [01 N3](01-current-state-audit.md#n3-the-model-control-disappears-below-1100-px) second cause. | e2e: new session, choose a model in the dock composer, send, assert `session.model`. |
| **MC-5** | A switch applies to the next turn only, is stated as such in the UI, and is visible per turn afterwards. | [005 FR-9/FR-10](../005-llm-models/02-requirements.md). | Existing `model-facts` test plus an e2e assertion on the chip's "from turn N" note. |
| **MC-6** | An unavailable model cannot be selected; choosing one states the remedy (add a key, ask an admin). | [005 U7](../005-llm-models/07-ux-ui-wireframes.md). | Existing picker tests; one e2e on the `add a key` affordance. |
| **MC-7** | The control names the model, not its id, and never truncates to something unrecognisable at 760 px. | Legibility at the narrowest width is the whole point of MC-1. | e2e: at 760 px the label contains a recognisable fragment; `title` carries the full id. |

## Files browser — `FL`

| id | Requirement | Why | Acceptance |
|---|---|---|---|
| **FL-1** | Files offers **tree** and **list**; the choice persists per browser. | Databricks parity [observed]: tree answers *where*, list answers *which*. | e2e: toggle, reload, the mode is remembered. |
| **FL-2** | The list shows name, type, owner and last updated, sorted by name, folders first. | Those are the four columns Databricks shows [observed]. | Sorting is a pure function with tests; e2e asserts the header. |
| **FL-3** | The pane shows a breadcrumb of the current folder and one "up" affordance. | Today the path is only in a row's `title`. | e2e: breadcrumb matches the folder. |
| **FL-4** | A list row opens on click and offers the same right-click menu as a tree row. | The menu already exists ([`WorkspaceMenu.tsx`](../../apps/coding-agent/web/src/components/WorkspaceMenu.tsx)); it must not be tree-only. | e2e: right-click a list row, the menu appears with the same items. |
| **FL-5** | Favorites and Trash are anchored at the bottom and do not move with the folder contents. | Databricks parity [observed]. | Visual assertion in the screenshot; no `Favorites` row inside the scroll region. |
| **FL-6** | Dropping files onto the pane imports them into the current folder, using the existing `/api/workspace/import`. | The action exists and has no drop target. | e2e with `DataTransfer`. |

## Persistence — `PS`

| id | Requirement | Why | Acceptance |
|---|---|---|---|
| **PS-1** | Sessions, turns, bindings and the model pin survive a process restart. | [00 P5](00-why-first-principles.md#p5-state-that-the-user-created-is-the-products-responsibility). | Kill and restart the app; `GET /api/sessions/{id}` still returns the turns. |
| **PS-2** | The event stream can be replayed from the durable store at any cursor, so a reload shows the whole conversation. | Today the cursor is written to `localStorage` but the log is in memory. | After a restart, `GET /stream?after=0` yields every event in order. |
| **PS-3** | A database that is unreachable degrades to the in-memory store, loudly, and never silently loses a turn. | A deployed app must start without Lakebase. | Config test: with no DSN, `store` is memory and `/api/ready` says so. |
| **PS-4** | Retention is explicit: sessions older than N days are pruned by a job, not by a restart. | An unbounded table in a shared Postgres is someone else's incident. | A `reaper` unit test on the age predicate; [05 §Retention](05-data-model-lakebase.md). |

## Notebook surface, only what the dock touches — `NB`

| id | Requirement | Why | Acceptance |
|---|---|---|---|
| **NB-1** | A cell exposes `ask`, which opens the dock bound to `{ doc, cell }` and focuses the composer. | [01 N5](01-current-state-audit.md#n5-two-controls-in-a-notebook-do-nothing). | e2e: click `ask` on cell 2, dock shows `cell 2`, composer focused. |
| **NB-2** | There is no run affordance until a real executor exists. | [00 P4](00-why-first-principles.md#p4-a-control-that-cannot-act-must-not-be-shown). | Grep test: no `.cell-run` in the tree; e2e asserts the button is absent. |
| **NB-3** | The `ask` action appears on hover and on keyboard focus of the cell, and is announced. | A control that only appears on hover is invisible to the keyboard. | a11y audit: the button is reachable by Tab and has an accessible name. |

## Cross-cutting — `UX`

| id | Requirement | Why | Acceptance |
|---|---|---|---|
| **UX-1** | No control in the shell is inert: every button either acts or is not rendered. | [00 P4](00-why-first-principles.md#p4-a-control-that-cannot-act-must-not-be-shown). | A `dead-controls` e2e walks every button in the three panes and asserts each is either `aria-disabled` or produces a request/DOM change/focus move. |
| **UX-2** | Chrome above the first line of code stays ≤ 150 px. | [01 N4](01-current-state-audit.md#n4-chrome-above-the-first-line-of-code-146-px) — 146 today; this must not regress. | `dock-audit.mjs` asserts it. |
| **UX-3** | The dock's toggle is present, pressed-state, and labelled at every width. | The drawer must always be recoverable. | a11y audit: `aria-pressed` and a name at 1600 and 760. |
| **UX-4** | Every state change in the dock is announced once to assistive technology. | A streaming answer must not be re-announced per token. | e2e reads the live region; vitest asserts the announce policy. |
| **UX-5** | Everything works in both themes and at 200 % zoom. | Existing rule ([001 UX-5](../001-perfect-shell/02-requirements.md)), re-asserted because the dock is new chrome. | `audit:a11y` and screenshots in both themes. |

---

## What is explicitly **not** required

Stated so a reviewer does not ask for it:

| Not required | Reason |
|---|---|
| Cell outputs and execution timing | Needs a real executor; see [11 D3](11-decisions-risks.md). NB-2 removes the false affordance instead. |
| Multi-user presence in the dock | [004](../004-crdt-collaboration/README.md) owns it. |
| A second assistant surface (e.g. inline ghost text) | Out of scope; the dock is the one place a conversation lives. |
| Model auto-selection | [005 D7](../005-llm-models/11-decisions-risks.md). |
| Databricks' full left navigation (Jobs, Compute, Marketplace) | We are not a workspace browser. |
