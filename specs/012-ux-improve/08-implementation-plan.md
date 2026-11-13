[Index](README.md) · prev: [07 Architecture](07-architecture.md) · next: [09 Edge cases](09-edge-cases.md)

# 08 · Implementation plan

Ordered so that **each phase leaves the app in a working state and every phase is independently
verifiable.** No phase depends on a later one. The pure work comes first because it is where the
tests are cheap and the semantics are decided; the wiring comes last because it is where a mistake is
visible.

The whole plan is 4 new files, 7 edited files, and 9 test files. Deleting is most of the diff.

---

## Phase 0 · Instrument (before touching behaviour)

The claims in [02](02-assessment.md) must be re-runnable or they are anecdotes.

| File | What | Why |
|---|---|---|
| `web/scripts/focus-probe.mjs` | zone geometry, focus reachability, tab order | ✅ written, used for the assessment |
| `web/scripts/focus-repro.mjs` | the disabled window, offline/online | ✅ written |
| `web/scripts/deadend-probe.mjs` | the terminal `reconnecting` | ✅ written |
| `web/scripts/state-probe.mjs` | hard refresh, deeplinks, stale links | ✅ written |
| `web/package.json` | `probe:focus`, `probe:deadend`, `probe:state` scripts | so the next person runs them |

**Gate:** the four probes run and print the pre-fix numbers recorded in [02](02-assessment.md). They
are *instruments*, not gates: they print, they do not fail the build. The gates are the unit tests.

---

## Phase 1 · `domain/compose.ts` — one answer to "may this be sent"

The defect's root. Independent of everything else, and the phase that would fix the reported bug on
its own if the rest were dropped.

```ts
// web/src/domain/compose.ts
export type BlockedReason = "archived" | "needs-resume";
export interface SendInput { status: string; requiresResume?: boolean }
export type SendDecision = { canSend: true } | { canSend: false; reason: BlockedReason; message: string };

export function canSend(input: SendInput): SendDecision;
export function canAct(input: SendInput): boolean;   // approvals, Stop, Restore
export function reasonText(reason: BlockedReason): string;
```

**`conn` is absent from `SendInput` on purpose** ([P1], [FX-5]). A call site that wants to disable on
connection state cannot express it without changing the type — which is the enforcement.

| Test | Asserts |
|---|---|
| `compose.test.ts` | the full truth table: 3 statuses × requiresResume × nothing else |
| | `canSend` ignores every connection-shaped property that could be added later (a type-level test via `satisfies`) |
| | `reasonText` is a total function over `BlockedReason` — adding a reason breaks the build |

**DRY note.** `reasonText` exists so the dock, the main composer and the `aria-describedby` element
say the same sentence. Three copies of a sentence is how they drift.

---

## Phase 2 · `domain/stream.ts` — the machine

```ts
// web/src/domain/stream.ts
export type ClosedReason = "not-found" | "cursor-ahead" | "rejected" | "unknown";
export type StreamState =
  | { kind: "idle" } | { kind: "connecting" } | { kind: "live" }
  | { kind: "reconnecting"; attempt: number; nextInMs: number }
  | { kind: "closed"; reason: ClosedReason };

export function afterOpen(): StreamState;                       // → live
export function afterFailure(status: number | null, attempt: number, online: boolean): StreamState;
export function afterRetry(state: StreamState): StreamState;    // a user pressed Retry
export function isLive(s: StreamState): boolean;
export function describe(s: StreamState): { word: string; action: "none" | "retry" | "retry-or-new"; urgent: boolean };
```

| Status | Verdict | Reason |
|---|---|---|
| `404` | `closed` | the session is gone; retrying cannot help |
| `409` | `closed` | the cursor is ahead of the journal; a retry repeats it |
| `422` | `closed` | the request is malformed; a retry repeats it |
| `null` and `!online` | `reconnecting` | offline is transient by definition |
| anything else | `reconnecting` | backoff `min(1000·2^attempt, 15000)` |

| Test | Asserts |
|---|---|
| `stream.test.ts` | every status in the table above |
| | backoff is 1s, 2s, 4s, 8s, 15s, 15s… and never exceeds 15 s |
| | `afterRetry` resets the attempt counter, so a manual retry is not punished for a prior failure |
| | `describe` is total over `StreamState` |

**DRY note.** `describe()` is the ONLY place a connection state becomes words. That kills the current
duplication where `AssistantDock` has a pill, `mission.ts` has a `missionStatus` paragraph, and
`RunStatus` has its own heading — three vocabularies for one fact.

---

## Phase 3 · `domain/scroll.ts` — hand-off as arithmetic

