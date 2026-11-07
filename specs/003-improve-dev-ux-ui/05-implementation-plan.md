# 05 · Implementation plan

[Index](README.md) · prev: [04 Lenses](04-lenses.md) · next: [06 Edge cases and testing](06-edge-cases-testing.md)

Seven phases. Each one ends in a state that is **shippable and verifiable on its own** — no phase
depends on a later one to be useful, and no phase leaves the app in a worse state than it found it.

Ordering principle: **the fence comes first, the editor last.** A save path that is fenced and
tested is useful even with no editor (an agent-only write). An editor with no fence is a regression
waiting to happen.

```
P0 fence + save route ──► P1 editor host ──► P2 files editable ──► P3 drafts/conflict
                                                                          │
                                                          P4 notebook mode
                                                                  │
                                                          P5 diff + proposals
                                                                  │
                                                          P6 polish + audits
```

---

## P0 · The write path (no UI yet)

**Goal:** a fenced save exists and is proven, before any editor can call it.

| Work | File | Acceptance |
|---|---|---|
| `serialize_source()` next to `parse_source()` | `api/domain/notebook.py` | property test: round trip on 200 real notebooks |
| `import_source()` + `status()` on the browser | `api/adapters/databricks/workspace.py` | unit test with a fake HTTP layer |
| `POST /api/workspace/save` | `api/routers/api.py` | calls `check_path`; 403 out of fence; 409 on version mismatch |
| version token helper | `api/domain/version.py` | same token for the same object; changes when it changes |
| event record for a human write | `api/routers/api.py` | appears in `/api/sessions/{id}` stream |

**Why first:** it is the risky part (a second write path) and it must be proven safe before there is
a UI to make it convenient. If this phase cannot be made fenced, the rest of the plan is cancelled.

**Definition of done:** a `curl` can save a file inside the working folder, is refused outside it
without an approval, and the write appears in the session's event stream.

