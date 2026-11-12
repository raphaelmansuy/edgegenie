[Index](README.md) · prev: [08 Implementation plan](08-implementation-plan.md) · next: [10 E2E plan](10-e2e-plan.md)

# 09 · Edge cases and tests

Every failure I could name, with its mitigation and the test that holds it. The ids are cited from
[03](03-requirements.md) and [08](08-implementation-plan.md).

Format: **E-n · the case** — what happens, what the user sees, and where the test lives.

---

## Composer writability

### E-1 · A session is archived while the tab is open
The reaper archives an idle session. An event arrives saying so.
**Before:** the composer becomes `disabled` mid-sentence; the draft is lost from view.
**After:** the box becomes `readOnly`, the draft **stays in the box**, and the reason replaces the
placeholder with "This conversation is archived. Start a new one." The text is selectable so the user
can copy it. A `New conversation` action is in the dock header.
**Test:** `Composer.test.tsx` — "a blocked composer keeps its value and states why".

### E-2 · `requiresResume` is true
The server restarted and the agent is not attached. Sending would produce a 409.
**After:** `readOnly`, reason "Restore the agent to continue", and the **Restore agent** button is the
highlighted action. `canAct()` is true, so Restore is pressable.
**Test:** `sendGates.test.tsx`, `RunStatus.test.tsx`.

### E-3 · A non-writable composer is the ONLY focusable thing in the dock
Tab reaches it, `aria-disabled` is true, the reason is read. `⌘L` lands on it and announces.
**After:** no new tab stop is introduced for the reason ([FX-2]).
**Test:** `focus-probe.mjs` scene `[S5]`; `a11y-audit.mjs` asserts the `aria-describedby` target exists.

### E-4 · The connection is `connecting` on first paint
**After:** the box is writable immediately ([FX-1]). Nothing is disabled for a state that resolves in
200 ms.
**Test:** `Composer.test.tsx` — "connecting does not block".

---

## Stream state

### E-5 · The session was deleted or reaped → 404
**After:** `closed`, reason `not-found`, word "session closed", actions **Retry** and **New
conversation**. Retry is honest: it will fail again, and the user learns that in one click rather
than waiting forever.
**Test:** `stream.test.ts` (404 → closed), `deadend-probe.mjs` (the action exists).

### E-6 · The replay cursor is ahead of the journal → 409
Happens when a second tab advanced the seq and this one kept a stale cursor.
**After:** `closed`, reason `cursor-ahead`. Copy is specific: "This conversation moved on in another
tab. Reopen it to catch up." Retry re-opens from 0, which is the correct recovery — so here Retry
*does* work, unlike 404.
**Test:** `stream.test.ts`, `[E-13]`.

### E-7 · A send is attempted while `reconnecting`
The box is writable. The user presses Enter.
**Outcome:** the `POST` is attempted (it does not travel over the SSE stream). On success the turn is
queued server-side and the transcript catches up on reconnect. On failure the draft is **restored**
and the reason is shown inline — the existing `submit()` catch already restores `text`; the change is
that the composer no longer *prevents* the attempt.
**Test:** `Composer.test.tsx` — "a failed send restores the draft"; `[S4]`.

### E-8 · Offline → online
`online` fires, backoff resets, `open()` runs. The draft survives (probe measured: `value` preserved).
**Test:** `useSessionStream.test.ts` — "online resets the attempt counter".

### E-9 · The wheel is over the outermost scroller
**After:** no `preventDefault()`, so the browser gets the event and whatever the platform does (a
back-navigation gesture, a page bounce) still works. [SC-3]
**Test:** `scroll.test.ts` — `absorb` returns 0 and the hook does not prevent.

### E-10 · The reader scrolled up mid-stream
A new event arrives. The transcript must **not** jump to the bottom.
**After:** unchanged — `pinned` is remembered from the last scroll event, not measured after the
update (`AssistantDock.tsx:92-100`). Protected because Phase 5 touches the same component.
**Test:** `dock-e2e.mjs` existing scene; `[S8]`.

### E-11 · Focusing a cell in an `overflow: clip` document
`scrollIntoView` on a cell while `html, body { overflow: clip }`. `clip` forbids programmatic
document scrolling, which is deliberate (`styles.css:180-183`).
**After:** the cell scrolls **within** the notebook's own scroller, and the document does not move.
**Test:** `[S6]` asserts `document.scrollingElement.scrollTop === 0` after focusing cell 12.

### E-12 · A malformed deeplink
`#/notebook/` with no path, or `#/session/` with no id.
**Measured:** `parseRoute` returns `EMPTY_ROUTE` — the app opens on the start page. Safe, but silent.
**After:** [LK-2] adds a one-line notice ("That link did not name anything. Here is your start
page.") so the user knows the link was bad rather than that the app ignored them.
**Test:** `route.test.ts` (already covers the parse), a new `[S7]` scene for the notice.

### E-13 · A deeplink to a `closed` session
`#/session/<gone>` → the stream 404s → `closed`. The screen must not be a dead field.
**After:** StreamNotice says "session closed" with **Retry** and **New conversation**; the rail still
lists the other conversations.
**Test:** `[E-5]` scene; `deadend-probe.mjs` extended to assert `recoveryControls.length > 0`.

### E-14 · Copying a link while non-`live`
**After:** `linkTo()` builds the URL from state, not from the connection, so the copied link works
after reconnecting. [LK-5]
**Test:** `RunStatus.test.tsx` — the copy action is enabled in every connection state.

### E-15 · Escape with a drawer open and focus in a cell
**Before:** nothing happened ([F5]).
**After:** the drawer closes. [KB-B]
**Test:** `escape.test.tsx`.

### E-16 · Escape with nothing open and nothing running
**After:** the handler returns `false`, `useHotkeys` does not `preventDefault`, and the browser keeps
its meaning (exit full-screen, exit reader mode). [KB-D]
**Test:** `escape.test.tsx` — asserts `defaultPrevented === false`.

### E-17 · Two tabs on the same session
Tab A advances the seq; tab B's cursor is behind. B replays from its own cursor — that is correct,
the journal is the truth. If B's cursor is *ahead* (only possible if it held a newer view than the
server), it gets a 409 → `closed` → Retry → re-opens from 0.
**Test:** `[E-6]`.

