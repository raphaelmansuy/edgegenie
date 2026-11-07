# 02 · Requirements

[Index](README.md) · prev: [01 Current state audit](01-current-state-audit.md) · next: [03 Architecture](03-architecture.md)

Every requirement traces to an axiom in [00](00-why-first-principles.md) and to a finding in
[01](01-current-state-audit.md). Nothing here is a preference; if you cannot name the axiom, it does
not belong in this document.

Legend: **MUST** = failing it is a defect. **SHOULD** = failing it needs a written reason.

---

## ED · The editing surface

| ID | Requirement | Axiom | Finding |
|---|---|---|---|
| ED-1 | A file or notebook cell **MUST** be editable with a caret, a selection model, undo/redo, and multi-cursor. | A3 | E1, E4 |
| ED-2 | Typing **MUST NOT** cause a React re-render of any component that also renders the transcript. The keystroke path touches only the editor's own state. | A3 | — |
| ED-3 | Syntax highlighting **MUST** be parser-based (nesting-aware) for python, sql, scala, r, and **MUST** at minimum highlight markdown, json, yaml, shell, js/ts, html, css. | A2 | E3 |
| ED-4 | The editor **MUST** provide bracket matching, auto-indent, indent guides, and code folding for every parser-based language. | A3 | E3 |
| ED-5 | Highlighting **MUST NOT** be able to alter the text. The existing invariant (`tokenize` round-trips exactly) becomes a property of the new highlighter too. | A2 | — |
| ED-9 | The editor engine **MUST** be chosen on measured evidence (bundle size, theme model, and what the reference notebook implementation uses), recorded with its measurements, and re-measurable by a script in the repo. | A3 | E3 |
| ED-6 | A document larger than 400 KB **MUST** be openable read-only with an explicit explanation, and **MUST NOT** be silently truncated into something savable. | A4 | E8 |
| ED-7 | The editor **MUST** be keyboard-complete: open, save, find, go-to-line, close, next/previous document, without the mouse. | A3 | E6 |
| ED-8 | An unsaved buffer **MUST** survive a page reload, a closed tab, and a failed save. | A4 | E7 |

### Acceptance

- ED-2: a keystroke test asserts zero React renders of the transcript component while typing 50
  characters (instrumented render counter).
- ED-5: property test over the real highlighter: for 10 000 generated strings across 8 languages,
  concatenating the tokens reproduces the input byte-for-byte.
- ED-6: opening a 500 KB file shows the read-only banner and no Save affordance.
- ED-9: `scripts/verify-editor-choice.mjs` rebuilds both candidate bundles and fails if the recorded
  numbers are off by more than 10%, so the decision cannot silently become stale.

---

## NB · Notebook mode

| ID | Requirement | Axiom | Finding |
|---|---|---|---|
| NB-1 | A notebook **MUST** open as a sequence of cells, each with a stable id, a kind (code/markdown), a language, and a source. | A5 | E2 |
| NB-2 | A cell **MUST** be addable, deletable, movable, and convertible between code and markdown, from the keyboard. | A5 | E2 |
| NB-3 | A markdown cell **MUST** render as prose when it is not focused, and become editable when focused — without the text changing on the round trip. | A2, A5 | E2 |
| NB-4 | Cell ids **MUST** be stable across a reorder, so a diff or an AI action addressed to "cell 3" still refers to the same cell after a move. | A5 | E2 |
| NB-5 | Saving a notebook **MUST** produce SOURCE format byte-identical to what `parse_source` would parse back into the same cells. | A2 | E2 |
| NB-6 | Running a cell **MUST** go through the agent's execution path (warehouse or job), not a second executor. | A1 | E6 |
| NB-7 | A cell that the agent wrote, changed, or ran **MUST** be visibly attributable as such, and that attribution survives a reload. | A6 | E1 |

### Acceptance

- NB-5: property test — for every cell list in a generated corpus,
  `parse_source(serialize(cells))` equals `cells` including ids, kinds, languages and sources.
- NB-4: move cell 5 to position 1; the diff view and the "ask about this cell" action both still
  address the same id.
- NB-6: there is no new HTTP route that executes code. Verified by a test that enumerates routes.

---

## WR · The write path and the fence

| ID | Requirement | Axiom | Finding |
|---|---|---|---|
| WR-1 | There **MUST** be exactly one function that decides whether a path may be written: `scope.check_path`. The new save route calls it; it does not re-implement it. | A1 | E6 |
| WR-2 | The fence **MUST** be evaluated on the client before the request (to explain itself early) **and** on the server as the authority. A client that lies is refused. | A1 | — |
| WR-3 | A save outside the working folder **MUST** require explicit human approval, and the approval **MUST** name the target path and the reason. | A1 | E6 |
| WR-4 | A save **MUST** be recorded in the session's event stream with the path, the byte count, and who initiated it (human or agent), so the transcript and the audit are one record. | A6 | E7 |
| WR-5 | The UI **MUST** show the fence before the user types: the path being edited, and whether it is inside the writable folder. | A4 | E6 |
| WR-6 | No route added by this work may delete, move, or overwrite without going through WR-1 and WR-3. | A1 | E6 |
| WR-7 | A save **MUST** be atomic from the user's perspective: either the object is replaced or it is not, and an error is never reported as success. | A4 | — |

### Acceptance

- WR-1: a test asserts the save handler's only policy call is `check_path` (no inlined path logic),
  and a mutation test flips `check_path` to always-deny — the route must obey.
