# 003 · Improve the developer UX/UI: editing and notebooks

**A specification and implementation plan for a first-class editing and notebook experience inside
the Databricks Coding Agents app — one that is faster than the workspace editor, understands
Databricks notebooks natively, and never opens a second unfenced way to write.**

> **Status:** specification · 7 November 2026
> **Scope:** `apps/coding-agent/web` (React 19 + Vite) and `apps/coding-agent/api` (FastAPI).
> **Relation to earlier specs:** builds on [001 · Perfect shell](../001-perfect-shell/README.md)
> (zones, resizing, theme, icons, CLS) and [001 · Databricks coding agents](../001-databricks-coding-agents/README.md)
> (the agent, the write fence, evidence). Does **not** replace either.
> **Audience:** product, design, front end, back end, data, AI, and the person who will maintain it.

---

## The one-paragraph version

The app can *show* a notebook and it can *show* a file, but it cannot **edit** either — and that
is deliberate. [`Viewer.tsx`](../../apps/coding-agent/web/src/components/Viewer.tsx) says so at the
top: *"Read-only on purpose. Editing happens through the agent (which is fenced and audited), so a
viewer that could also write would be a second, unfenced way to change the workspace."* That
sentence is the whole design problem of this specification. Users want to edit — the workspace
editor is slow to open, has no local history, no multi-cursor beyond the basics, and no way to
ask an agent to change *this line*; but the reason editing was removed is real, and re-adding a
naive editor would quietly dismantle the product's central promise.

So this spec does not add an editor and hope. It adds **a fenced editing surface**: a CodeMirror 6
editor, a notebook mode built on the same `Cell` model the agent already uses, and a write path
that goes through the *same* `check_path` scope fence, shows that fence in the UI before you type,
requires human approval outside it, and produces the same evidence trail as an agent turn. The
proposal loop runs both ways: the agent proposes, you review the diff in the editor, and your own
edits are auditable in exactly the same way.

The measured baseline is in [01](01-current-state-audit.md); the reasoning that leads here is in
[00](00-why-first-principles.md).

---

## What is wrong today, in one table

| # | Problem | Evidence |
|---|---|---|
| E1 | **No editing at all.** Every surface is read-only. | `Viewer.tsx` header comment; `Code` renders a `<pre>` |
| E2 | **A notebook is rendered as static blocks.** No cell selection, no run, no reorder, no add. | `NotebookViewer` maps `data.cells` to `<div class="cell">` |
| E3 | **Highlighting is approximate and self-built.** 5 token classes, 4 languages, no bracket matching, no indent guides. | `domain/highlight.ts`, 55 lines |
| E4 | **No caret, no selection, no undo.** A `<pre>` cannot have them. | `Code` component |
| E5 | **No local edit history.** The only history is the agent's transcript. | no `history` in `web/src` |
| E6 | **The only write path is the agent.** A user who wants to fix one typo must write a prompt. | `workspace.py` exposes `mkdirs` only |
| E7 | **No conflict detection.** Two writers (agent + human, or two tabs) silently clobber. | `Doc.rev` is a local counter, not a server version |
| E8 | **Large files are truncated with no way to edit the rest.** | `MAX_READ_BYTES = 400_000` |

---

## Reading map

Read in this order the first time. Every document is self-contained and cross-linked.

| # | Document | The question it answers | Lead lens |
|---|---|---|---|
| 00 | [Why, from first principles](00-why-first-principles.md) | Why bother? What is irreducibly true here? | PO + AI engineer |
| 01 | [Current state audit](01-current-state-audit.md) | What exactly do we have, measured? | Full-stack + VSCode expert |
| 02 | [Requirements](02-requirements.md) | What must be true when we are done? | PO + UX |
| 03 | [Architecture](03-architecture.md) | How is it built? Where does each piece live? | Full-stack + compiler |
| 04 | [Eight lenses](04-lenses.md) | What does each discipline refuse to ship without? | all eight |
| 05 | [Implementation plan](05-implementation-plan.md) | In what order, with what acceptance? | Full-stack |
| 06 | [Edge cases and testing](06-edge-cases-testing.md) | What can go wrong, and what catches it? | Compiler + AI |
| 07 | [Decisions and risks](07-decisions-risks.md) | What did we choose, reject, and fear? | PO |

---

## The editor choice, grounded

"Use the best editor" is not an argument, so the choice was measured rather than asserted.