```ts
// web/src/domain/scroll.ts
export interface Box { scrollTop: number; scrollHeight: number; clientHeight: number }
export function absorb(box: Box, deltaPx: number): number;      // how much this box takes
export function toPixels(delta: number, deltaMode: number, linePx?: number, pagePx?: number): number;
```

| Test | Asserts |
|---|---|
| `scroll.test.ts` | at the top with a negative delta: absorbs all of it |
| | at the bottom with a positive delta: absorbs none |
| | in the middle: absorbs the whole delta |
| | a non-scrolling box (`scrollHeight === clientHeight`) absorbs nothing, so the ancestor gets it all |
| | a delta larger than the remaining extent: absorbs exactly the remainder |
| | `toPixels`: `DOM_DELTA_PIXEL` = 1, `LINE` = 16, `PAGE` = `clientHeight` |

---

## Phase 4 · `hooks/useSessionStream.ts` — carry the machine, keep the hard-won parts

The riskiest edit, because this file contains two fixes that were expensive:

```140:144:apps/coding-agent/web/src/hooks/useSessionStream.ts
    /* Always from the start. The view is rebuilt from nothing above, so the replay IS the transcript:
       a cursor kept across page loads (it used to live in localStorage) resumed past events this
       fresh view had never seen, and a reload, a second tab or a pasted session link showed an empty
       conversation. The cursor in this ref only serves reconnects within the page. */
```

| Change | Detail |
|---|---|
| state | two `useState` (`session`, `conn`) → `conn: StreamState` driven by `domain/stream.ts` |
| retry | a `setTimeout` to `open()` after `nextInMs`, cleared on unmount and on a manual retry |
| status | `EventSource` does not expose the HTTP status. Use `fetch(url, {method:"GET", headers:{Accept:"text/event-stream"}})` to learn it **only on error**, then decide; if it is a 200 the `EventSource` is re-opened. This is the one genuinely fiddly piece — recorded as `[D2]`. |
| manual retry | `retry()` closes and re-opens, resetting `attempt` |
| keep | `seq.current = 0` on session change; `BATCH_MS = 40`; the `flush` queue; `mergeTurns`; `hydrate` |

| Test | Asserts |
|---|---|
| `useSessionStream.test.ts` | a session change replays from seq 0 (prevents the empty-transcript regression) |
| | a 404 puts the hook in `closed`, not `reconnecting` |
| | a 503 retries and reaches `live` |
| | a manual retry from `closed` re-opens |
| | the stream effect does not depend on state that changes when events arrive (the reconnect-loop regression) |

**Ordering note.** Phase 2 must land before this phase, because a hook that cannot name its states
cannot be tested. This is the only hard ordering constraint in the plan.

---

## Phase 5 · `components/StreamNotice.tsx` — one announcement

```tsx
<StreamNotice state={conn} onRetry={retry} onNew={newSession} />
```

| State | Renders | a11y |
|---|---|---|
| `idle` | nothing | — |
| `connecting` | "connecting…" | `role="status"` |
| `reconnecting` | "reconnecting…" + **Retry now** | `role="status"` |
| `closed` | "session closed" + reason + **Retry** + **New conversation** | `role="alert"` |

Test `StreamNotice.test.tsx`: every state renders; the action is the first focusable child of the
notice ([ST-5]); `closed` is assertive and the others polite ([ST-7]).

**Replaces:** the `.pill` `<span>` at `AssistantDock.tsx:134-138`, and the connection branch of
`missionStatus` (`mission.ts:34-38`) — which becomes unreachable and is deleted.

---

## Phase 6 · `Composer.tsx` — `readOnly` and a stated reason

```diff
+ const blocked = !canSend(session).canSend;
+ const why = !blocked ? "" : canSend(session).reason;   // via one call
  <textarea
-   disabled={disabled}
+   readOnly={blocked}
+   aria-disabled={blocked || undefined}
+   aria-describedby={blocked ? `${id}-why` : undefined}
+   placeholder={blocked ? reasonText(why) : (placeholder ?? DEFAULT)}
```

| Element | Rule |
|---|---|
| textarea | focusable always; never `disabled` ([FX-1], [FX-2]) |
| reason | rendered once, `id`suffixed, `aria-describedby`-linked ([FX-2]) |
| Send button | stays `disabled` while blocked — a button that cannot act should not be pressable |
| visual | `.composer-box.is-blocked`: tinted, dashed border ([FX-3]) |
| `⌘L` | focuses; if blocked the reason is announced ([FX-4]) |

Test `Composer.test.tsx`: a blocked composer is focusable, accepts no keystrokes, has the reason in
`aria-describedby`, and its Send is disabled. A writable one has none of those.

---

## Phase 7 · Wire the call sites, delete the re-derivations

