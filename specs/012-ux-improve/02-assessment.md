[Index](README.md) · prev: [01 Five whys](01-five-whys.md) · next: [03 Requirements](03-requirements.md)

# 02 · Measured assessment

Every number here comes from a probe against a running app on `http://127.0.0.1:8062`, viewport
1480×900, headless Chromium. The probes are committed so each claim can be re-run:

| Probe | Measures |
|---|---|
| [`scripts/focus-probe.mjs`](../../apps/coding-agent/web/scripts/focus-probe.mjs) | zone geometry, focus reachability, tab order, Escape |
| [`scripts/focus-repro.mjs`](../../apps/coding-agent/web/scripts/focus-repro.mjs) | the disabled window, offline/online, recovery affordances |
| [`scripts/deadend-probe.mjs`](../../apps/coding-agent/web/scripts/deadend-probe.mjs) | the terminal `reconnecting` state |
| [`scripts/state-probe.mjs`](../../apps/coding-agent/web/scripts/state-probe.mjs) | hard refresh, deeplinks, stale links |

---

## 1. What is healthy (so the fix does not break it)

Measured first, because most of this system is correct and the correction has to be surgical.

| Check | Result |
|---|---|
| Zone geometry at 1480 px | rail 276 · main 822 · dock 380, no overflow, document exactly viewport-tall (`sh=ch=900`) |
| Layout width survives a hard refresh | `railWidth 320` restored |
| Selected rail tab survives a hard refresh | `Files` restored |
| A settings deeplink opens on a cold load | `#/settings/providers` → dialog open, heading "Providers and keys" |
| A **stale** session link still renders the app | shell present, dock present, no blank page |
| Back after closing a dialog | no loop |
| `route.ts` `parse(format(r))` round-trip | covered by `domain/route.ts` tests |
| The composer accepts typing when the stream is live | `value="can i type?"`, `activeElement=TEXTAREA` |
| Focus ring is defined for every interactive element | `:focus-visible` at `styles.css:192` and ~20 specific rules |

The one thing this **rules in**: the state and deeplink layer is not where the defect lives. F8 (scroll
hand-off) is the only finding that touches layout, and it is a gap rather than a bug.

## 2. The defect, in a timeline

Probe `focus-repro.mjs`, sampling the composer every 200 ms after opening a session:

```
t= 704 ms   disabled=true    pill="idle"       ← the page is interactive and looks ready
t= 909 ms   disabled=false   pill=null         ← the stream opened
```

**A 205 ms window in which the app invites a keystroke and discards it.** On a cold Databricks Apps
container this is far longer: the `EventSource` has to reach a cold FastAPI process. It is not a
theoretical race — it is the first two seconds of every visit, and the screenshot's user was still in
that window when they tried to type.

Then the terminal case, probe `deadend-probe.mjs`:

```
healthy:       pill=null              textareaDisabled=false   runStatusButtons=[Copy return link]
DELETE /api/sessions/<id> → 204
afterBreak:    pill=null              textareaDisabled=true    canType=false
               dockText="archived in context: nothing open"
               recoveryControls=[]        ← nothing anywhere on the page
               runStatusButtons=[Copy return link]   ← the only enabled control
```

Two findings in three lines:

1. `textareaDisabled=true` **and** `canType=false`: the field is gone from the keyboard entirely.
2. `recoveryControls=[]`: there is no control on the page whose name suggests recovery. "Copy return
   link" is enabled, which is the app telling a user to leave.

The stream state is not even reported as broken once the session is marked archived — the pill
disappears, so the screen says "archived" and offers no way to a new conversation from the composer
itself. The `New conversation` button in the dock header *is* reachable (`newSessionReachable:
{present:true, disabled:false}`), which is the one genuine escape hatch — and it is an unlabelled
icon, not part of the stated reason.

## 3. The mechanism, proven

A `disabled` form control cannot take focus. Measured directly, in the page:

```js
const ta = document.createElement("textarea");
ta.disabled = true; document.body.appendChild(ta); ta.focus();
document.activeElement === ta   // false
```

So "I cannot focus the right panel" is the *correct* browser behaviour for the markup the app
produces. There is no `tabIndex` bug and no missing `focus()` call. The bug is upstream: **a state
that should not disable a field is wired into `disabled`.**

## 4. Offline is a different bug with the same cause

```
offline      → pill="lost"     disabled=true
back online  → pill=null       disabled=false   value preserved
```

The offline path recovers (`online` → `open()`), so a laptop lid is fine. The point is that the same
`disabled` mechanism fires for a state the app *knows* is transient. Two states, one flag, no
distinction — which is F1's root: **connection state and input permission were never separated.**

## 5. The dead abstraction