| | CodeMirror 6 | Monaco |
|---|---|---|
| **Gzipped bundle** (editor + 5 languages + diff + search) | **250 KB** | **1.19 MB** |
| Installed | ≈ 1.9 MB | 101.7 MB |
| Weekly downloads (core) | **23.1 M** (`@codemirror/view`) | 13.5 M (`monaco-editor`) |
| Theme | per instance (`EditorView.theme`) | global (`MonacoEnvironment`, workers) |
| Diff included | `@codemirror/merge` | separate |

And the decisive one: **JupyterLab 4.6.6 — the most-used notebook implementation — is built on
CodeMirror 6.** In `@jupyterlab/codemirror` 24 of 34 dependencies are CodeMirror/Lezer, and
`monaco-editor` appears nowhere in its notebook, cells, or codemirror packages. Its cell model uses
a Yjs CRDT for identity, which is the same reasoning as [axiom A5](00-why-first-principles.md#a5-a-notebook-cell-is-a-unit-of-intent-not-a-unit-of-layout):
an index cannot survive a reorder.

Full measurements and the honest list of Monaco's advantages: [07 D1](07-decisions-risks.md#d1-codemirror-6-not-monaco).

## Scope boundary

**In scope**

- An editing surface for `.py`, `.sql`, `.scala`, `.r`, `.md`, `.json`, `.yaml`, `.toml`, `.sh`,
  `.js`, `.ts`, `.html`, `.css` files in the workspace.
- A **notebook mode**: cells as first-class objects, with add, delete, move, change-type, run,
  and a markdown cell that renders when you leave it and edits when you enter it.
- A **fenced write path**: save, with the scope fence evaluated before the request leaves the
  browser and again on the server, with approval outside the fence.
- **Diff review**: an agent proposal arrives as a diff you accept or reject per hunk.
- Conflict detection on save.
- Keyboard model, accessibility, and theme integration consistent with
  [001-perfect-shell](../001-perfect-shell/README.md).

**Out of scope, and why**

| Not doing | Reason |
|---|---|
| A full LSP / IntelliSense with type inference | Requires a language server per language; the Databricks workspace editor has the DB engine behind it, we do not. We do *syntax-aware* completion from catalog metadata instead, which is the useful 20%. |
| Running a notebook cell-by-cell in the browser | Execution belongs to the warehouse and the agent, which already has `dbx_run_sql` and `dbx_run_notebook` with evidence. A second executor would need its own scope fence. |
| Collaborative multi-cursor editing | Needs a CRDT and a presence server. Valuable, but a different project; the seam is noted in [07](07-decisions-risks.md). |
| Editing Git folders with a commit UI | A Git folder is a repo with its own semantics. We support editing a file inside one, and refuse the commit flow — see [06](06-edge-cases-testing.md) D3. |
| Replacing the agent with an editor AI | The agent is the product. The editor is where you *review and correct* its work. |

---

## The five sentences this spec must satisfy

If any of these is false, the design is wrong.

1. **There is still exactly one way to change a workspace object's content: through the scope
   fence.** Not "the editor is also fenced"; the *same* function decides.
2. **A user can fix a typo without writing a prompt**, in under three seconds, from the keyboard.
3. **A notebook behaves like a notebook**: cells add, move, change type, run, and a markdown cell
   renders as prose when you are not in it.
4. **An agent proposal is reviewable before it lands**, per hunk, with the diff in the same
   surface you would have typed in.
5. **Nothing is lost**: a failed save, a closed tab, or a race with the agent leaves your text
   recoverable.

---

## Cross-reference index

Every document links forward and back. If you are reading one in isolation, this is where to go
next for any given question.

| If you want to know… | Read |
|---|---|
| Why an editor at all, when the agent writes code | [00 §The fourth why](00-why-first-principles.md#the-five-whys) |
| Which editor engine, and why not Monaco | [07 D1](07-decisions-risks.md#d1-codemirror-6-not-monaco) |
| How the fence is enforced twice | [03 §The write path](03-architecture.md#the-write-path) |
| What a cell *is*, formally | [03 §The document model](03-architecture.md#the-document-model) |
| What happens if the agent writes while I edit | [06 C1–C6](06-edge-cases-testing.md#c-concurrency-conflict-and-loss) |
| How this ships, in what order | [05](05-implementation-plan.md) |
| What each discipline will refuse | [04](04-lenses.md) |
| What we are not building | [README §Scope](#scope-boundary) and [07 §Rejected](07-decisions-risks.md) |