### E-18 · The `EventSource` reconnects before the retry timer
The browser's own retry may fire first. The hook must not open a second source. Guard: close the
previous source before opening, and clear the timer in the same step.
**Test:** `useSessionStream.test.ts` — "only one EventSource is open at a time".

### E-19 · The tab is backgrounded for an hour
`visibilitychange` → if the source is `CLOSED`, re-open. Combined with the new timer this is belt and
braces; the timer handles the foreground case the old code missed.
**Test:** `[S4]` covers the visible path; unit test covers the hidden one.

### E-20 · A very long draft with a send that fails
The draft is restored **with its full length**, the textarea scrolls, and the failure message is
`role="alert"` so it is announced.
**Test:** `Composer.test.tsx` — a 4000-character draft round-trips.

---

## Focus and keyboard

### E-21 · A dialog closes and the opener is gone
Its trigger was a tab that has since closed. `useReturnFocus` falls back to `successor()` — the
selected tab, then the composer, then `main`. Never `<body>`. [FX-7]
**Test:** `useReturnFocus.test.ts` (exists).

### E-22 · `⌘L` while the dock is not on screen
`focusComposer` uses `dockOnScreen ? dockComposer : composerBox`, then falls back to `composerBox`.
**After:** when the dock is hidden, `⌘L` opens the dock first, then focuses it — instead of focusing
an element nobody can see.
**Test:** `focus-probe.mjs` scene `[S5]`, dock hidden.

### E-23 · The dock is an overlay on a narrow window
Focus moving into an overlay must not leave the underlying content focusable. The overlay is a
`role="dialog"`-shaped region; on close, focus returns ([FX-7]).
**Test:** `[S6]` at 820 px.

### E-24 · Tab order with the inspector as a drawer
Measured order is chrome → rail → main → dock; the drawer must come **after** the dock, matching its
position on screen.
**Test:** `focus-probe.mjs` extended to the four-column case.

---

## Scroll

### E-25 · A cell output shorter than its max-height
`scrollHeight === clientHeight`, so `absorb` returns 0 and the notebook takes the whole delta
immediately. This is the common case and must feel native.
**Test:** `scroll.test.ts`.

### E-26 · A horizontal trackpad gesture over a vertical scroller
`deltaX` is ignored by the hand-off; only `deltaY` participates. A horizontal gesture must not be
converted into a vertical scroll.
**Test:** `scroll.test.ts` — `deltaX` never reaches `absorb`.

### E-27 · Shift+wheel (a horizontal scroll on a mouse)
The browser maps it to `deltaX` with `shiftKey`. Ignored, same as E-26.

### E-28 · A wheel over the topbar
Not inside a scroller, so the handler does nothing and the native behaviour (none) remains.
**Test:** `scroll.test.ts` — walking up finds no scrollable ancestor → no prevent.

---

## State survival (measured PASS — protected)

### E-29 · A v0 layout blob
`parse()` rejects `version: 0` and returns defaults. Total function.
**Test:** `layout.test.ts` (exists).

### E-30 · A layout blob wider than the window
`reclamp` on viewport change; `parse` clamps on load. Measured: `railWidth 320` restored at 1480.
**Test:** `layout.test.ts` (exists).

### E-31 · localStorage blocked (private mode)
`useLayout` catches on read and on write; the shell works without remembering.
**Test:** `layout.test.ts` / `useLayout` behaviour is guarded by try/catch, asserted in `[S7]` by
blocking storage via `context.addInitScript`.

### E-32 · A deeplink that names a notebook with a `?` in its path
`formatRoute` percent-encodes per segment and leaves `@`, `/` and `:` readable. `parse(format(r)) === r`
for every route is held by `route.test.ts`.
**Test:** exists.

---

## Requirement → test matrix

| Req | Unit | Probe / e2e |
|---|---|---|
| FX-1 | `compose.test.ts`, `Composer.test.tsx` | `[S2]` |
| FX-2 | `Composer.test.tsx` | `a11y-audit.mjs`, `[S5]` |
| FX-3 | — | `[S5]` screenshot |
| FX-4 | `Composer.test.tsx` | `[S5]` |
| FX-5 | `compose.test.ts` | — |
| FX-6 | `sendGates.test.tsx` | — |
| FX-7 | `useReturnFocus.test.ts` | `[S6]` |
| FX-8 | — | `focus-probe.mjs` |
| ST-1..3 | `stream.test.ts` | — |
| ST-4..5 | `StreamNotice.test.tsx` | `[S4]`, `[S5]` |
| ST-6 | `Composer.test.tsx` | `[S4]` |
| ST-7 | `StreamNotice.test.tsx` | `a11y-audit.mjs` |
| SC-1..3 | `scroll.test.ts` | `[S8]` |
| SC-4 | — | `dock-e2e.mjs` |
| SC-5 | — | `[S6]` |
| LK-1..3 | `route.test.ts`, `layout.test.ts` | `state-probe.mjs` |
| LK-4 | — | `deadend-probe.mjs` |
| KB-A..E | `escape.test.tsx`, `keys.test.ts` | `[S6]` |

No requirement is without a test; no test is without a requirement. That is the check that this
document set is complete.