`escapeTarget()` is the documented, tested, single meaning of Escape:

```258:272:apps/coding-agent/web/src/domain/keys.ts
export type EscapeTarget =
  | "dialog" | "popover" | "drawer" | "edit" | "stop-agent" | "nothing";

export function escapeTarget(ctx: {...}): EscapeTarget {
  if (ctx.dialog) return "dialog";
  ...
  if (ctx.running && ctx.composerFocused) return "stop-agent";
  return "nothing";
}
```

`rg escapeTarget` finds **three** call sites, all in `keys.test.ts`:

```
domain/keys.test.ts:104  import { …, escapeTarget, … }
domain/keys.test.ts:168  describe("escapeTarget: one ordered meaning (KB-8)", …)
hooks/useHotkeys.ts:44   // a COMMENT: "or the shell's ordered `escapeTarget`"
```

The comment in `useHotkeys` says the shell uses it. The shell does not. The real precedence is:

```658:672:apps/coding-agent/web/src/App.tsx
      stop: () => {
        if (settingsOpen) { setSettingsOpen(false); return true; }
        if (paletteOpen || keysOpen) { setPaletteOpen(false); setKeysOpen(false); return true; }
        if (dockDrawer) { setDockDrawer(false); toggle("assistant", false); return true; }
        if (inspectorDrawer) { toggle("inspector", false); return true; }
        if (drawer) { setDrawer(null); toggle("rail", false); return true; }
        return false;
      },
```

A second, smaller contradiction: this handler is reachable only when `resolve()` returns the `stop`
shortcut, and `stop` is declared `owner: "composer"` (`keys.ts:135`), so the notebook-scoping branch
at `keys.ts:236` returns `null` unless focus is inside the dock. **Escape cannot close the rail
drawer from the notebook.** The handler that would do it is guarded by a condition that excludes the
very situation it is written for.

This is the clearest instance of the pattern behind all of it: **the model says one thing, the
wiring does another, and both are tested — separately.** The pure tests pass, the app misbehaves,
because nothing asserts that the pure answer is the one used.

## 6. The same question, answered three ways

| Question | Call site | Expression |
|---|---|---|
| May the dock composer take text? | `AssistantDock.tsx:90` | `status !== "archived" && !requiresResume && (!hasSession \|\| conn === "live")` |
| May the main composer take text? | `App.tsx:997` | `status === "archived" \|\| requiresResume \|\| conn !== "live" && Boolean(active)` |
| May Restore/Stop be pressed? | `RunStatus.tsx:18,40,44` | `connected = conn === "live"`, then `disabled={pending \|\| !connected}` |
| May an approval be decided? | `App.tsx:993` | `disabled={conn !== "live"}` |

`App.tsx:997` has no parentheses around `conn !== "live" && Boolean(active)`, so `&&` binds tighter
than `||` and the effective rule is *"disable if archived, or requires-resume, or (offline AND a
session is open)"*. On the home screen (`active === null`) the main composer is therefore **enabled
while the dock's is not** — the same session, the same connection, two answers. It happens to be the
behaviour we want (P1), and it is right by accident, which is worse than being wrong: a later reader
"fixing" the precedence would silently disable typing on the home screen too.

## 7. Scroll: the nested-scroller trap

```
.cell-output   { overflow: auto; overscroll-behavior: contain; max-height: 220px }   styles.css:432
.transcript    { overflow: auto; overscroll-behavior: contain }                      styles.css:399
.dock-body     { overflow: auto; overscroll-behavior: contain }                      styles.css:365
```

Each rule is individually correct and commented as such — they were written to stop a trackpad flick
chaining outward (007 SC-3). The composition is the problem: a wheel over a cell's output stops dead
at its 220 px edge. The user's hand says "keep going", the screen does nothing, and the only recourse
is to move the pointer into the notebook and wheel again. At 1480 px with a dock open, that is a
~380 px pointer travel to continue reading.

## 8. Summary, by severity

| Severity | Finding | User-visible consequence |
|---|---|---|
| **Blocker** | F1 — `conn` disables the composer | the reported bug; unrecoverable while it lasts |
| **Blocker** | F2 — no recovery from a refused stream | "reconnecting…" forever; the app is stuck |
| **High** | F3 — every recovery control shares the dead flag | nothing on screen can fix it |
| **High** | F7 — two composers, two rules | inconsistent, and right only by precedence accident |
| **Medium** | F6 — invisible disabled state | the invitation and the refusal look identical |
| **Medium** | F4/F5 — `escapeTarget` dead; Escape scoped to the composer | the designed escape hatch does not exist |
| **Low** | F8 — no scroll hand-off | pointer travel to keep reading |
