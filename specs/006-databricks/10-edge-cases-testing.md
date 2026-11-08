# 10 · Edge cases and testing

[Index](README.md) · prev: [09 Implementation plan](09-implementation-plan.md) · next: [11 Decisions and risks](11-decisions-risks.md)

Every edge case has an id, the failure it would cause, the mitigation, and **the test that fails if
the mitigation is removed**. An edge case without a test is a hope, and this app has already shipped
two inert controls by hoping.

---

## Focus and binding

### E-01 · The document closes while it is the focus

**Failure:** the dock keeps `in context: revenue.sql`, the prompt attaches a file that is no longer
open, and the user cannot tell why the answer mentions code they closed.

**Mitigation:** `withoutDoc(focus)` is called from `closeDoc`, so the focus becomes "nothing open" and
the chip says so. The turn history is untouched.

**Test:** vitest `focus.test.ts` — `closing the focused document clears the focus`; e2e — open, close,
assert the chip.

### E-02 · The focus points at a document that failed to load

**Failure:** the user picked a file with no permission; the viewer shows `PaneError`; the dock still
claims to be about it, and a prompt attaches something the agent cannot read.

**Mitigation:** a failed `GET /workspace/object` clears the doc from `docs` and therefore from the
focus. The dock falls back to "nothing open".

**Test:** e2e with a mocked 403 on `/api/workspace/object`; assert the chip.

### E-03 · Two documents, one session, alternating questions

**Failure:** the transcript accumulates turns about different files with no record of which — the
classic "what was that answer about" bug.

**Mitigation:** each turn stores its binding in the event payload, and the transcript renders a small
`about: <name>` label per turn when it differs from the previous turn's.

**Test:** vitest on the turn label logic; e2e — ask about A, then B, both labels present.

### E-04 · A cell is bound, then the notebook is edited so the cell index moves

**Failure:** the prompt describes "cell 3" while the user means what is now cell 4. The agent edits the
wrong code — the most damaging failure in this spec.

**Mitigation:** the binding carries the cell's **content hash**; `binding.py` re-reads the object,
compares, and if it differs the rendered context says *"cell 3 changed since you selected it: <sha> →
<sha>"* and includes the current text, so the agent works on what exists rather than on what was
described.

**Test:** pytest — a binding with a stale hash renders the changed-cell notice; e2e — edit a cell after
binding, ask, assert the notice appears in the request body (captured by the fake agent).

### E-05 · The cell index is out of range

**Failure:** a 500, or an empty attachment silently dropped.

**Mitigation:** `binding.py` raises a typed `BindingError`; the route maps it to 422 with a sentence
(`that cell is no longer in this notebook`); the client shows it in the dock's failed state.

**Test:** pytest — index 99 on a 3-cell notebook.

### E-06 · The same object is bound twice (a doc and its cell)

**Failure:** the notebook and one cell both sent; the model gets the cell text twice and the context
budget is wasted.

**Mitigation:** `attachmentsFor` returns a cell binding **instead of** its document binding, never both.

**Test:** vitest — `a cell binding supersedes its document`.

---

## Layout and placement

### E-07 · Three zones at exactly 1180 px

**Failure:** the centre column drops below 480 px, which is the guarantee
[001 SH-G3](../001-perfect-shell/02-requirements.md) made.

**Mitigation:** `modeFor(1180)` is `mid`, so the dock takes no column there. The boundary is tested,
not assumed.

**Test:** `layout.test.ts` — at 1180 the dock is an overlay; at 1181 it may be a column and the centre
stays ≥ 480.

### E-08 · The dock is wide and the rail is wide at 1280 px

**Failure:** two 500 px panels and a 280 px sliver of code.

**Mitigation:** `maxWidth` already enforces `MAX_SHARE` and `CENTRE_MIN` for a zone; the dock is
subject to the same function, with the other zones as siblings.

**Test:** `layout.test.ts` — `no combination of widths can push the centre below CENTRE_MIN`, iterating
over ranges rather than one case.

### E-09 · Resize from 1600 to 760 with the dock open

**Failure:** the drawer appears by itself and covers the code the user was reading.