**Risk:** the workspace `import` API may not accept `format=SOURCE` for a notebook whose language
differs from the existing object. Mitigation: probe it in this phase; fall back to
`create`-then-`delete` with a temp path ([06 A5](06-edge-cases-testing.md#a-the-write-path-and-the-fence)).

---

## P1 · The editor host

**Goal:** an editor that mounts, edits, and cannot re-render the app per keystroke.

| Work | File | Acceptance |
|---|---|---|
| `EditorHost` interface + CodeMirror adapter | `web/src/editor/host.ts` | 5 methods; no `@codemirror` import outside `web/src/editor/` |
| theme binding to tokens | `web/src/editor/theme.ts` | both themes pass `audit:a11y` |
| lazy chunk | `web/src/components/Editor.tsx` | editor JS is a separate chunk; opening a doc adds 0 CLS |
| render-count instrumentation | `web/src/hooks/useRenderCount.ts` (test-only) | typing 50 chars → 0 transcript renders |

**Definition of done:** a document opens in an editor, you can type with a caret and undo, the
app's render count does not move while typing, and the bundle grew by ≤ 250 KB gzipped.

**Depends on:** nothing. P1 can run in parallel with P0.

---

## P2 · Files become editable

**Goal:** open → edit → save, end to end, for a plain file.

| Work | File | Acceptance |
|---|---|---|
| fence chip in the editor bar | `web/src/components/EditorBar.tsx` | three states; text + icon, not colour alone (UX-5) |
| save client + 409 mapping | `web/src/api/save.ts` | 403 → approval sheet; 409 → conflict; 200 → clean |
| read-only for oversize | `Viewer.tsx` | 500 KB file: banner, no Save (ED-6) |
| keyboard map | `web/src/editor/keys.ts` | `⌘S`, `⌘F`, `⌘G`, `⌘Z`, `⌘/`, `⌥↑/↓` |
| draft on debounce | `web/src/domain/drafts.ts` | survives reload |

**Definition of done:** the three-sentence user story works — open `notes.md`, type a line, `⌘S`,
reopen, the line is there.

---

## P3 · Drafts, conflict and loss

**Goal:** CX-1..CX-5 hold under a real race.

| Work | Acceptance |
|---|---|
| version token threaded through load → edit → save | 409 on a stale save |
| conflict panel (keep mine / take theirs / diff) | never auto-resolves (CX-3) |
| pre-save snapshot to `localStorage` | a losing save is restorable (CX-5) |
| two-tab Playwright test | loser gets 409, file is the winner's (CX-4) |
| draft TTL + cleanup | 30 days, then evicted; never grows without bound |

**Definition of done:** the two-page test passes and the losing page can restore its text.

---

## P4 · Notebook mode

**Goal:** NB-1..NB-6.

| Work | File | Acceptance |
|---|---|---|
| `domain/notebook.ts` — parse/serialize/cell ops | new | property tests both directions |
| cell stack component | `NotebookEditor.tsx` | add/delete/move/convert from keyboard |
| markdown cell: render ⇄ edit | `MarkdownCell.tsx` | NB-3, no text change on round trip |
| cell gutter + attribution | `CellGutter.tsx` | NB-7: "agent wrote this · ran 4.2s" |
| run → agent tool, not a new executor | calls `dbx_run_sql` via the compose path | route enumeration test finds no new executor (NB-6) |

**Definition of done:** open a real notebook, add a markdown cell, move it to the top, save, and the
bytes differ from the original **only** by that cell.

**The hardest item in the whole plan** is the round-trip property. Budget for it.

---

## P5 · Diff and agent proposals

**Goal:** DF-1..DF-5.

| Work | Acceptance |
|---|---|
| `domain/diff.ts` — line and cell hunks | apply-all → proposal; apply-none → base |
| `DiffView.tsx` | per-hunk accept/reject |
| agent write to an open doc becomes a proposal | tool result says "proposed" |
| cell-level diff | a move reports "moved" |

**Definition of done:** the agent proposes a change to an open notebook, the user rejects one hunk,
saves, and the result is exactly base + accepted hunks.

---

## P6 · Polish and the standing audits

**Goal:** the new surface is indistinguishable in quality from the shell.

- `audit:a11y` → 0 findings, both themes.
- `audit:cls` → 0.0000, including the editor mount.
- `audit:overflow` → 0 / 20.
- e2e scenes for the editor: `editor-open`, `editor-dirty`, `editor-conflict`, `notebook-cells`,
  `diff-review` added to the screenshot suite with stable numbers.
- Documentation: update [001-perfect-shell](../001-perfect-shell/README.md) to note the second work
  surface, and this spec's [06](06-edge-cases-testing.md) with what the audits actually found.

---

## Risk table

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Workspace `import` rejects a language change | medium | high | probe in P0; temp-path fallback |
| Round-trip property fails on real notebooks | **high** | **high** | run the corpus in P0, before the UI exists |
| Editor bundle too large | medium | medium | measure gzip in P1; code-split per language |
| Per-keystroke re-render creeps back | medium | high | the render-count test is a gate, not a report |
| The fence gets duplicated | low | **critical** | mutation test on `check_path`; review checklist |
| Diff algorithm slow on a 400 KB file | medium | medium | cap hunks; fall back to "whole file replace" with a warning |
| Users edit outside the fence and get blocked constantly | medium | medium | default the working folder to `agent_scratch`; the approval is one keystroke |

---

## Definition of done for the whole spec

1. All `MUST` requirements in [02](02-requirements.md) pass, each with a named test.
2. The standing audits are still green: `vitest`, `pytest`, `audit:a11y` (both themes),
   `audit:overflow`, `audit:cls`, `e2e:shell`.
3. Every edge case in [06](06-edge-cases-testing.md) has a mitigation in code and a test that fails
   if the mitigation is removed.
4. No route, module, or component re-implements the fence, the serializer, or the cell model.
5. A person who has never seen the app can open a notebook, change a cell, save it, and see the
   change in Databricks — with no instructions.

[Next: edge cases and how each is caught →](06-edge-cases-testing.md)