- WR-2: a client that posts an out-of-fence path *without* an approval token gets `403`, not `200`.
- WR-3: the same path *with* a valid approval succeeds, and the approval appears in the event stream.
- WR-7: simulate a mid-import failure; the object on the workspace is unchanged and the UI shows an
  error, not a success.

---

## DF · Diff and agent proposals

| ID | Requirement | Axiom | Finding |
|---|---|---|---|
| DF-1 | An agent's proposed change to an open document **MUST** arrive as a diff against a version the user holds, reviewable per hunk. | A6 | E1 |
| DF-2 | Accepting a hunks-set **MUST** produce exactly the same bytes as if the user had typed the change. | A6 | — |
| DF-3 | Rejecting **MUST** leave the buffer byte-identical to before the proposal. | A6 | — |
| DF-4 | A diff **MUST** be expressible per cell for a notebook, not only per line, because a cell move is a change a line diff renders as a delete plus an insert. | A5 | E2 |
| DF-5 | The diff view **MUST** be reachable from the transcript (the tool call that proposes it) and from the editor, and both must show the same diff. | A6 | — |

### Acceptance

- DF-2: for 200 generated (base, proposal) pairs, applying every hunk yields the proposal exactly;
  applying none yields the base exactly; applying a random subset yields a well-formed document that
  parses.
- DF-4: reorder two cells in a proposal; the diff reports "moved", not "deleted and added".

---

## CX · Concurrency, conflict and loss

| ID | Requirement | Axiom | Finding |
|---|---|---|---|
| CX-1 | The client **MUST** hold a version token for the document it loaded, derived from the server's `object_id` + `modified_at` + `size`. | A4 | E7 |
| CX-2 | On save, the server **MUST** compare the held token with the current one. If they differ, the save **MUST** be refused with `409` and both versions. | A4 | E7 |
| CX-3 | A `409` **MUST** be presented as a choice (keep mine / take theirs / see the diff), never resolved automatically. | A4 | E7 |
| CX-4 | Concurrent saves from two tabs **MUST NOT** interleave into a corrupt document; the loser gets `409`, never a silent overwrite. | A4 | E7 |
| CX-5 | Every write **MUST** keep a local recoverable copy of what the user had, so "the agent overwrote my work" is always recoverable from the browser. | A4 | E7 |

### Acceptance

- CX-2/4: two Playwright pages edit the same file; page A saves, page B saves. B receives a conflict
  UI; the workspace file equals A's content; B's content is offered back, not lost.
- CX-5: force a losing save; assert the draft is still in `localStorage` and restorable.

> **Honest limitation.** The workspace API has no conditional write ([01](01-current-state-audit.md#what-the-databricks-workspace-api-gives-us)).
> CX-2 shrinks the race to a check immediately before the import; it cannot eliminate it. That is
> why CX-5 exists: the guarantee we actually sell is **"a lost write is always recoverable"**, not
> "a lost write never happens". [07 R1](07-decisions-risks.md#r1-no-conditional-write-in-the-workspace-api)

---

## UX · Experience, accessibility and consistency

| ID | Requirement | Axiom | Finding |
|---|---|---|---|
| UX-1 | Opening a document and placing the caret in it **MUST** be possible in under 3 s from a keyboard-only flow (⌘P, type, ⌘↵, F2). | A3 | E6 |
| UX-2 | The editing surface **MUST** meet WCAG 2.2 AA in **both** themes, and **MUST** pass the existing `audit:a11y`. | A4 | — |
| UX-3 | The editor **MUST** contribute 0 CLS on open (`audit:cls` budget is 0 and stays 0). | A4 | — |
| UX-4 | Every icon and control **MUST** use the single geometry from `components/Icons.tsx`. | A4 | — |
| UX-5 | The fence state **MUST** be conveyed by more than colour (text + icon), for forced-colours and greyscale. | A4 | — |
| UX-6 | Losing focus on an unsaved buffer **MUST NOT** discard it; there is no "are you sure?" for text the user can still see. | A4 | E7 |

### Acceptance

- UX-1: e2e timing test, median of 5 runs.
- UX-2/3: the existing audit scripts run unchanged against the new surface and must stay at
  0 findings / 0.0000.
- UX-5: a forced-colours screenshot shows the fence badge still legible.

---

## Traceability matrix

Requirement → axiom → finding → phase → test.

| Req | Axiom | Finding | Phase | Test |
|---|---|---|---|---|
| ED-1..ED-5 | A2, A3 | E1, E3, E4 | P1, P2 | unit + property |
| ED-6 | A4 | E8 | P3 | e2e |
| ED-7, ED-8 | A3, A4 | E7 | P2, P3 | e2e + unit |
| NB-1..NB-5 | A2, A5 | E2 | P2, P4 | property + e2e |
| NB-6 | A1 | E6 | P4 | route enumeration |
| NB-7 | A6 | E1 | P5 | e2e |
| WR-1..WR-7 | A1, A4 | E6 | P0, P3 | unit + mutation |
| DF-1..DF-5 | A5, A6 | E1, E2 | P5 | property + e2e |
| CX-1..CX-5 | A4 | E7 | P3 | e2e, two pages |
| UX-1..UX-6 | A3, A4 | E6 | P1, P6 | e2e + existing audits |

Every row has a phase in [05](05-implementation-plan.md) and a test in
[06](06-edge-cases-testing.md#the-test-map).

[Next: how it is built →](03-architecture.md)