| File | Change |
|---|---|
| `AssistantDock.tsx:90` | `canSend(session)` from domain; no `conn` |
| `AssistantDock.tsx:134-138` | the pill → `<StreamNotice/>` |
| `RunStatus.tsx:18,40,44` | `connected` → `canAct(session)`; never gate on `conn` |
| `App.tsx:993` | approvals → `canAct(session)` |
| `App.tsx:997` | `canSend(session)`; the unparenthesised expression is deleted |
| `mission.ts:34-38` | the connection branch is deleted (StreamNotice owns it) |

Test `sendGates.test.tsx`: walks every `(status, requiresResume, conn)` combination and asserts the
dock composer, the main composer, Restore, Stop and the approval buttons all agree ([FX-6]). This is
the test that would have caught F7.

---

## Phase 8 · Escape, at last

| File | Change |
|---|---|
| `keys.ts:135` | `stop` becomes `owner: "shell"` ([KB-B]) |
| `App.tsx:655-672` | the five `if`s → `close(escapeTarget(...))` with an exhaustive `switch` ([KB-A]) |
| `useHotkeys.ts:44` | the comment stops claiming something untrue |

Test `escape.test.tsx`: with a drawer open and focus in a cell, Escape closes the drawer ([KB-B]);
with nothing open it returns `false` so the browser keeps the key ([KB-D]); the order is the one
`escapeTarget` documents ([KB-C]).

**A wiring test, not just a unit test** — the reason [F4] survived this long:

```ts
it("the shell calls escapeTarget, not its own chain", () => {
  const spy = vi.spyOn(keys, "escapeTarget");
  render(<App/>); press("Escape");
  expect(spy).toHaveBeenCalled();
});
```

---

## Phase 9 · Scroll hand-off

`hooks/useScrollHandoff.ts`: one delegated `wheel` listener on `document`, non-passive, that walks
from `event.target` up the scrollable ancestors calling `absorb()`.

| Rule | Detail |
|---|---|
| only when contained | if the innermost scroller absorbs everything, do nothing — the native behaviour already ran |
| hand the remainder down | `ancestor.scrollTop += remainder`, then `preventDefault()` |
| never at the document | if no ancestor can take it, do **not** prevent ([SC-3]) |
| keep `overscroll-behavior: contain` | the CSS rule prevents the *chain*; this handles the *hand-off* |

`scroll.test.ts` covers the arithmetic; a Playwright scene `[S8]` covers the real wheel.

---

## Phase 10 · Verification

| Gate | Command | Pass |
|---|---|---|
| types | `npx tsc -b --noEmit` | clean |
| unit | `npx vitest run` | all green, +9 files |
| a11y | `node scripts/a11y-audit.mjs` | no new violations, blocked composer announces its reason |
| overflow / cls | `node scripts/overflow-audit.mjs`, `cls-audit.mjs` | unchanged |
| probes | `node scripts/deadend-probe.mjs` | `canType=true`, `recoveryControls` non-empty |
| e2e | `node scripts/deep-link-e2e.mjs`, plus `[S1]`..`[S8]` | see [10](10-e2e-plan.md) |
| screenshots | `specs/012-ux-improve/e2e/screenshots/` | each one inspected, listed in [11](11-outcome.md) |

---

## What each phase buys, independently

| Phase | Fixes | If every later phase were cancelled |
|---|---|---|
| 1 | F1, F7 | the reported bug is gone; the box cannot be disabled by a connection |
| 2 | F2 | the dead end becomes a named state |
| 3 | F8 | scroll continues across the boundary |
| 4 | F2 (wiring) | the state machine is actually used |
| 5 | F3, F6 | the user can see and act on a non-live state |
| 6 | F6 | the invitation stops looking like the refusal |
| 7 | F7 | the four call sites agree |
| 8 | F4, F5 | Escape works, and the documented order is the real one |
| 9 | F8 (wiring) | the wheel hands off |

**The DRY principle applied to the plan itself:** phases 1, 2 and 3 are three *different* questions,
not three implementations of one. The only thing they share is the layering rule (`domain/` is pure),
which is enforced by the import test rather than repeated in each phase.

**The SOLID principle, concretely:**

| Letter | Where it shows |
|---|---|
| **S**ingle responsibility | `canSend` decides permission; `StreamNotice` decides wording; the hook carries both |
| **O**pen/closed | a new `ClosedReason` requires editing one union and one `switch`, and `tsc` names every site |
| **L**iskov | every `StreamState` is consumed by `describe()` with no special cases at call sites |
| **I**nterface segregation | `SendInput` has 2 fields; it does not take a whole `SessionView` or a `Conn` |
| **D**ependency inversion | components depend on `canSend`/`describe`, never on `conn` or on `EventSource` |