**Mitigation:** crossing a breakpoint closes drawers
([`App.tsx:89`](../../apps/coding-agent/web/src/App.tsx) already does this for the other two); the
dock joins the same effect.

**Test:** e2e — resize, assert the drawer is closed and the toggle is unpressed.

### E-10 · The dock is hidden and the user presses ⌘J while the composer has focus

**Failure:** the key inserts nothing but the dock opens behind a focused composer; or worse, the
composer swallows the key.

**Mitigation:** `⌘J` is registered in the global hotkey layer and the composer only intercepts
`Enter`, `Shift+Enter`, `Escape`, `ArrowUp/Down` and `Tab`.

**Test:** e2e — focus the composer, press `⌘J`, the dock toggles.

### E-11 · 200 % zoom at 760 px

**Failure:** the dock's header chip and the model label collide; the composer's Send button is pushed
out.

**Mitigation:** both the chip and the model label truncate with `text-overflow` and carry `title`; the
composer's action row wraps rather than overflows.

**Test:** `audit:overflow` at 200 % zoom; a screenshot in [12](12-e2e-plan.md).

---

## The stream

### E-12 · The dock and the Chat tab both render the same session

**Failure:** two `EventSource`s, double fan-out, and a `localStorage` cursor written twice.

**Mitigation:** one hook instance at `App` level, passed down. A second `EventSource` for `/stream` is
a review-blocking defect.

**Test:** e2e counts requests to `/stream` while both views are mounted (Playwright `request` events);
expected exactly one.

### E-13 · The page reloads mid-turn

**Failure:** the answer starts over, or the turn is lost.

