[Index](README.md) · prev: [06 Lenses](06-lenses.md) · next: [08 Implementation plan](08-implementation-plan.md)

# 07 · Architecture

Where each new rule lives, what it replaces, and why it belongs there rather than one layer up or
down. The governing constraint: **the pure layer decides, the React layer carries.** That rule is
already the repository's (`layout.ts`, `keys.ts`, `route.ts` are all pure and all tested without a
DOM); this work extends it rather than inventing a second style.

---

## The layering, and what it costs to break it

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  domain/            pure · no React · no DOM · unit-tested in isolation      │
│                                                                             │
│   compose.ts  NEW   canSend(session, draft) → SendDecision                  │
│   stream.ts   NEW   streamState(...) → StreamState   (the machine)          │
│   scroll.ts   NEW   handoff(scroller, delta) → number | null                │
│   keys.ts     EDIT  escapeTarget becomes the only Escape resolver           │
│   layout.ts   —     unchanged (measured correct)                            │
│   route.ts    —     unchanged (measured correct)                            │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │  carries the decision, decides nothing
┌───────────────────────────────────▼─────────────────────────────────────────┐
│  hooks/             binds a pure module to React and to one browser API     │
│                                                                             │
│   useSessionStream.ts  EDIT  owns the state machine and the retry timer      │
│   useScrollHandoff.ts  NEW   one delegated wheel listener for the document   │
│   useHotkeys.ts        EDIT  calls escapeTarget, and only for Escape         │
│   useReturnFocus.ts    —     unchanged (measured correct)                    │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │  renders the decision
┌───────────────────────────────────▼─────────────────────────────────────────┐
│  components/        presentation only                                       │
│                                                                             │
│   Composer.tsx      EDIT  readOnly+aria-disabled, reason, no `disabled`      │
│   AssistantDock.tsx EDIT  call canSend; state word + its action, one group   │
│   RunStatus.tsx     EDIT  never gate on conn; gate on writability            │
│   StreamNotice.tsx  NEW   the one place a non-live state is announced        │
│   App.tsx           EDIT  delete four re-derivations; wire escapeTarget       │
└─────────────────────────────────────────────────────────────────────────────┘
```

**The test for "is this in the right layer?"** — if the rule can be stated without the words
*element*, *event*, *class* or *render*, it belongs in `domain/`. All five of this spec's rules can:

| Rule | Stated purely |
|---|---|
| [FX-5] | "may this draft be sent, given this session?" |
| [ST-1..3] | "given the last attempt and its outcome, what is the next state and when?" |
| [SC-1] | "given a scroll offset, an extent and a delta, which container takes the delta?" |
| [KB-A] | "given what is open, what does Escape close?" |
| [FX-2] | "is this composer writable, and why not?" |

---

## 1. `domain/compose.ts` — one answer to one question

Replaces four expressions ([02 §6](02-assessment.md#6-the-same-question-answered-three-ways)).

```ts
export interface SendInput {
  status: SessionView["status"];      // ready | streaming | archived
  requiresResume: boolean;
  hasSession: boolean;                // a session exists at all
}                                     // NOT: conn. Deliberately absent. [P1]

export type SendDecision =
  | { canSend: true }
  | { canSend: false; why: "archived" | "needs-resume" | "no-session"; reason: string };

export function canSend(input: SendInput, draft: string): SendDecision;
```

Three properties, each a test:

1. **`conn` is not in the signature.** Not "is ignored" — cannot be passed. The type system is the
   enforcement, so a future call site cannot reintroduce F1 without editing the module and its
   tests. This is the whole point of [P1] made structural.
2. **`why` is an enum, not a sentence**, so the component chooses the wording and the same reason
   renders identically in the dock, the main composer and the reason element ([FX-6]).
3. **A draft is required for `canSend`**, because "the box works" and "there is something to send"
   are different questions and `Send` is disabled for the second one. Conflating them is how the
   original bug hid: the button and the box shared one flag.

## 2. `domain/stream.ts` — the missing state

Replaces the pair of `useState`s in `useSessionStream` that can only express "live or not".

```ts
export type StreamState =
  | { kind: "idle" }
  | { kind: "connecting" }
  | { kind: "live" }
  | { kind: "reconnecting"; attempt: number; nextInMs: number }
  | { kind: "closed"; reason: ClosedReason };

export type ClosedReason = "not-found" | "cursor-ahead" | "rejected" | "unavailable" | "unknown";

/** What to do after an attempt failed. Pure: it returns a decision, the hook performs it. */
export type Verdict =
  | { retry: true; afterMs: number; state: Extract<StreamState, { kind: "reconnecting" }> }
  | { retry: false; state: Extract<StreamState, { kind: "closed" }> };

export function afterFailure(status: number | null, attempt: number, online: boolean): Verdict;
export function afterOpen(): Extract<StreamState, { kind: "live" }>;
```

Three properties:

1. **The retryable set is data.** 404/409/422 → closed. Everything else → retry with
   `min(1000 * 2**attempt, 15000)`. One table, one test.
2. **`nextInMs` is part of the state**, so the UI can show "Retry now" and mean it, and a test can
   assert the schedule without a clock.
3. **`online` is an input**, because offline is a different reason than a 5xx and the copy differs.

## 3. `domain/scroll.ts` — hand-off, as arithmetic

```ts
export interface Box { scrollTop: number; scrollHeight: number; clientHeight: number }

