[Index](README.md) · prev: [05 Diagrams](05-diagrams.md) · next: [07 Architecture](07-architecture.md)

# 06 · Six lenses

The same defect seen by six people who would each be paged for a different part of it. The point is
not that there are six opinions; it is that five of the six find something the others miss.

---

## 1. The accessibility engineer

**Finding.** `disabled` removes a control from the tab order **and** from the accessibility tree's
focus. A screen-reader user cannot reach the composer, cannot discover it exists, and is never told
why. The visual user at least sees an inert grey box; the assistive user gets silence.

| Rule | Status before | Requirement |
|---|---|---|
| WCAG 2.2 **3.3.1 Error identification** | the state is not identified at all | [FX-2] |
| WCAG 2.2 **1.3.1 Info and relationships** | the reason, once added, must be programmatically linked | [FX-2] `aria-describedby` |
| WCAG 2.2 **4.1.3 Status messages** | `reconnecting…` is a bare `<span>`, not a live region | [ST-7] |
| WCAG 2.2 **2.1.1 Keyboard** | a disabled composer is unreachable, and so is the only way to ask | [FX-1] |
| WCAG 2.2 **2.4.3 Focus order** | measured: the tab order jumps chrome → rail → main → dock correctly, *except* the dock composer is skipped when disabled | [FX-8] |

**The measurement that matters:** `state-probe.mjs` confirms a `disabled` textarea does not become
`activeElement`. There is no clever `tabIndex` that fixes this; the attribute must go.

**What this lens adds to the plan:** `readOnly` + `aria-disabled` is not a stylistic alternative to
`disabled` — it is the only shape that satisfies 2.1.1 while still refusing the input.

---

## 2. The keyboard-only power user

**Finding A.** `⌘L` promises "focus the message box". When the box is disabled it does nothing, with
no feedback — the worst of the three possible behaviours (it could focus-and-explain, or explain).

**Finding B.** Escape is the universal "get me out". Measured behaviour: with the rail drawer open and
focus in the notebook, Escape does nothing at all, because `stop` is owned by the composer
([F5]). A keyboard user's only exit is Tab-hunting for a close button.

**Finding C.** The tab order is otherwise good — `focus-probe.mjs` shows every zone reachable and in
visual order. That is worth protecting: the fix must not insert a focusable "reason" element into the
tab sequence ahead of the box.

| Requirement | Detail |
|---|---|
| [FX-4] | `⌘L` always lands on a focusable box, and states why if it cannot accept text |
| [KB-B] | Escape is a shell chord, so it works from any zone |
| [KB-C] | ...but only unwinds the *topmost* transient, so it never surprises |
| [FX-2] | the reason is `aria-describedby`, not a separate tab stop |

