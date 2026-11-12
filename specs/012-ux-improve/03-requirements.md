[Index](README.md) · prev: [02 Assessment](02-assessment.md) · next: [04 Wireframes](04-wireframes.md)

# 03 · Requirements

Every id is defined here exactly once and cited elsewhere. A requirement states a **behaviour that
can be observed**, so each one maps to a test in [09](09-edge-cases.md) and a scene in [10](10-e2e-plan.md).

---

## FX — Focus and input

| Id | Requirement | Why | Proved by |
|---|---|---|---|
| **FX-1** | A composer is focusable and accepts text whenever the session is *writable*: not archived and not requiring resume. The connection state never makes the field unfocusable. | F1, P1 | `canSend.test.ts`, `[S2]` |
| **FX-2** | A non-writable composer is **not** `disabled`. It is `readOnly` with `aria-disabled="true"`, keeps its tab stop, and states its reason in an element the field is `aria-describedby`-linked to. | F6, P3 | `[E-3]`, a11y audit |
| **FX-3** | A non-writable composer is visually distinct: tinted box, muted text, and the reason replaces the placeholder. | F6 | `[S5]` screenshot |
| **FX-4** | `⌘L` focuses the composer of the zone the user is looking at, and if that composer is non-writable it focuses the box **and announces the reason** rather than silently doing nothing. | F1 | `[S5]` |
| **FX-5** | One pure function answers "may this be sent": `canSend(session, draft)` in `domain/`. No call site re-derives it. | F7, P4 | `canSend.test.ts` (full truth table) |
| **FX-6** | The dock composer and the main composer agree on every input, for every session state. | F7 | a test that walks the cross-product |
| **FX-7** | Focus never lands on `<body>` after a dialog closes, a tab closes, or a drawer closes. | 007 `KB-1` | `useReturnFocus.test.ts`, `[S6]` |
| **FX-8** | Every zone is reachable by Tab, and the tab order follows visual order: chrome → rail → main → dock. | `[S1]` | `focus-probe.mjs` |

## ST — Stream state

| Id | Requirement | Why | Proved by |
|---|---|---|---|
| **ST-1** | The stream is a state machine with exactly five states: `idle`, `connecting`, `live`, `reconnecting`, `closed`. | F2 | `streamState.test.ts` |
| **ST-2** | `closed` is a **distinct** state from `reconnecting`. It carries a reason (`not-found`, `cursor-ahead`, `network`, `unknown`). | F2 | `streamState.test.ts` |
| **ST-3** | A reconnect is attempted with bounded backoff (1 s, 2 s, 4 s, 8 s, capped at 15 s) while the failure is retryable; a non-retryable status (404, 409, 422) goes straight to `closed`. | F2 | `[E-5]`,`[E-6]` |
| **ST-4** | Every non-`live` state that is not `idle` renders **one action** next to the word that names it. `connecting` → nothing (it resolves itself). `reconnecting` → "Retry now". `closed` → "Start a new conversation" **and** "Retry". | F2, F3, P2 | `[S4]`,`[S5]` |
| **ST-5** | Retry is reachable by keyboard and is the first thing after the state word in the tab order of the dock header. | P2 | `[S4]` |
| **ST-6** | A send while `reconnecting` or `closed` is attempted and, if it fails, restores the draft and states the reason. It is never silently dropped. | P1 | `[E-7]` |
| **ST-7** | The connection state is announced to assistive technology once per change, through a single `role="status"` region, and never on every event. | 007 `KB-7` | a11y audit |

## SC — Scroll

| Id | Requirement | Why | Proved by |
|---|---|---|---|
| **SC-1** | A contained scroller at its end **hands the remaining delta to its nearest scrollable ancestor** in the same direction. | F8, P6 | `scrollHandoff.test.ts` |
| **SC-2** | Hand-off never occurs when the delta would move the inner scroller (i.e. it is not at an edge). | P6 | `scrollHandoff.test.ts` |
| **SC-3** | Hand-off never chains out of the app: at the outermost scroller the event is left to the browser. | 007 `SC-3` | `[E-9]` |
| **SC-4** | The transcript follows the stream only while the reader is pinned to the bottom, and unpins on the first upward wheel or the first upward key. | 010 | `[E-10]` |
| **SC-5** | Focusing a cell scrolls it into view **without** scrolling the document (which is `overflow: clip`). | 007 | `[E-11]` |

## LK — Links and state survival

| Id | Requirement | Why | Proved by |
|---|---|---|---|
| **LK-1** | Every one of `#/notebook/…?cell=n`, `#/file/…`, `#/table/…`, `#/session/<id>`, `#/settings/<tab>` opens correctly on a **hard** load, with no prior page state. | measured PASS, keep it | `[S7]` |
| **LK-2** | A stale or malformed deeplink renders the app with a stated notice, never a blank page and never a silent ignore. | measured PASS for the shell; the *notice* is missing | `[E-12]` |
| **LK-3** | Layout (widths, zone visibility, rail tab) survives a reload. | measured PASS, keep it | `[S7]` |
| **LK-4** | A `closed` stream's session deeplink says the session is gone and offers the conversation list, not a dead field. | F2 + LK-2 | `[E-13]` |
| **LK-5** | Copying a link while in a non-`live` state still copies a link that works after reconnecting. | 010 | `[E-14]` |

## KB — Keyboard (extends 007)

| Id | Requirement | Why | Proved by |
|---|---|---|---|
| **KB-A** | `escapeTarget()` is the **only** resolver of Escape, and the shell calls it. | F4, P5 | `keys.test.ts` + a wiring test |
| **KB-B** | Escape reaches the shell from anywhere, not only from the composer: the `stop` shortcut is `owner: "shell"` with the composer-only stop handled inside the composer. | F5 | `[E-15]` |
| **KB-C** | Escape while the agent is running stops it **only** when nothing else is open above it, in the order `dialog → popover → drawer → edit → stop-agent → nothing`. | P5 | `escapeTarget` truth table |
| **KB-D** | When nothing is open and nothing is running, Escape is **not** consumed, so the browser keeps its meaning. | 007 `KB-8` | `[E-16]` |
| **KB-E** | Every shortcut in the registry has exactly one owner, and a test asserts the handler table covers the registry exactly. | 007 `KB-5` | `keys.test.ts` |

---

## Non-goals

Stated so the work stays bounded:

| Not doing | Why |
|---|---|
| Rewriting `useSessionStream` as a reducer | The current hook is correct in what it does; it lacks states. A reducer would be a larger change with the same behaviour. |
| A websocket transport | The `EventSource` + journal replay is the durable design (010). |
| Virtualising the transcript | A different performance problem with its own spec; today's transcripts are small. |
| Changing the zone geometry model | `layout.ts` is measured and correct (see §1 of [02](02-assessment.md)). |
| Touching the agent or the notebook model | Out of scope; the defect is in the shell's state handling. |
