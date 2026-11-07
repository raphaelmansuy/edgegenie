# 07 · Decisions, risks, open questions

[Index](README.md) · prev: [06 Edge cases](06-edge-cases-testing.md)

---

## D1 · CodeMirror 6, not Monaco

**Decision:** CodeMirror 6.

This is the decision most likely to be second-guessed ("surely the `monaco-editor` package is the
best, it is VS Code"), so it is grounded in measurements taken on this machine on 7 November 2026,
not in reputation.

### Shipped weight, measured

Built both with the same tool (`esbuild --bundle --minify --format=esm`) and gzipped, because
gzipped bytes over the wire is what a user waits for:

| Bundle | Raw | **Gzipped** | Extra assets |
|---|---|---|---|
| CodeMirror 6 — editor + python, sql, markdown, json, javascript + merge + search | 720 293 B | **250 281 B** | — |
| `monaco-editor` — the package entry | 4 594 453 B | **1 193 544 B** | `codicon.ttf`, worker scripts |

**Monaco is 4.8× the gzipped bytes** for the editor alone, before language workers. The CodeMirror
figure already includes **five language parsers** plus the diff engine and the search panel — the
whole editing feature set, not a bare core.

Installed footprint tells the same story: `monaco-editor` unpacks to **101 674 083 B**;
the CodeMirror packages we need sum to **≈ 1.9 MB**.

### Ecosystem, measured

Weekly downloads from the npm registry API:

| Package | Downloads / week |
|---|---|
| `@codemirror/view` (CM6 core) | **23 099 855** |
| `@codemirror/state` | 22 551 659 |
| `monaco-editor` | 13 465 751 |
| `@codemirror/merge` | 3 431 014 |

> The bare `codemirror` package shows 15.5 M/week but that number is not a fair v6 signal: the
> `codemirror` name also served CodeMirror 5. `@codemirror/view` is the honest v6 core count, and
> it is the **most-downloaded code editor on npm** — ahead of Monaco. "Best on the market" and
> "least popular" are not the same thing, and this is not a niche choice.

### Architectural fit, verified in the type definitions

- **Theming is per instance.** `@codemirror/view` exposes `EditorView.theme` — a theme is a
  value you pass to one editor. Our themes are CSS tokens resolved at runtime
  ([04](04-lenses.md#5-front-end-designer)); a per-instance theme means dark mode is inherited, not
  built twice.
- **Monaco requires a global.** Its ESM API references `MonacoEnvironment` for worker
  resolution — a process-wide singleton. That fights React's lifecycle and makes two independently
  themed editors awkward.
- **State is a value, not a tree.** `EditorState.create()` returns the document state as data. This
  is what makes ED-2 possible: the app can observe and replace state without a component re-render.
- **`@codemirror/merge` ships the diff.** DF-1..DF-5 need per-hunk review; it is one dependency we
  already count, not a fourth library.

### The decisive evidence: the reference notebook is built on the same engine

The request that produced this spec was to build *the best notebook experience*, so the right
question is not only "which editor is fastest" but **"what did the people who built the reference
notebook choose, when they had our exact problem"** (cells, markdown ⇄ code, diff, syntax
highlighting, one page, many languages).

JupyterLab 4.6.6, from the registry:

```
@jupyterlab/codemirror@4.6.6 — 34 dependencies, of which 24 are CodeMirror 6 / Lezer:

  @codemirror/autocomplete ^6.20.0     @codemirror/lang-python  ^6.2.1
  @codemirror/commands     ^6.10.2     @codemirror/lang-rust    ^6.0.2
  @codemirror/lang-cpp     ^6.0.3      @codemirror/lang-sql     ^6.10.0
  @codemirror/lang-css     ^6.3.1      @codemirror/lang-wast    ^6.0.2
  @codemirror/lang-html    ^6.4.11     @codemirror/lang-xml     ^6.1.0
  @codemirror/lang-java    ^6.0.2      @codemirror/language     ^6.12.1
  @codemirror/lang-javascript ^6.2.4   @codemirror/legacy-modes ^6.5.2
  @codemirror/lang-json    ^6.0.2      @codemirror/search       ^6.6.0
  @codemirror/lang-markdown ^6.5.0     @codemirror/state        ^6.7.6
  @codemirror/lang-php     ^6.0.2      @codemirror/view         ^6.43.15
  @lezer/common ^1.2.1  @lezer/generator ^1.7.0  @lezer/highlight ^1.2.0  @lezer/markdown ^1.3.0
```

`monaco-editor` appears **nowhere** in JupyterLab's notebook, cells, or codemirror packages. And
`@jupyterlab/notebook` itself depends on `@jupyterlab/codemirror` — the notebook *is* CodeMirror
cells.

That is the strongest grounding available for this decision: **the most-used notebook implementation
in the world, solving the same problem, chose CodeMirror 6.** Choosing Monaco would mean arguing we
know better than the Jupyter team about notebooks, on a project with one-tenth their scope.

It also validates the architecture in [03](03-architecture.md): a notebook is a list of independent
CodeMirror instances, each with its own state, not one editor pretending to be cells. That is exactly
the EditorHost-per-cell model this spec proposes.

> Caveat, stated: JupyterLab does not use `@codemirror/merge` — it has its own nbdime-based diff.
> We use `@codemirror/merge` because it is 183 KB installed and gives per-hunk review, which is
> all DF-1..DF-5 need.

### Where Monaco would be better, stated honestly

Monaco has things CodeMirror does not:

| Monaco strength | Does it matter for us? |
|---|---|
| Real language services (TS/JS type checking out of the box) | Not for python/sql notebooks; and we have no LSP for them either way |
| The VS Code extension model | Out of scope ([04](04-lenses.md#6-vs-code-expert)) |
| Familiar to VS Code users | Cosmetic; CodeMirror's default keymap is VS Code-compatible where it matters |
| Multi-file workspace model | We have one document per tab |

So Monaco's advantages cluster in areas this spec explicitly excludes, and its costs land directly
on the two things we care most about: **time to first keystroke** (250 KB vs 1.19 MB) and
**theme integration** (per-instance vs global).

**Revisit if:** we ship a real TypeScript/JavaScript language service, or a multi-file editing model.

## D2 · A second work surface in the centre zone, not a new zone

**Decision:** the editor replaces the viewer inside the existing centre zone; no fifth zone.

**Rejected:** a right-hand "edit" pane, or a full-screen editor route.

**Why:** [001-perfect-shell](../001-perfect-shell/03-architecture.md#zone-model) established four zones
and paid for it with a careful drawer/resize/persist model, tested by `audit:shell`. A fifth zone
multiplies the layout state space (visibility × width × mode × persistence) without adding a
capability. The editor is a *document*, and documents already open in tabs in the centre.

**Cost accepted:** you cannot see the transcript and the editor at full width simultaneously. The
inspector carries the "what did the agent say about this cell" context instead, which is the
information that actually matters while editing ([00, the fourth why](00-why-first-principles.md#the-fourth-why-restated-as-a-design-goal)).

---

## D3 · The agent's write to an open document becomes a proposal

**Decision:** when a tool write targets a document the user has open, it is recorded as a proposal
with a diff, not applied.

**Rejected:** apply it and let the user undo; apply it and show a toast.

**Why:** A6, and the "lost my work" failure. A toast after the fact is a notification that a loss
already happened.

**Cost accepted:** the agent is slightly less autonomous when a document is open. Its tool result
must say "proposed", or it will produce a confidently wrong summary
([04](04-lenses.md#7-ai-engineer)).

---

## D4 · No lock, no "editing" presence

**Decision:** no server-side lock, no "someone else is editing" indicator between tabs.

**Why:** the workspace API cannot enforce a lock, so a lock we displayed would be advisory and
therefore a lie. Two tabs of the same user are a normal case, not a conflict to prevent.

**The substitute** is the version token + conflict UI + draft (CX-1..CX-5).

---

## D5 · Serialization lives in Python, not duplicated in TypeScript

**Decision:** `api/domain/notebook.py` gains `serialize_source`. The front end calls the save route
with cells (or text) and never serializes independently — except in tests, where a shared corpus
verifies agreement.

**Rejected:** a TypeScript serializer mirroring the Python one, used to build the payload.

**Why:** DRY at the point of danger. Two serializers is two chances to corrupt a notebook, and the
bug would only appear on files with an unusual structure (A3, B7, B8). One serializer has one set of
tests.

**Cost accepted:** saving a notebook requires a round trip that would otherwise be local. That is
acceptable because saving is not on the keystroke path.

---

## D6 · `EditorHost` is a 5-method interface

**Decision:** the app depends on `mount / getValue / setValue / onChange / onCellMeta`, not on
CodeMirror.

**Why:** Liskov and DIP ([04](04-lenses.md#solid-applied)). It also makes the editor mockable: an
`EditorHost` over a `<textarea>` lets component tests run without a real editor, which keeps the test
suite fast.

**Cost accepted:** a thin adapter to maintain, and one indirection when debugging.

---

## D7 · Read-only for truncated documents

**Decision:** a document the reader truncated (400 KB, or a truncated cell) cannot be saved.

**Why:** saving it would write back only the part we read — **silent data loss**, the worst failure in
an editor. The banner explains it.

**Rejected:** "save what you see" — that is the data-loss bug.

---

## D8 · `⌘F` belongs to the editor when it has focus

**Decision:** `⌘F` opens the document find panel only when focus is inside the editor; elsewhere it is
the browser's.

**Why:** overriding a browser key globally is hostile (E9). Scoping it to focus is the behaviour
people expect from every editor.

---

## D9 · No CRDT in this design

**Decision:** no CRDT (no Yjs, no Automerge). Concurrency is a version token and a conflict UI.

This needs defending, because the spec *cites* JupyterLab's Yjs CRDT as evidence for axiom A5. Taking
the reasoning and not the protocol is deliberate, and the distinction matters:

> A5 says **a cell needs a stable identity, because an index cannot survive a reorder.** That is a
> statement about the document model. A CRDT is one *implementation* of it, and it exists to solve a
> different problem: merging concurrent operation streams. We adopted the identity rule (cells carry
> ids, moves are operations on ids) without the merge machinery.

### What a CRDT needs, and what we have

| A CRDT requires | What exists here |
|---|---|
| Two writers producing **operation streams** on one shared document | Both writers produce a **whole-file replacement**. The agent calls `dbx_write_notebook(cells)`; the human posts a full text. |
| A **stable document identity** to converge on | The storage **destroys identity on every write**: `overwrite` is rejected with `format=SOURCE` (measured: `INVALID_PARAMETER_VALUE`), so a save is delete-then-import and `object_id` changes. This was discovered the hard way — `object_id` had to be removed from the version token because it made every first save 409. |
| A **channel** to exchange deltas | The workspace API is REST import/export. No websocket, no delta endpoint, no server-side document store. |

### Why a client-only CRDT buys nothing

If the CRDT lives in one browser tab, the merge happens locally and is then **discarded by the next
whole-file import**. It gives no cross-session guarantee, and it is strictly more machinery than a
version token for the same outcome.

### What a server-side CRDT would cost

- a second source of truth for document content (Lakebase + Yjs), which **contradicts D5** (one
  serializer, one authority) and duplicates a persistence problem the workspace already solves;
- agent writes must become operation streams, so every tool's write path changes;
- presence/awareness, tombstone GC, and auth on a new sync endpoint;
- and at import time a **whole-file reconcile would still be needed**, because the workspace is not
  CRDT-aware. That is two concurrency models layered, neither authoritative — the worst outcome.

### When this decision should be *reversed rather than extended*

The trigger is a product condition, not scale: **two people editing the same notebook at once and
expecting to see each other's carets.** If that becomes the goal, the design changes:

1. the document store owns content (Lakebase + Yjs) and the workspace becomes an **export target**;
2. agent writes become operations, not whole files;
3. the version token, the 409 path and `ConflictPanel` are **removed** — replaced by presence and
   convergence. Keeping them alongside a CRDT would be the layered failure above.

Until then, the honest promise stands: a lost write is always **recoverable** (draft, CX-5), and a
detected conflict is always a **choice** (CX-3). That is the strongest guarantee the current storage
can keep, and it is a guarantee we can test.

## Risks

### R1 · No conditional write in the workspace API

**What:** there is no `If-Match`-style conditional import. Our version check is
time-of-check-to-time-of-use racy, so a lost write is possible and undetectable in a narrow window.

**Why we cannot fix it:** the API does not expose the primitive.

**Mitigation:** detect what we can (compare immediately before import), never auto-resolve a detected
conflict, and keep a local draft so an undetected one is recoverable. **We ship the promise
"recoverable", not "impossible"**, and the UI says so.

**Residual risk:** a user who ignores the draft-recovery affordance can lose text. Accepted and
documented, because the alternative is claiming a guarantee we cannot keep.

### R2 · Round-trip corruption of a real notebook

**What:** a notebook with an unusual structure (a separator inside a string, a cell with no trailing
newline, mixed magics) serializes back differently, so opening and saving changes bytes.

**Impact:** high — it looks like the editor "touched" a file.

**Mitigation:** P0 property test over 200 real notebooks from the workspace *before* the UI exists.
Any failure blocks P2.

### R3 · The fence is duplicated by accident

**What:** a future contributor adds a save variant with its own path check.

**Impact:** critical — the product's central promise.

**Mitigation:** a mutation test that makes `check_path` always deny; any route that still saves is
unfenced. Plus a review checklist item and the route-enumeration test.

### R4 · Per-keystroke re-render returns

**What:** someone converts the editor to a controlled component because it is "simpler".

**Impact:** the app feels slow exactly when it must feel fast.

**Mitigation:** the render-count test (ED-2) is a gate in CI, not a diagnostic.

### R5 · Bundle growth

**What:** the editor chunk plus language parsers plus the diff library push the app over a size
budget users notice on a slow connection.

**Mitigation:** measure gzip in P1; lazy-load per language; a documented budget of ≤ 250 KB gzipped
for the editor chunk.

### R6 · Diff performance on large files

**What:** a 400 KB file's diff produces thousands of hunks and the UI stalls.

**Mitigation:** cap the hunk count; beyond it, present "replace whole file" with a clear warning
instead of a misleading summary.

### R7 · Users edit outside the fence constantly

**What:** the working folder is `agent_scratch` but users open files in `/Shared`, so every save
prompts.

**Impact:** friction that makes the feature feel broken.

**Mitigation:** the fence chip explains *before* typing (WR-5), the folder is settable per session,
and the approval is one keystroke. If telemetry shows this is the common path, promote "change my
working folder to here" to the approval sheet.

### R8 · Notebook language changes break `import`

**What:** `import` with `format=SOURCE` may refuse a language that differs from the existing object.

**Mitigation:** probe in P0; fall back to create-at-temp-path then swap (A5).

---

## Open questions

These are genuinely unresolved and need a decision before or during implementation. Each names who
should decide.

| # | Question | Why it is not decided here | Who |
|---|---|---|---|
| Q1 | Do we show a **notebook revision history** from the workspace API, or only the local draft? | The API exposes revisions for notebooks but not files; showing it for one and not the other is an inconsistency we should decide deliberately | PO + DB |
| Q2 | Does `⌘S` save the **whole notebook** or the focused cell? | Whole notebook is simpler and matches the API; per-cell is what a user might expect. D2 says the object is the unit — but is that what people feel? | UX + PO |
| Q3 | Should the agent see the **unsaved buffer** when asked about the current cell? | Convenience vs. an implicit data-sharing surprise ([04](04-lenses.md#7-ai-engineer)) | PO + AI |
| Q4 | Do we support **multi-root workspaces** (edit in two folders)? | The session has one working folder; a second is a scope-model change, not a UI change | PO + security |
| Q5 | What is the **draft TTL**? | 30 days is a guess; it should follow user expectations for "recover my work" | PO |
| Q6 | Do we ship a **vim/emacs keymap**? | `@replit/codemirror-vim` is 205 KB; worth it for some users, dead weight for most. A preference, not a default | Front-end + PO |

---

## Traceability: decision → requirement

| Decision | Enables | Constrains |
|---|---|---|
| D1 CodeMirror | ED-1..ED-5 | ED-2 (its state model is what makes no-re-render possible) |
| D2 centre zone | all UX | UX-1 (must be fast because it is a replacement, not an addition) |
| D3 proposal | DF-1, A6 | NB-7 (attribution matters more once changes are reviewable) |
| D4 no lock | CX-1..CX-5 | CX-3 (no lock means conflict is a first-class state) |
| D5 one serializer | NB-5 | WR-7 (atomicity depends on one canonical byte representation) |
| D6 EditorHost | ED-1 | test speed |
| D7 read-only truncated | ED-6 | — |
| D8 scoped `⌘F` | UX-1 | — |
| D9 no CRDT | CX-1..CX-5 (a guarantee we can keep) | rejects live multi-user editing |

[Back to the index](README.md)
