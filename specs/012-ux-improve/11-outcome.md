[Index](README.md) · prev: [10 E2E plan](10-e2e-plan.md)

# 11 · Outcome

What shipped, what the screenshots found, and what remains open. Written last, from the running app,
not from the plan.

---

## The report, and what it actually was

> "I cannot focus on the right panel to edit and ask a new command."

It was not a `tabIndex`, and not a missing `focus()` call. Any connection state other than `live`
reached a `disabled` attribute on the `<textarea>`, and **a disabled form control is not focusable in
any browser** — proven directly, then proven in the app:

| Probe | Before | After |
|---|---|---|
| `typeof textarea.disabled` after a refused stream | `true` | `false` |
| can the field take focus (`document.activeElement === ta`) | `false` | **`true`** |
| keystrokes typed during `connecting` | lost | **kept** |
| recovery controls on the page while `closed` | `[]` | **Retry, New conversation** |

The `disabled` window existed on **every page load** for ~205 ms (measured `t=704 disabled=true` →
`t=909 disabled=false`), and permanently whenever the stream was refused — which a routine reaper
sweep produces.

---

## What was built

| File | Change | Why |
|---|---|---|
| `domain/compose.ts` | **new** | one answer to "may this be sent"; `conn` not in the type at all |
| `domain/stream.ts` | **new** | the state machine the hook was missing: `reconnecting` ≠ `closed`, bounded backoff |
| `domain/scroll.ts` | **new** | hand-off arithmetic, three wheel units normalised |
| `hooks/useScrollHandoff.ts` | **new** | one delegated wheel listener implementing hand-off |
| `components/StreamNotice.tsx` | **new** | the one place a non-live state becomes a word **and** an action |
| `components/Composer.tsx` | edited | `readOnly` + `aria-disabled` + a described reason; never `disabled` |
| `components/AssistantDock.tsx` | edited | calls `canSend`; the pass pill replaced by `StreamNotice` |
| `components/RunStatus.tsx` | edited | `canRestore` / `canStop`; never gate on `conn` |
| `hooks/useSessionStream.ts` | edited | the state machine, a status probe on failure, bounded retry, `retry()` |
| `domain/mission.ts` | edited | reads `StreamState`; the connection branch defers to `StreamNotice` |
| `App.tsx` | edited | four re-derivations deleted; `escapeTarget()` wired; the wheel hook mounted |

**The diff is mostly deletion.** Four expressions that answered one question, one chain of five `if`s,
a passive pill, and a `disabled` attribute — replaced by three pure modules and one notice component.

---

## The five defects the screenshots found

Every one of these was invisible in review and obvious in a picture.

| # | Found in | Defect | Fix |
|---|---|---|---|
| 1 | `s5-closed` (1st look) | The reason showed **twice**: in the placeholder and in a visible paragraph under it | the paragraph is now the `aria-describedby` target only (visually hidden) |
| 2 | `s5-closed` (2nd look) | The same fact stated **four times**: centre banner, header chip, run-status box, composer | one notice; the raw `no such session` line suppressed when the notice already names the fault |
| 3 | `s5-closed` (3rd look) | The notice was a **66 px chip inside a 40 px header** — it overflowed upward and read as a floating toast | the notice moved to the dock body, where the word and both actions fit |
| 4 | `s5-closed` (4th look) | The header **truncated the state word** when the notice carried two actions | same fix; the header's `height` became `min-height` |
| 5 | my own scene | Three scenes measured `null` because they intercepted the stream *after* the app had connected | scenes use an unopened session; the real 404 condition documented |

Defect 3 is the instructive one: the markup was correct, the assertions passed, and the **box could
not fit its container**. Only a picture shows that.

## Two claims withdrawn or corrected

Recorded because a spec that edits away its own mistakes is not a record.

| Claim | What happened |
|---|---|
| **F5** — "Escape cannot reach the shell from a cell, because `stop` is owned by the composer" | **Wrong.** `resolve({key:"Escape"}, {cell:true})` returns the row: the notebook branch only rejects `owner: "notebook"` rows. Measured in the browser: Escape closes the rail drawer from `main`. Withdrawn in [README](README.md). |
| **A single `canAct`** for Restore, Stop and approvals | **Wrong.** It reused `blockedReason`, so it disabled "Restore agent" exactly when `requiresResume` was true — the only condition Restore exists for. `RunStatus.test.tsx` caught it. Replaced with one predicate per control ([compose.ts](../../apps/coding-agent/web/src/domain/compose.ts)). |
| The `closed` state renders a `readOnly` composer | **Wrong for that state.** A closed *stream* is not a closed *session*: the box stays writable, which is the whole point of [P1]. `readOnly` belongs to an *archived* session. The scene asserted the wrong thing and was corrected, not the code. |

The last one matters most: it is the same conflation the original defect made, arriving from the
opposite direction. Checking `s5` against the design intent — not against my memory of writing it —
is what caught it.

---

## Verification

| Gate | Result |
|---|---|
| `tsc -b --noEmit` | clean |
| `vitest run` | **655 passed, 0 failed** (53 new pure tests + 3 new suites) |
| `pytest` (backend) | **643 passed, 7 skipped** |
| `ux-scenes.mjs` | **7/7 scenes pass**, screenshots in [`e2e/screenshots/`](e2e/screenshots/) |
| `deadend-probe.mjs` | `canType: true`, `textareaDisabled: false` (was `false`/`true` before) |
| `state-probe.mjs` | deeplinks and layout persistence still pass |
| `prepare-app.sh` (the Databricks build) | runs; now warns by name when Node is too old |

## The toolchain defect found on the way

`npm run build` failed with `Cannot find module '@rolldown/binding-darwin-arm64'` on Node 20.14. The
cause is not that package: the rolldown native binding declares `node ^20.19 || >=22.12`, and **npm
silently skips an optional dependency whose `engines` is unmet**. So the install reported success and
the build died naming the wrong module.

Fixed in three places, each for a different reader: `web/.npmrc` (`include=optional`, so the binary
installs), `scripts/prepare-app.sh` (names the cause instead of letting the build fail cryptically),
and a comment recording why `engines` is *not* in `package.json` — declaring it there would fail
`npm ci` on the platform and break the **deployment** to warn a developer.

---

## Still open, honestly

| Item | Why it is not closed |
|---|---|
| A real turn through Gemini in the deployed dev app | needs a signed-in browser session; the model itself is proven reachable (deploy spec 021) |
| Scroll hand-off with a real trackpad | the hook is unit-tested and S8 drives a real synthetic `WheelEvent` through it; a trackpad's moment-to-moment feel is a human judgement |
| The dock's model selector vs the topbar chip | deliberate (global default vs session model) and already guarded — only the visible control answers ⌘⇧M — but a first-time user sees the same value twice. A design question, not a defect. |
| `RunStatus`' "Temporary history" note | correct for the fake agent; the deployed app is `durable` and shows "Progress saved" |

## The one sentence, re-checked

> A field the user can see, and is invited to type into, must accept a keystroke — or say in one line
> why it cannot and offer the one action that fixes it.

The app now does both. The field accepts a keystroke in every connection state; when the *session*
genuinely cannot be written to, the box is `readOnly`, visually distinct, and states its reason in the
same sentence to both a sighted user and a screen reader; and every connection fault names itself and
carries its own exit.