**Mitigation:** the client resumes from `?after=<seq>` (existing); with
[P6](09-implementation-plan.md#p6-persistence-l) the server can replay the turn's deltas from the
durable log, so the answer continues rather than restarting.

**Test:** e2e — send, reload at 1 s, assert the turn completes and its text is whole.

### E-14 · A very long answer in a 320 px column

**Failure:** markdown re-parsing per delta freezes the tab; or the answer overflows horizontally on a
code block.

**Mitigation:** existing 40 ms batching and `MAX_ANSWER` cap; `overflow-x: auto` on code blocks inside
the dock; `min-width: 0` on the dock's flex children.

**Test:** a vitest render-count assertion, and an e2e with a 20 000-character answer at 760 px asserting
`scrollWidth <= clientWidth` on the dock.

### E-15 · The connection drops and the dock says nothing

**Failure:** a user types into a dead session and loses the message.

**Mitigation:** the existing `conn` state (`reconnecting`, `lost`) is rendered in the dock header, and
the composer is disabled with the reason while `lost`.

**Test:** e2e with the route aborted; assert the header and the disabled composer.

---

## The model control

### E-16 · No models are available at all

**Failure:** an empty popover, or a control that opens nothing.

**Mitigation:** the picker already renders an explanatory empty state
([`ModelPicker.tsx:280-285`](../../apps/coding-agent/web/src/components/ModelPicker.tsx)); the composer
control shows `model · none` and is still clickable, because the explanation is the useful part.

**Test:** existing picker test plus a vitest on the control's label for an empty catalogue.

### E-17 · The pinned model becomes unavailable mid-session

**Failure:** the next turn fails with a provider error the user did not cause.

**Mitigation:** the control shows a warning glyph, the popover states the remedy on the current row, and
the failed turn keeps its pin so a retry is still meaningful.

**Test:** e2e with discovery mocked to mark the current model `not_served`.

### E-18 · A switch is refused by the agent

**Failure:** the UI shows the new model while the session still runs the old one.

**Mitigation:** `set_model` raises `ProviderUnhealthy`; the client does not update `session.model` on
failure, and the status line shows the provider's words.

**Test:** pytest on the orchestrator's refusal path (exists), plus an e2e asserting the label is
unchanged.

### E-19 · The model label at 320 px

**Failure:** `google-vertex/gemin…` — meaningless truncation.

**Mitigation:** `label()` produces the short name; the trigger prefers it and falls back to the last
path segment. `title` carries the full id.

**Test:** vitest on the formatter at 320 px width; screenshot.

---

## Persistence

### E-20 · The database is unreachable at boot

**Failure:** the app does not start, and nobody can use the assistant at all because a database for a
*different* feature is down.

**Mitigation:** start with memory, log loudly, report in `/api/ready`, show a banner (PS-3).

**Test:** boot test with an invalid DSN.

### E-21 · The database dies mid-turn

**Failure:** the turn dies too.

**Mitigation:** the turn continues; events buffer in memory; a single warning is surfaced; the next
append retries.

**Test:** store test with an injected failure on the third append.

### E-22 · Two containers, one session

**Failure:** each container has its own subscriber set, so a client sees only half the events.

**Mitigation:** out of scope, named as
[R-4](11-decisions-risks.md#r-4-two-app-instances-break-live-fan-out-medium-accepted). The
single-container deployment is asserted in [12](12-e2e-plan.md).

**Test:** none. Stated as a limit rather than tested, because testing it would require the deployment
we do not have.

### E-23 · A migration is applied twice

**Failure:** a non-idempotent statement errors at boot.

**Mitigation:** every statement is `IF NOT EXISTS` / `ON CONFLICT DO NOTHING`; the runner records a
version.

**Test:** apply twice on a scratch database; the second is a no-op.

---

## Dead controls

### E-24 · A button that does nothing

**Failure:** the two that exist today: `.cell-run`, and the in-cell `ask`.

**Mitigation:** three mechanisms — the run button is deleted with a grep test; `onAskCell` becomes a
required prop on the notebook branch so forgetting it does not compile; and the dead-control e2e walks
every visible button.

**Test:**

```text
web/scripts/dead-controls.e2e.mjs
  for each visible button in .pane.rail, .pane.main, .pane.assistant:
    click it (in a scratch context that can be restored)
    assert one of: a request fired, the DOM changed, focus moved, aria-expanded changed
    else fail with the element's aria-label and its spec requirement
```

**What "the DOM changed" means, precisely:** the e2e snapshots `document.body.innerHTML` length plus
the focused element before and after; a button that changes neither is dead. It is a coarse
instrument, and that is the point: it must not be clever enough to have false negatives.

**Known false positives and how they are handled:** a button that copies to the clipboard changes
nothing in the DOM but emits a `status` line (so the DOM does change); a button that navigates changes
the URL (checked); a button that is intentionally disabled must carry `aria-disabled` or `disabled`
and is skipped.

---

## Cross-cutting: what could still break silently

| Risk | Detected by |
|---|---|
| The dock re-introduces a horizontal scrollbar | `audit:overflow` |
| A new colour token creeps into the dock | a CSS test asserting the dock uses only `--surface`, `--line`, `--ink*`, `--blue-600` |
| The transcript re-renders on every keystroke somewhere else | a render-count test on `AssistantDock` |
| The `@` root regresses to home | `focus.test.ts` on `searchRoot`, plus an e2e searching a file outside home |
| The approval in the dock and the sheet drift apart | both call `api.decide`; one test asserting the same three outcomes |

---

## The test pyramid for this spec

| Level | Count | What it covers |
|---|---|---|
| vitest domain (`focus`, `dock`, `files`, `searchroot`, `layout`) | ~45 new | every decision, with no DOM |
| vitest components (`AssistantDock`, `Composer` variant) | ~8 new | the four states render, the variant does not fork behaviour |
| pytest domain (`binding.py`) | ~8 new | cell parsing, stale hash, out of range, dedupe |
| pytest store (`test_store_pg.py`) | ~10 new | replay, batching, cascade, failure injection |
| e2e (`dock-e2e.mjs`) | 11 scenes | the sequence in [04](04-assistant-dock.md#acceptance-as-a-sequence) plus widths and themes |
| e2e (`dead-controls.e2e.mjs`) | 1 walk | UX-1 |
| audit (`dock-audit.mjs`) | 6 widths | the five numbers in [01](01-current-state-audit.md) |

The ratio is deliberate: **most of the new logic is in `domain/` because that is where it can be
tested exhaustively.** A dock with more component logic than domain logic would be a dock whose four
states are only ever verified by eye.
