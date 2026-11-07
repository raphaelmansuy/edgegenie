# 00 · Why, from first principles

[Index](README.md) · next: [01 Current state audit](01-current-state-audit.md)

## The five whys

Start from the complaint, not the solution.

**1. Why does the user want a better edit experience?**
Because they open a notebook in this app, see a problem on line 42, and cannot fix it.

**2. Why can they not fix it?**
Because the viewer renders cells as static `<div>`s inside a `<pre>`. There is no caret, no
selection, no undo, and no save. `Viewer.tsx` is explicit: *"Read-only on purpose."*

**3. Why is it read-only on purpose?**
Because the product's promise is that *nothing outside your working folder changes without your
approval*, and that promise is implemented as a single choke point — the agent's tool calls, each
of which passes through `domain/scope.py::check_path` / `check_sql` and is recorded as evidence.
A general-purpose writable editor is a **second path to the same bytes** that does not pass through
that choke point. The author removed the second path rather than fence it.

**4. Why was removing it the wrong trade?**
Because it made the app a *reporting* tool with a chat box. The user's loop is: read → think →
**change** → verify. We support read and verify, and we outsource *change* to a prompt. That is a
slow, lossy, and in one specific way unsafe trade — the user's intent goes through a natural
language compressor before it becomes an edit, and the editor they *would* have used lives in
another tab where the fence does not exist at all. **We did not remove the unfenced path; we pushed
the user to Databricks' workspace editor to find it.** The risk moved, it did not shrink.

**5. Why does that matter for the product?**
Because the differentiator against the workspace editor is not that we can *show* a notebook — it
is that we know **why** the notebook exists: the turn that produced it, the tables it read, the SQL
that ran, the evidence that it worked. That context is worth nothing at the moment of reading and
everything at the moment of editing. Cutting editing cut the loop exactly where our advantage is
largest.

> **The conclusion the five whys force:** the fence was never the problem. The problem was that
> the fence had exactly one door. Build the second door **in the fence**, not around it.

---

## First principles

Six axioms. Each is falsifiable and each constrains the design; [02 Requirements](02-requirements.md)
traces every requirement back to one of these.

### A1 · Every byte written has one owner and one decision function

There is no write that skips the policy. Not "the editor also checks"; the *same* function decides,
in the same way, with the same result, whether the request came from a tool call or a keystroke.

**Consequence:** the save endpoint takes a path and a payload and calls `scope.check_path`. It does
not take a boolean `allowed`. The browser's copy of the check is a *courtesy* — it prevents a
round-trip and explains itself — never the authority. If the two ever disagree, the server wins and
the client must be able to explain why.

### A2 · Text is the product; the editor is a view of it

A notebook is not a DOM. It is a sequence of cells, each with a language and a source, and a
canonical serialization to the workspace's SOURCE format. The editor edits **text**, and the cell
structure is derived. This is why `api/domain/notebook.py` is pure and already tested: `parse_source`
is the inverse of the serialization we will need, and it must stay a total function.

**Consequence:** one module owns the round trip, `parse(serialize(cells)) === cells` for every cell
list we can produce, and that is a property test, not an example test.

### A3 · Latency is a feature of an editor and a defect elsewhere

An editor that lags 100 ms per keystroke is unusable in a way a chat that streams in 100 ms chunks
is not. The keystroke path must not touch the network, React state that re-renders the transcript,
or a synchronous parse of the whole document.

**Consequence:** the editor owns its own document state (CodeMirror's `EditorState`), and React
never re-renders it per keystroke. This is the single most important architectural rule in
[03](03-architecture.md#the-edit-path-no-react-in-the-keystroke), and it is why the editor is not a controlled component.

### A4 · The user's unsaved work outranks the server's convenience

Any design where a background refresh, an agent turn, or a tab switch can discard typed text is
wrong regardless of how rare the race is. The failure is silent and unrecoverable, which makes it
categorically worse than a visible error.

**Consequence:** a local draft is written on a debounce *before* any save is attempted, restored on
open, and a conflict is surfaced as a **choice**, never a resolution. See
[06 C1–C6](06-edge-cases-testing.md#c-concurrency-conflict-and-loss).

### A5 · A notebook cell is a unit of intent, not a unit of layout

Users reason about "*this* cell". So selection, execution, AI actions, diff hunks, and error
reporting must all be able to address one cell. A cell needs a stable identity that survives
reordering — index alone cannot, because moving a cell changes every index below it.

**Consequence:** cells carry an id derived from content and position at parse time and stabilised
on load; reorder is an operation on ids, and a diff is expressed per cell before it is expressed
per line.

> **This is independently confirmed by the reference implementation.** JupyterLab's cell model is
> built on `@jupyter/ydoc` — *"Jupyter document structures for collaborative editing using YJS"*,
> a CRDT — and `@jupyterlab/cells` depends on it directly. A CRDT cannot address a cell by index,
> because an index is not stable under concurrent edits; it needs a stable identity per cell. That
> is exactly the reasoning in A5, arrived at by a team with no knowledge of this spec. See
> [07 D1](07-decisions-risks.md#the-decisive-evidence-the-reference-notebook-is-built-on-the-same-engine).

### A6 · The agent and the human are two clients of the same document

Not one privileged writer and one guest. Both produce edits, both must be able to see the other's,
and the merge must be described in the same terms. Treating the agent's write as a special case is
how you get a "the agent overwrote my changes" bug that nobody can reason about.

**Consequence:** agent proposals arrive as a **diff against a version**, exactly like a human's edit
buffer, and both go through the same accept/reject and the same save. See
[03 §Both writers, one model](03-architecture.md#both-writers-one-model).

---

## What the axioms rule out

Stated plainly, because these are the tempting shortcuts:

| Temptation | Which axiom kills it | Why |
|---|---|---|
| A `<textarea>` with highlight overlay | A3 | Two sources of truth for the text; scroll and cursor drift are unfixable |
| Make the editor read-only until the agent approves | A4, A6 | Punishes the human for the agent's concurrency; treats them as unequal clients |
| `contentEditable` per cell | A2, A3 | The DOM becomes the document; round-trip serialization becomes lossy |
| Save the whole notebook on every keystroke | A3 | Network on the keystroke path |
| Client-side fence with server as a rubber stamp | A1 | The client is not the authority and must never be able to become it |
| Reuse `tokenize()` and add a caret | A3, E3 | 55 lines of regex cannot give bracket matching, indent guides, or a selection model |
| Full Monaco to "get it right" | A3 | 101 MB unpacked for a chat app's editor pane (measured, [07 D1](07-decisions-risks.md#d1-codemirror-6-not-monaco)) |

---

## The fourth why, restated as a design goal

> **Make the moment of editing the moment our context is most valuable.**

Concretely: when the caret is in cell 3, the inspector should be able to tell you what cell 3 does,
which table it reads, whether it ran, and what the agent said about it. That is only possible
because we own the whole surface. It is the reason to build an editor here rather than link out to
one.

[Next: what we actually have today, measured →](01-current-state-audit.md)
