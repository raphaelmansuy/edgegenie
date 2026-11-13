[Index](README.md) · prev: [09 Edge cases](09-edge-cases.md) · next: [11 Outcome](11-outcome.md)

# 10 · E2E plan

Each scene is a browser scenario against a running app, with screenshots saved to
`specs/012-ux-improve/e2e/screenshots/`. Every screenshot is inspected before it is accepted: a scene
that "passes" while the picture shows a dead field is a failed scene.

Viewports: **1480** (three columns), **1180** (mid — panels are overlays), **820** (narrow — both are
overlays). Themes: light, and dark for one scene.

---

## Scenes

| Id | Scene | What it proves | Files |
|---|---|---|---|
| **S1** | The healthy shell, all three zones | geometry, no overflow, tab order | `s1-shell-1480-{light,dark}.png`, `s1-shell-820.png` |
| **S2** | Type during `connecting` | [FX-1]: the first keystroke is kept | `s2-connecting-1480.png` |
| **S3** | **The reported bug, before** | the defect, recorded | `s3-before-dead-composer.png` |
| **S4** | `reconnecting`: word + action + live box | [ST-4], [ST-6] | `s4-reconnecting-1480.png` |
| **S5** | `closed`: stated reason + two actions | [ST-4], [FX-2], [FX-3] | `s5-closed-1480.png` |
| **S6** | Escape closes the drawer from a cell | [KB-B], [FX-7], [SC-5] | `s6-escape-820.png` |
| **S7** | Hard refresh + cell deeplink | [LK-1], [LK-3] | `s7-deeplink-cell3.png` |
| **S8** | Wheel hand-off at a cell's edge | [SC-1] | `s8-scroll-handoff.png` |

---

## S1 · The healthy shell

```
  arrange   open the app at 1480×900, a session with one turn
  assert    rail 276 ±1 · main > 480 · dock 380 ±1
            document.scrollingElement.scrollHeight === clientHeight  (no page scroll)
            Tab from the top: chrome → rail → main → dock, each zone reached
  shoot     s1-shell-1480-light.png, s1-shell-1480-dark.png, s1-shell-820.png
  inspect   the composer's focus ring is visible and the box looks writable
```

## S2 · Type during `connecting`

The scene must *hold* the connection at `connecting`, or it tests nothing. Implemented by routing
`/api/sessions/*/stream` to a delayed response.

```
  arrange   intercept the stream, delay the response 1500 ms
  act       load the session, immediately type "chart the trips"
  assert    the textarea value is "chart the trips"            ← the whole point
            the textarea is document.activeElement
  shoot     s2-connecting-1480.png                              ← shows text in the box
  before    this scene failed: value === "" and activeElement === BODY
```

## S3 · The reported bug, before

Recorded so the fix has a "before" that is a picture, not a memory.

```
  arrange   create a session, DELETE it, switch tabs to force a reconnect
  assert    textarea.disabled === true
            textarea cannot take focus
            no control on the page offers recovery
  shoot     s3-before-dead-composer.png
```

This is the screenshot that matches the user's report. It is kept in the folder deliberately: a spec
that removed its own evidence is a claim, not a record.

## S4 · `reconnecting`

```
  arrange   intercept the stream → 503, let the retry fail twice
  assert    the notice reads "reconnecting…"
            a "Retry now" control exists and is focusable       [ST-5]
            the composer is writable and accepts text            [FX-1]
            typing survives the failed retry                     [ST-6]
  shoot     s4-reconnecting-1480.png
  inspect   the box visibly accepts text; the action is beside the word, not elsewhere
```

## S5 · `closed`

```
  arrange   intercept the stream → 404
  assert    the notice reads "session closed" with a specific reason
            two actions: Retry, New conversation
            the composer is readOnly, focusable, and aria-describedby points at the reason
            role="alert" on the notice                          [ST-7]
  shoot     s5-closed-1480.png
  inspect   the box looks distinct from a writable one ([FX-3]) and the reason is readable
```

## S6 · Escape, at 820 px

```
  arrange   viewport 820 (both panels are drawers), open the rail drawer, focus a cell
  act       Escape
  assert    the drawer is closed
            focus is back inside the notebook                   [FX-7]
            document.scrollingElement.scrollTop === 0           [SC-5]
  shoot     s6-escape-820.png
```

## S7 · Hard refresh and a cell deeplink

```
  arrange   copy the link to cell 3 of a notebook
  act       hard navigate to that URL in a fresh context
  assert    the notebook is open, cell 3 is focused and in view
            the rail width and tab are the stored ones          [LK-3]
            a second hard refresh gives the same screen
  shoot     s7-deeplink-cell3.png
```

## S8 · Wheel hand-off

```
  arrange   a cell whose output is taller than 220 px, scrolled to its bottom
  act       wheel down 400 px over the output
  assert    the notebook scrolled by ~400 − (output's remaining)   [SC-1]
            the cell output did not scroll further
  shoot     s8-scroll-handoff.png
```

---

## How a screenshot is accepted

A picture is accepted only if all four hold. This is written down because "it looked fine" is how the
original bug shipped.

1. **It answers its scene's question.** S5 must show a box that *looks* closed and *says* why. If the
   only difference from S1 is a word in the header, the scene failed.
2. **Nothing is clipped.** No control at the edge of a panel, no text under a separator, no horizontal
   scrollbar.
3. **The focus ring is where the scene says it is.** A screenshot of a focus state with no visible
   ring is a screenshot of nothing.
4. **The state is legible without the caption.** Someone who has not read this document can tell
   "this is closed" from "this is reconnecting" from "this is ready".

---

## Commands

```bash
cd apps/coding-agent/web
node scripts/focus-probe.mjs   http://127.0.0.1:8062   # the measurements in 02
node scripts/deadend-probe.mjs http://127.0.0.1:8062   # the terminal state
node scripts/state-probe.mjs   http://127.0.0.1:8062   # refresh and deeplinks
node scripts/ux-scenes.mjs     http://127.0.0.1:8062   # S1–S8, writes the screenshots
```
