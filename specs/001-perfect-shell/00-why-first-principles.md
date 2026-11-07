# 00 · Why, from first principles

[Index](README.md) · next: [01 Shell audit](01-shell-audit.md)

## The five whys

The chain starts from the observation that decides whether this product succeeds, and drills to a
cause that can be *changed* rather than merely described.

**Observation.** A person uses this app for forty minutes, several times a day, to do real work in a
Databricks workspace. They could use a CLI, a notebook, or Genie Code instead.

---
**Why 1 — Why do they stay, or leave?**
Because the app either gets out of their way or it does not. The functionality is comparable: any
competent agent can write a notebook. What differs is how many small frictions sit between an
intention and its result.

**Why 2 — Why do small frictions decide it?**

Because they are not small when multiplied. A three-second wait, a panel that will not widen so you
can read a wide table, a tab that scrolls off screen, a layout that resets every reload: each costs
seconds; together they cost the habit. A tool people use forty minutes a day is judged per week, not
per interaction.

**Why 3 — Why do these frictions exist here?**

Because the shell was built feature-first, to demonstrate capabilities, not usage-first, to serve
repetition. Each capability landed where it was convenient: the layout columns are a fixed
`grid-template-columns` literal, panel visibility is a boolean in React state, the tab strip is
`overflow-x: auto` with nothing managing it. Each is individually defensible and collectively a
ceiling.

**Why 4 — Why was feature-first the wrong order here?**

Because the shell is the only part of the product that is on screen 100% of the time. The agent is
episodic; the frame is constant. An agent that is 5% slower is invisible; a frame that steals 5% of
the window on every glance is felt continuously. Optimising the episodic part while leaving the
constant part fixed is optimising the wrong denominator.

**Why 5 — Why does that framing point at a specific fix?**

Because if the frame is the product, then the frame's *state* is the feature. Resizable, remembered,
restorable, honest about progress, stable under load. That is not decoration: it is the difference
between a demo and a tool. It is also, precisely and measurably, what this shell does not yet do
([01](01-shell-audit.md)).

---

## First principles

Six axioms, each of which can be falsified by a measurement in the audit.

### A1 · The frame is the product's constant; the work is its variable

Every pixel and every millisecond spent on the frame is paid on *every* interaction; the same spent on
a one-off capability is paid once. Therefore the frame's cost budget is stricter, not looser.

**Test of the axiom:** if the shell is on screen during 100% of a session and the agent's own latency
is 4–60 s per turn, then the shell's responsiveness must be measured in milliseconds and the agent's
in seconds. Both are in the audit.

### A2 · Space is a resource the user allocates, not the designer

A user reading a wide results table needs more centre column; a user auditing a session needs more
inspector. There is no correct answer, only the user's answer, changing by task. A fixed column is
therefore always wrong for someone.

**Consequence:** any zone whose width is a constant in code is a defect, not a default.

### A3 · State that is not remembered is state the user re-creates

A layout that resets on reload charges the user a setup tax on every visit. The tax is small and
constant, which is the worst kind: never big enough to complain about, always there.

**Consequence:** panel widths, visibility, active zone and open tab must survive a reload. Not
"should" — must, because the alternative is a tax with no ceiling on repetitions.

### A4 · Feedback must be proportional to the wait it describes

A 300 ms operation needs no narrative. A 4 s operation needs progress; a 30 s one needs progress,
an estimate, and a cancel. Showing the same "searching…" for 0.3 s and 4.3 s is misinformation by
omission.

**Measured:** workspace search takes **4.1–4.3 s** on this workspace and shows one static word.
([01 §F](01-shell-audit.md))

### A5 · A frame that moves under the reader is a frame that loses the reader

If content reflows while someone is reading it, they lose their place — the cost is re-acquisition,
not just annoyance. So: the composer must not jump when a turn starts; the transcript must not
re-wrap when a panel opens; the tab strip must not shift the content when a tab is added.

**Consequence:** layout changes are explicit (a resize, a toggle) and otherwise the frame is stable.

### A6 · Every hidden thing must be one action from returning, by keyboard

Hiding a panel is a power feature only if it is reversible without hunting. A drawer that opens on
top of the thing you were reading; a collapse whose restore control moved; a mode with no exit —
each turns a feature into a trap.

**Consequence:** every zone has (a) a keyboard toggle, (b) a visible control, (c) a restore affordance
that exists exactly when the zone is hidden, and (d) the same key that hid it brings it back.

---

## What follows, stated as the design's purpose

> The shell exists to give the work as much room as the work needs, while remaining the same shell
> every time the user returns — and to say honestly how long anything is taking.

That single sentence generates every requirement in [02](02-requirements.md):

| Axiom | Requirement |
|---|---|
| A1 | Frame interactions ≤ 100 ms; no frame work in the streaming path |
| A2 | Rail and inspector are resizable within bounds |
| A3 | Widths, visibility, active zone and open tab persist across reload and restart |
| A4 | Search shows progress and can be cancelled after 400 ms |
| A5 | Composer does not jump; transcript does not re-wrap on toggle |
| A6 | Every zone toggles by key and by control, and restores by both |

## What this spec deliberately does not do

- **No visual redesign.** The palette, type scale and spacing already pass an accessibility audit with
  zero findings ([001/20](../001-databricks-coding-agents/20-accessibility.md)). Changing tokens now
  would buy nothing and risk regressions.
- **No new zones.** There is no fourth panel coming. The value is in making the existing three behave.
- **No framework change.** The shell is React 19 with a hand-written grid; that is sufficient, and a
  rewrite would trade a measured problem for an unmeasured one.