**What this lens adds:** the reason must be *attached* to the control, not a sibling the user has to
Tab into. The wireframe in [04 §5](04-wireframes.md#5-a-non-writable-composer-and-how-it-differs-from-a-writable-one)
shows the placeholder being replaced, which is where a keyboard user already looks.

---

## 3. The site reliability engineer

**Finding.** The stream state machine is missing a state. `useSessionStream` handles `onopen` and
`onerror` and assumes the browser's automatic reconnect is a complete recovery strategy. It is not:

- `EventSource` retries **only** a connection that dropped after a `200`. A non-200 response is final
  — the browser sets `readyState = CLOSED` and stops.
- So `404` (session archived/reaped by the reaper — which is *expected* after the idle timeout), `409`
  (replay cursor ahead of the journal, which happens when a second tab advanced it), and `422` are all
  terminal, and all render as `reconnecting`.

That means **a routine platform event — the reaper archiving an idle session — puts every open tab
into a permanent state that looks like a network blip.** That is the difference between "a user is
confused" and "an incident".

| Requirement | Why the SRE cares |
|---|---|
| [ST-2] | distinguishing `closed` from `reconnecting` is what makes the state alertable |
| [ST-3] | bounded backoff prevents a thundering herd of `EventSource`s when the platform restarts |
| [ST-4] | the manual Retry is a circuit-breaker reset the user controls |

**What this lens adds:** the retry must be *bounded and named*, not infinite and silent. And the
`closed` reason must be specific enough to distinguish "your work is gone" from "try again".

---

## 4. The product designer

**Finding.** The screen in the screenshot tells the user three things and none of them is actionable:
"READY", "reconnecting…", and a paragraph about the server running independently. The paragraph is
true, warm, and useless — it explains *why* the user cannot act while the user is trying to act.

A better screen says the same thing in the opposite order: **what you can do**, then *why*.

```
  before                              after
  ───────────────────────────         ──────────────────────────────────
  READY                               reconnecting…   [ Retry now ]
  reconnecting…                       ┌──────────────────────────────┐
  ┌─────────────────────────┐         │ Ask anything…                │  ← you can still
  │ Reconnecting to your    │         │ +  @  /    model ▾   Send    │     ask
  │ session                 │         └──────────────────────────────┘
  │ The server runs         │         Progress saved · Copy return link
  │ independently…          │
  └─────────────────────────┘
  ┌─────────────────────────┐
  │ [grey, inert box]       │  ← your sentence goes nowhere
  └─────────────────────────┘
```

Two design rules fall out, and both are requirements:

1. **The state word sits next to its action.** `reconnecting…` and `Retry now` are one control group
   ([ST-4], [ST-5]), not a word in the header and a button elsewhere.
2. **The invitation never looks like the refusal.** A non-writable box is visually distinct and says
   why ([FX-3]).

**What this lens adds:** the wording. "The server runs independently" is an apology; "Progress saved"
is a fact the RunStatus already displays, and it is the one that keeps a user calm.

---

## 5. The frontend architect

**Finding.** The defect is not in any one component. It is that the question *"may this be sent?"*
has **four** implementations and no owner ([02 §6](02-assessment.md#6-the-same-question-answered-three-ways)).

| Call site | Rule |
|---|---|
| `AssistantDock.tsx:90` | `… && (!hasSession \|\| conn === "live")` |
| `App.tsx:997` | `… \|\| conn !== "live" && Boolean(active)` |
| `RunStatus.tsx:18` | `connected = conn === "live"` |
| `App.tsx:993` | `disabled={conn !== "live"}` |

`App.tsx:997` is additionally a precedence accident: `||` and `&&` without parentheses give
`archived || requiresResume || (offline && active)`, which is the *desired* behaviour on the home
screen and an accident. A reader who "tidies" it disables typing on the home screen.

There is a second architectural smell: `handlers` in `App.tsx` is a `useMemo` whose dependency list
is 20 items long, including `layout`, `mode` and `narrow`. So **Escape's behaviour is a function of
window width**, which nobody designed and nobody would predict.

| Requirement | Architectural consequence |
|---|---|
| [FX-5] | one pure `canSend(session, draft)`; every call site delegates |
| [FX-6] | a test walks the state cross-product across both composers |
| [KB-A] | `escapeTarget` becomes load-bearing; the handler stops encoding precedence |
| [KB-B] | the `stop` shortcut moves to `owner: "shell"`, so Escape is reachable |

**What this lens adds:** the fix is mostly *deletion and centralisation*, not addition. The new code
is one pure function, one state machine, one delegated wheel handler, and one call to a function that
already exists.

---

## 6. The person who has to maintain this in six months

**Finding.** `escapeTarget()` is the worst kind of dead code: **documented, tested, and cited by a
comment that claims it is live.**

```
hooks/useHotkeys.ts:44   // Escape is always handled by whoever is listening (a dialog's own
                         // keydown, or the shell's ordered `escapeTarget`)
```

A maintainer reads that comment, believes Escape is ordered, and changes the `stop` handler under a
false premise. The tests pass — because they test `escapeTarget` in isolation, and never the wiring.

**The general lesson, which becomes a requirement:** *a pure function the app does not call is a
comment.* [KB-A] closes this by making the wiring itself testable, and the test asserts that the
function is called, not merely correct.

| Requirement | Maintainer value |
|---|---|
| [KB-A] | the precedence is one function, so changing it is one edit with one test |
| [FX-5] | "why is the box enabled?" has one answer to grep |
| [ST-2] | a new state cannot be added by string comparison; the union forces every switch |
| probes in `scripts/*-probe.mjs` | the claims in this spec are re-runnable, not prose |

---

## What each lens contributed that the others did not

| Lens | Contribution |
|---|---|
| Accessibility | `readOnly` + `aria-describedby` instead of `disabled` |
| Keyboard | the reason must be attached to the control, not a separate tab stop |
| SRE | `closed` ≠ `reconnecting`; bounded backoff; the reaper makes this routine |
| Design | the state word and its action are one group; the wording is a requirement |
| Architecture | four implementations of one question; `escapeTarget` dead; Escape depends on width |
| Maintainer | the dead function is cited as live by a comment — a wiring test is the only cure |