/** How much of `delta` this box can absorb. 0 at an edge, `delta` in the middle. */
export function absorb(box: Box, delta: number): number;
```

The hook does the DOM work; this decides *how much*. A pure function means the edge cases (delta
larger than the remaining extent, a box that does not scroll at all, a `deltaMode` of lines or pages)
are unit-testable without a browser.

`deltaMode` matters and is easy to miss: a mouse wheel reports pixels, Firefox with a line-based
setting reports lines, and a page-based wheel exists. The hook normalises to pixels before calling
`absorb`, and a test holds the three conversions.

## 4. `hooks/useSessionStream.ts` — owns the machine, not the policy

The hook keeps exactly what a hook must: the `EventSource`, the seq cursor, the timer handle, and the
flush buffer. Every *decision* moves to `domain/stream.ts`.

```
  what the hook does                what the domain decides
  ────────────────────────           ───────────────────────────────────
  open()/close() the source          is this state live, retrying, or closed
  setTimeout for the next attempt    how long to wait, and whether to retry
  parse the event, bump seq          nothing (the reducer already owns it)
  batch events at 40 ms              nothing
```

The one subtlety, kept because it was hard-won (spec 010): **`seq` resets to 0 when the session
changes** and must not be persisted. The comment at `useSessionStream.ts:140-144` explains why, and
this change must not disturb it. A test asserts a session switch replays from 0.

## 5. `components/StreamNotice.tsx` — one announcement, one action

The only component that renders a non-`live` state. It replaces the pill in `AssistantDock` and the
duplicate logic in `RunStatus`'s `missionStatus`.

| State | Word | Action | Live region |
|---|---|---|---|
| `connecting` | "connecting" | none (it resolves) | `role="status"`, polite |
| `reconnecting` | "reconnecting…" | **Retry now** | `role="status"`, polite |
| `closed` | "session closed" | **Retry** · **New conversation** | `role="alert"`, assertive |
| `idle` | nothing rendered | — | — |

`closed` is assertive because it is a terminal state about lost work; the others are polite because
they resolve. That distinction is [ST-7] and it is the difference between an interruption and a
background note.

## 6. `Composer.tsx` — `readOnly` is the correction, not a workaround

```diff
- <textarea disabled={disabled} …>
+ <textarea
+   readOnly={blocked}
+   aria-disabled={blocked || undefined}
+   aria-describedby={blocked ? reasonId : undefined}
+   placeholder={blocked ? why : placeholder}
+   …>
```

| Property | `disabled` (before) | `readOnly` + `aria-disabled` (after) |
|---|---|---|
| focusable | **no** | yes |
| in the tab order | **no** | yes |
| reachable by `⌘L` | no | yes |
| text selectable | no | yes |
| screen reader announces it | as nothing | as "read only, <reason>" |
| a keypress changes the value | no | no |

The last row is why this is safe: `readOnly` refuses edits exactly as firmly as `disabled`; it only
stops pretending the control is not there. [FX-2]

`Send` stays genuinely `disabled` while blocked — a button that cannot act should not be pressable,
and a button is not the place a user has to be able to put the cursor.

## 7. `App.tsx` — deletions, and one wiring

Most of the diff here is removal:

| Removed | Replaced by |
|---|---|
| `canSend` inline (line 997) | `canSend(session, draft)` |
| `conn !== "live"` on the approval (line 993) | `!canAct(session)` — approvals need a writable session, not a live stream |
| five `if`s in the `stop` handler (655–672) | `escapeTarget(state)` then a `switch` on its answer |
| `stop` with `owner: "composer"` in `keys.ts:135` | `owner: "shell"`, so Escape reaches the shell from anywhere |

**The `escapeTarget` wiring, which is the point of [KB-A]:**

```ts
const close = (target: EscapeTarget): boolean => {
  switch (target) {
    case "dialog":     …; return true;
    case "popover":    …; return true;
    case "drawer":     …; return true;
    case "edit":       …; return true;
    case "stop-agent": …; return true;
    case "nothing":    return false;   // let the browser have it
  }
};
```

A `switch` over a union is exhaustive by the type checker, so adding an `EscapeTarget` becomes a
compile error instead of a silent fall-through. That is [KB-A] enforced by `tsc` rather than by
review.

---

## Dependency rule

```
   components ──► hooks ──► domain
        │           │         ▲
        └───────────┴─────────┘        components may import domain directly
                                     domain imports nothing but itself
```

Enforced by a test that walks the import graph: `domain/` may not import from `hooks/` or
`components/`, and may not reference `window`, `document`, or `localStorage`. `route.ts` today takes
`{ origin, pathname }` as an argument instead of reading `window.location`, and that is the pattern
this rule keeps.

---

## What deliberately does not move

| Component | Why it stays |
|---|---|
| `layout.ts` | measured correct at every width; the defect does not touch geometry |
| `useReturnFocus.ts` | its contract (opener → fallback → successor) is already right and tested |
| `route.ts` / `useRoute.ts` | hard refresh and deeplinks measured PASS ([LK-1]..[LK-3]) |
| `events.ts` reducer | the state shape is not the problem; the *permission* derived from it was |
