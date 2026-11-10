[Index](README.md) · next: [02 Assessment](02-assessment.md)

# 01 · Five whys and first principles

## The report

> "I cannot focus on the right panel to edit and ask a new command."

### Five whys

**1. Why can the user not focus the message box?**
Because the `<textarea>` is `disabled`, and a disabled form control is not focusable in any browser.
Measured: a freshly created `<textarea disabled>` does not become `document.activeElement` after
`.focus()`. See [02 §3](02-assessment.md#3-the-mechanism-proven).

**2. Why is it disabled?**
Because `canSend` is false, and `canSend` is false because `conn !== "live"`:

```90:90:apps/coding-agent/web/src/components/AssistantDock.tsx
  const canSend = p.session.status !== "archived" && !p.session.requiresResume && (!p.hasSession || p.conn === "live");
```

**3. Why is `conn` not `live`?**
Two different reasons, and they were conflated:

- **transient**: every page load starts at `connecting` until the `EventSource` fires `onopen`.
  Measured window: **~200 ms** (`t=704 disabled=true` → `t=909 disabled=false`). A user who clicks and
  types on arrival loses their first keystrokes.
- **permanent**: the stream was refused. `onerror` sets `reconnecting`, and the browser has already
  given up on that `EventSource` (it does not retry a non-200). Nothing in the hook re-opens it
  except `visibilitychange` and `online`. So `reconnecting` is not a promise of recovery; it is a
  label printed after the last retry.

**4. Why does a permanent `reconnecting` have no way out?**
Because the four controls that could act are *all* gated on the same `conn === "live"`:

| Control | Gate | File:line |
|---|---|---|
| the composer | `(!p.hasSession \|\| p.conn === "live")` | `AssistantDock.tsx:90` |
| Restore agent | `disabled={pending \|\| !connected}` | `RunStatus.tsx:40` |
| Stop work | `disabled={pending \|\| !connected}` | `RunStatus.tsx:44` |
| inline approval | `disabled={conn !== "live"}` | `App.tsx:993` |

The state that most needs a manual action disables every manual action. That is the bug, stated as a
design error rather than a typo.

**5. Why was "connection" allowed to become "permission"?**
Because the question *"may this user send right now?"* has no owner. It is answered three times:

```
AssistantDock.tsx:90   canSend = … && (!hasSession || conn === "live")
App.tsx:997            disabled={archived || requiresResume || conn !== "live" && Boolean(active)}
RunStatus.tsx:18       const connected = conn === "live";
```

Three expressions, one boolean, two of them disagreeing (F7: the main composer allows typing on the
home screen while the dock does not, by accident of operator precedence). A rule with three
implementations is not a rule.

---

## First principles

What is irreducible here? Six statements, each of which can be checked against the code, and each of
which decides a whole class of behaviour.

### P1 · The stream is an output channel, not the input permission

The app's own architecture says this already. From `useSessionStream`'s header and spec 010: the
server owns the turn, the journal is durable, the client can disconnect and catch up. A send is an
HTTP `POST` with an `Idempotency-Key`; it does not travel over the `EventSource`.

> Therefore: `conn` may gate *what you are told*, never *what you may ask*. Gating the composer on
> `conn` contradicts the durability the rest of the system exists to provide.

**Consequence.** The composer is enabled whenever the session is writable (not archived, not
requires-resume). A send while reconnecting is queued-or-fails-with-a-reason, both of which are
honest. A disabled box is neither.

### P2 · Every persistent state needs a named exit

A state is *persistent* if the app cannot leave it on its own. `reconnecting` is persistent after a
refused stream (F2). A persistent state that looks transitional is the worst of both: the user waits
for something that is not coming, and the controls that would help are disabled by the same flag.

> Therefore: every non-`live` connection state renders one **action**, next to the word that
> announces it, and that action is the same control the app would use internally (re-open the
> stream).

### P3 · A control that cannot act must say why, in place

The `disabled` attribute is invisible. The composer in the screenshot looks available: same border,
same placeholder, same model chip. There is no `:disabled` styling on `.composer-box` at all (F6). A
user reasons from what they see, and what they see is an invitation.

> Therefore: a non-writable composer carries a **visible** state — a tinted box, a stated reason
> inside the placeholder position, and `aria-disabled` rather than `disabled` where the field must
> stay focusable so the reason can be read.

This is the subtle half of the fix. `disabled` removes the element from the tab order *and* from the
accessibility tree's focus, so a screen-reader user cannot even discover why. `readOnly` +
`aria-disabled` keeps it reachable and explainable.

### P4 · One question, one owner

"Can this composer accept a send?" is a single question. It must be one pure function over the
session and the connection, called by every composer, so the dock and the main screen cannot
disagree (F7).

> Therefore: `canSend(session, conn)` in `domain/`, with the whole truth table tested, and no call
> site re-deriving it.

### P5 · Escape has one meaning, and it is ordered

`escapeTarget()` already encodes the intended precedence — `dialog → popover → drawer → edit →
stop-agent → nothing` — and is called by nobody (F4). The real precedence is a chain of `if`s in a
React `useMemo` that re-creates the handler whenever its dependencies change, which is a second
reason it drifts: the handler's dependencies include `drawer`, `dockDrawer`, `inspectorDrawer`,
`narrow`, `mode`, `layout` — so the Escape behaviour is a function of the layout, which nobody would
predict.

> Therefore: one call site calls `escapeTarget()`, and the handler reads its answer. The pure
> function becomes load-bearing instead of decorative.

### P6 · Scroll belongs to the thing under the pointer, and stops at its edge

Three nested scrollers is correct — a cell's output must scroll without the notebook scrolling. Three
nested `overscroll-behavior: contain` is also correct, and it is what stops a trackpad flick from
hurling the whole page.

But the *combination* creates a trap: at the end of a cell's output, a wheel does nothing (F8). The
user must move the pointer to the notebook to continue. The fix is not to remove `contain` — that
would restore the original bug the rule was written for — it is to make the **contained edge hand
off**: when the inner scroller is at its end and the wheel continues in the same direction, the
outer scroller takes the remainder.

> Therefore: one delegated `wheel` handler implementing hand-off, and `contain` kept everywhere else.

---

## What this rules out

Stated because each was a plausible first instinct:

| Rejected | Why |
|---|---|
| Make `conn === "live" \|\| conn === "connecting"` | Treats the symptom. `reconnecting` is still terminal (F2). |
| Add a "Reconnect" button next to the pill | Necessary but not sufficient: the composer stays disabled, so the user still cannot write down what they wanted. Fixes F3, not F1. |
| Auto-retry the stream on a timer | Right thing, wrong scope: a 404 (deleted session) will never succeed. Retry must be *bounded and explained*, and a manual control must exist for the case where the bound is reached. |
| Remove `disabled` and let send fail | Closer, but a silent failure on send is worse than a stated refusal up front. The state must be visible (P3). |
| Make `.composer-box` look disabled and leave the logic | Cosmetic. The user's actual loss is the *content* they were about to write. |

## The irreducible design

```
      ┌─────────────────────── what the user sees ───────────────────────┐
      │  a box that accepts text, or a box that says why it cannot       │
      └──────────────────────────────┬──────────────────────────────────┘
                                     │  derived by ONE pure function
      ┌──────────────────────────────▼──────────────────────────────────┐
      │  writable = not archived ∧ not requires-resume                   │
      │  reachable = live ∨ (reconnecting ∧ will-retry)                  │
      │  canSend   = writable ∧ (draft non-empty)                        │
      └──────────────────────────────┬──────────────────────────────────┘
                                     │  the connection may never remove
                                     │  the ability to ASK, only to be TOLD
      ┌──────────────────────────────▼──────────────────────────────────┐
      │  stream state machine: idle → connecting → live ⇄ reconnecting   │
      │                       any → closed (with a stated reason)        │
      └─────────────────────────────────────────────────────────────────┘
```
