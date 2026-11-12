# 012 — Focus, input, scroll and state

**Status:** assessment + implementation plan, then implementation. This folder is the record.
**Scope:** how the keyboard, the pointer, the scroll wheel and the URL behave in each of the three
zones — and the *state machine* that decides whether a field accepts input at all. Not the agent, not
the notebook model, not the Databricks deployment. Those are 001, 007 and 017/021, cited not restated.

**The report this starts from.**

> "I cannot focus on the right panel to edit and ask a new command."

That is a bug report with no mechanism in it, so the first job was to find the mechanism. It is not a
`tabIndex`, and it is not a missing `focus()` call.

---

## What this folder is

| # | Document | Answers |
|---|---|---|
| 01 | [Five whys and first principles](01-five-whys.md) | Why does this happen at all, and what is irreducible? |
| 02 | [Measured assessment](02-assessment.md) | What is actually wrong, with the probe output and the file:line |
| 03 | [Requirements](03-requirements.md) | What must be true when it is done (`FX-*`, `ST-*`, `SC-*`, `LK-*`) |
| 04 | [Wireframes (ASCII)](04-wireframes.md) | Every zone, every state, every recovery path |
| 05 | [Diagrams (Mermaid)](05-diagrams.md) | Sequence, state and E/R: the contradictions drawn out |
| 06 | [Lenses](06-lenses.md) | The same system seen by six owners |
| 07 | [Architecture](07-architecture.md) | Where each rule lives, and why there |
| 08 | [Implementation plan](08-implementation-plan.md) | Phases, files, tests, order |
| 09 | [Edge cases](09-edge-cases.md) | Every failure I could name, its mitigation, its test |
| 10 | [E2E plan](10-e2e-plan.md) | Scenes, screenshots, pass criteria |
| 11 | [Outcome](11-outcome.md) | What shipped, and what the screenshots found |
| — | [E2E screenshots](e2e/screenshots/README.md) | What it actually looks like, each one inspected |

Cross-references: a requirement is `[FX-3]`, a decision `[D7]`, an edge case `[E-12]`, a scene `[S4]`.
Each id is defined once, in `03` or `09`, and cited everywhere else. A citation that is not in `03`
or `09` is a bug in this document set.

Builds on:
[007 the shell, keys and scroll](../007-ux-ui-improve/README.md) (the zone model, `resolve`, the
separator contract) and [010 long-running](../010-long-running/README.md) (durable sessions, the
return link). It does not replace either; it finds where the two disagree.

---

## The one sentence

> A field the user can see, and is invited to type into, must accept a keystroke — or say in one
> line why it cannot and offer the one action that fixes it.

The app currently satisfies neither half in the state the screenshot captured. The composer is
visible, styled as available, focusable-by-look and **unfocusable-by-fact**; the reason ("reconnecting")
is a passive word with no action attached; and nothing on screen names a way out.

## The finding, in one table

| # | Finding | Evidence | Kind |
|---|---|---|---|
| **F1** | Any connection state other than `live` **disables** the message box. `connecting` on every load, and `reconnecting…` indefinitely after a refused reconnect. A disabled textarea cannot receive focus. | probe: `everDisabled=true`; `canType=false` | **defect** |
| **F2** | A refused stream (404 deleted session, 409 cursor ahead) never re-opens. The only retries are `visibilitychange` and `online`. So `reconnecting…` is a terminal state that *renders as a transitional one*. | `useSessionStream.ts:163,178-180` | **defect** |
| **F3** | Four controls are gated on `conn === "live"`: the composer, Restore agent, Stop work, and the approval buttons. None of them says so, and none offers a manual retry. | `AssistantDock.tsx:90`, `RunStatus.tsx:40,44`, `App.tsx:993` | **defect** |
| **F4** | `escapeTarget()` — the documented single meaning of Escape — is **never called**. It is exported, tested, documented, and dead. The real precedence is a chain of `if`s inside the `stop` handler. | `rg escapeTarget` → only `keys.test.ts` | **incoherence** |
| **F5** | ~~`Escape` is declared `owner: "composer"`, so `resolve()` returns `null` unless the composer has focus.~~ **This claim was wrong, and measuring it is part of the record.** `resolve({key:"Escape"}, {cell:true})` returns the row, because the notebook-scoping branch at `keys.ts:236` only rejects rows whose owner IS `"notebook"`; a `composer` row falls through to `shellRow`. Measured in the browser at 820 px: with the rail open as a drawer and focus on `main`, Escape closes it. So the handler is reachable from most places. | `esc-probe2.mjs`: drawer closed, focus kept on `MAIN` | **claim withdrawn** |
| **F6** | The composer's `disabled` state has no visible affordance beyond a native `disabled` attribute: the box looks identical, the placeholder still says "Ask anything…", and the focus ring simply never appears. | probe: `composerRing` unchanged; styles.css has no `:disabled` rule for `.composer-box` | **UX gap** |
| **F7** | The main-screen composer is disabled by a *different* expression than the dock's (`…|| conn !== "live" && Boolean(active)`), so the two boxes disagree about the same session. Operator precedence makes it `(!== "live" && active)`, which is right by accident. | `App.tsx:997` vs `AssistantDock.tsx:90` | **incoherence** |
| **F8** | Scroll: three nested scrollers (`.dock-body`, `.cell-output`, `.transcript`), each with `overscroll-behavior: contain`. A wheel at the end of a cell's output cannot scroll the notebook. The user must move the pointer. | `styles.css:365,399,432` | **UX gap** |

F1 is the reported bug. F2 is why it is permanent rather than momentary. F3 is why the user cannot get
out. F7 is the same bug written twice, which is the architectural finding: **"can I type" is computed
in three places from one boolean, and none of them is the owner of the question.**

F4 stands and is the subtler one: `escapeTarget()` — the documented, tested, ordered meaning of
Escape — is exported, cited by a comment that claims the shell uses it, and **called only from its own
tests**. The behaviour that exists is a chain of `if`s inside a `useMemo` whose dependency list
includes `layout`, `mode` and `narrow`, so Escape's precedence is a function of window width. It works;
it works for reasons nobody designed, and the function that says what it should do is decoration.

Five of the eight findings are defects. One (F5) was a **wrong claim** — measured, found false, and
withdrawn in place rather than edited away, because a spec that hides a mistake is not a record.

## The two principles this rests on

1. **A connection state is not an input permission.** Losing the stream means "the answer will not
   arrive yet", not "you may not ask". A refused stream and a slow one are the same state to a user,
   and both are recoverable — so the field stays live and the *send* carries the consequence. This is
   what every durable-session product does, and this app is one: the server runs independently, the
   turn survives, and the request is idempotent (`Idempotency-Key`, spec 010).
2. **A state that can persist needs a stated action.** `reconnecting…` with no button is a dead end
   dressed as a transition. Every non-live state must name its exit, in the same place it is
   announced.

Everything below is an argument about those two sentences.
