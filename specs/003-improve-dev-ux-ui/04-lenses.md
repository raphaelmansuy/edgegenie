# 04 · Eight lenses

[Index](README.md) · prev: [03 Architecture](03-architecture.md) · next: [05 Implementation plan](05-implementation-plan.md)

Each lens answers one question: **what will this discipline refuse to ship without?** The point is
not to give every view equal airtime; it is to surface the requirements that a single perspective
would miss. Where two lenses conflict, the conflict and its resolution are stated explicitly.

---

## 1 · Product Owner

**Refuses to ship without:** a measurable answer to "what does the user do that they cannot do
today?" and a reason it is worth the risk to the fence.

The user's job today is **read → chat → wait → read again**. The missing verb is **change**. Every
feature here serves that verb:

| User story | Today | After |
|---|---|---|
| Fix a typo in a notebook cell | write a prompt, wait for a turn | place caret, type, ⌘S — ~3 s |
| Rename a variable across a cell | prompt, hope the agent scopes it | multi-cursor / find-and-replace |
| Add a markdown heading | prompt | `+ markdown` cell, type |
| Review what the agent changed | read the transcript, guess | see the diff, accept per hunk |
| Undo something stupid | impossible | undo, or restore the draft |

**The risk to the fence** is the product decision. We are adding a second way to write bytes. The
PO position: the fence was never the product — **the promise** is. The promise is *"nothing outside
your working folder changes without your approval, and you can always see what changed."* A fenced
editor strengthens that promise (it makes the agent's changes reviewable). An unfenced one would
break it. So: build it fenced, or do not build it.

**What the PO will not accept:** an editor that is "read-only until the agent approves". It treats
the human as the less-trusted client and it will be used once and abandoned.

---

## 2 · Full Stack Developer

**Refuses to ship without:** a seam between the editor library and the app, and no per-keystroke
React work.

The two failure modes of "add an editor to a React app":

```
wrong                                   right
─────                                   ─────
<Editor value={text} onChange={setText}/>   host.setValue(text) once on open
  → every keystroke: setState              → keystrokes stay inside CodeMirror
  → parent re-renders                     → React sees only: dirty, value-on-save
  → transcript re-renders                 → 0 renders while typing (ED-2)
  → cursor jumps on remote update         → no controlled-component problem at all
```

So the `EditorHost` interface ([03](03-architecture.md#component-model)) has exactly five methods
and the app never imports `@codemirror/*` outside `web/src/editor/`. A lint rule enforces it.

**Also refuses:** a save route that re-implements path logic. The route calls `check_path`. A test
mutates `check_path` to always-deny and requires the route to obey — if that test passes by luck
because the route has its own check, the mutation would not change the outcome, so the test is
written to assert the *call*, not just the result.

---

## 3 · Database Expert

**Refuses to ship without:** knowing that "save" here is not a database transaction, and saying so.

This lens is the one that stops the spec from over-claiming. The workspace API:

- has **no `If-Match` / no conditional import**;
- gives `modified_at` and `size` in `get-status`, which are *observations*, not locks;
- has `import` with `overwrite=true`, which is **last-write-wins**.

Therefore:

| Claim we could make | True? | What we say instead |
|---|---|---|
| "Optimistic locking prevents lost updates" | **No** — a TOCTOU window remains | "Conflicts are detected immediately before the write; an undetected conflict is always recoverable" |
| "The save is atomic" | Yes, per object | keep it: `import` replaces the object or fails |
| "Two writers cannot corrupt a file" | **Yes** for whole-object replace — no interleaving of bytes | keep it, and test it (CX-4) |
| "We version history" | **No** — the workspace API keeps notebook revisions, files do not | "Notebook revision history comes from Databricks; files rely on the local draft" |

This lens also owns the **partial-write** question for notebooks: since we import a whole object,
a notebook save is all-or-nothing at the object level, which is stronger than a per-cell save would
have been. That is a reason *not* to build per-cell saving.

---

## 4 · UX and UI designer

**Refuses to ship without:** the fence visible before the first keystroke, and no modal for
something the user can still see.

Three UX rules that come straight from the axioms:

1. **The fence is ambient, not an error.** WR-5. A chip in the editor bar
   (`⌂ in fence ✓` / `⚠ outside fence` / `◼ read-only`), always present, never a dialog. You should
   never discover the fence by being blocked.
2. **A conflict is a choice, not a verdict.** CX-3. Three buttons — keep mine / take theirs / show
   the diff — with both versions readable. Never "your changes were discarded".
3. **Unsaved text is not a question.** UX-6. No "are you sure?" prompt on a buffer the user can see.
   Keep it, mark the tab, offer recovery. A confirmation dialog for text on screen is an admission
   the app was about to lose it.

The **empty state of a cell** matters more than it looks: an empty code cell must show a caret, not
a placeholder that disappears on click (that is a 1-line layout shift and a moment of doubt).

---

## 5 · Front-end designer

**Refuses to ship without:** the editor looking like it belongs to *this* app, not like a library
dropped in.

CodeMirror ships with its own theme system and its own defaults. Left alone it will look like a
different product: different font metrics, different selection colours, different scrollbars. The
binding rules:

- **One type scale.** The editor uses the same `--mono` and the same 12.5 px as `.code` today. A
  different size in the editor than in the transcript is immediately visible when you diff them.
- **One token set.** Syntax colours come from the theme tokens (`--blue-600`, `--green-700`, …), not
  from a bundled editor theme, so dark mode is inherited rather than hand-built twice.
- **One geometry.** Indent guides, the active line, the selection and the caret all use the existing
  `--line` / `--surface-*` / `--blue-*` values. `audit:a11y` must keep passing in both themes.
- **No CLS.** The pane is reserved before the editor mounts (lazy chunk), so opening a document adds
  0 shift. `audit:cls` stays at 0.0000.
- **The cell gutter is ours**, not the editor's: it carries the run affordance, the index, and the
  "agent wrote this" attribution. That is product surface, not editor chrome.

---

## 6 · VS Code expert

**Refuses to ship without:** the keys people's hands already know, and honest capability boundaries.

| Key | Expected behaviour | Notes |
|---|---|---|
| `⌘S` | save | must not require focus in a specific sub-element |
| `⌘Z` / `⇧⌘Z` | undo / redo | per document, survives a tab switch |
| `⌘F` | find in document | CodeMirror search panel, restyled |
| `⌘G` | go to line | |
| `⌥↑` / `⌥↓` | move line | |
| `⇧⌥↑/↓` | duplicate line | |
| `⌘/` | toggle comment | language-aware, via the parser |
| `⌘D` | select next occurrence | |
| `⇧⌘K` | **ask the agent about the selection** | our own, and the reason we are not VS Code |
| `⌘↵` | run cell (notebook) | |
| `⌘P` | open by name | already exists |
| `Tab` / `⇧Tab` | indent / outdent **in a list** | |

**What a VS Code expert will flag immediately, and where we agree:**

- **No LSP.** So no "go to definition", no type hover, no real diagnostics. We say so in the UI
  rather than shipping a half-working hover. The substitute is *catalog-aware* completion: table and
  column names from Unity Catalog, which is the one thing our editor knows that VS Code cannot.
- **No extension model.** Out of scope; a plugin API is a different project.
- **`⌥↑` on a cell boundary** must move the cell, not the line — a rule that only exists because we
  have cells. This is documented in [06 B4](06-edge-cases-testing.md#b-the-notebook-surface).

---

## 7 · AI engineer

**Refuses to ship without:** the agent's proposals being reviewable, and the agent *knowing* what
the user is editing.

Two integration points, both of which exist only because we own the editor:

**(a) Selection as context.** `⇧⌘K` sends the selection *plus* its cell index, language and the
document path to the agent, so "explain this" means the lines you highlighted, not the whole file.
This is strictly better than attaching the whole notebook, and it is cheap because we own the buffer.

**(b) Proposal, not write.** When an agent write targets a document the user has open, it becomes a
diff ([03](03-architecture.md#both-writers-one-model)). The agent is told this in its tool result:
*"proposed — awaiting review"* rather than *"written"*. An agent that thinks it wrote when it
proposed will produce a confident, wrong summary, so the tool result must be honest.

**What this lens refuses:** letting the agent see unsaved buffer content without the user knowing.
The buffer is local until saved; if the agent needs it, that is an explicit "send my unsaved change"
action. Implicit sharing of unsaved text is a data-handling surprise.

---

## 8 · Compiler expert

**Refuses to ship without:** a parse that is total, and a round trip that is exact.

The `notebook.py` parser is already written to be total ("Never raises on odd input"). The
serializer must be its exact inverse, and that is a property, not a test case:

```
∀ t ∈ SOURCE documents:   serialize(parse(t)) ≡ t
∀ c ∈ cell lists:         parse(serialize(c)) ≡ c   (modulo id regeneration)
```

The failure mode this prevents is subtle and severe: **an editor that silently reformats a notebook
on open-and-save**. The user opens, changes nothing, saves, and the file's bytes changed. That is a
fake diff in Git, a lost comment alignment, and a loss of trust. So:

- The serializer must preserve the header line, the exact separator (`# COMMAND ----------`), blank
  lines around separators, magic prefixes per line, and the language's comment character.
- A cell whose source ends with a trailing newline must not gain or lose one.
- An empty notebook must round-trip to the same empty notebook.
- A notebook with a cell containing the separator string **inside a string literal** must not be
  split (the parser must be aware it is inside `"""…"""`).

That last one is a genuine compiler-grade problem and is listed as edge case
[A3](06-edge-cases-testing.md#a-the-write-path-and-the-fence). It is the one place where a regex-based
approach will quietly corrupt a document.

---

## Where the lenses disagree

| Tension | Lenses | Resolution |
|---|---|---|
| "Run the cell here, it is faster" | UX ↔ Compiler/AI | **Agent path only.** A second executor needs a second fence; NB-6 forbids it. The run affordance triggers the agent's tool, which shows the evidence. |
| "Full IntelliSense" | VS Code ↔ Front-end | **No LSP.** Catalog-aware completion only. Shipping a fake hover is worse than no hover. |
| "Warn before closing a dirty tab" | UX ↔ Front-end | **No dialog.** Keep the draft, mark the tab. UX-6. |
| "Lock the file while editing" | DB ↔ UX | **No lock.** It cannot be enforced server-side, and a lock that does not hold is worse than none. Draft + conflict UI instead. |
| "Make the agent's write instant, it is inside the fence" | AI ↔ PO | **Proposal for open documents only.** Silent-write is fine when nobody is looking; catastrophic when someone is. |
| "Monaco has everything" | VS Code ↔ Front-end | **CodeMirror 6.** 101 MB vs 1.9 MB unpacked for features we would not use ([07 D1](07-decisions-risks.md#d1-codemirror-6-not-monaco)). |

---

## SOLID applied

Not as a checklist, but where each principle actually bites:

- **S**ingle responsibility: `domain/notebook.ts` parses and serializes; it does not fetch, render, or
  decide policy. `domain/fence.ts` mirrors policy; it does not write.
- **O**pen/closed: adding a language is a parser registration, not a change to the editor component.
- **L**iskov: any `EditorHost` implementation (CodeMirror, a textarea stub for tests, a future engine)
  satisfies the same five-method contract, so tests can substitute it.
- **I**nterface segregation: `EditorHost` is deliberately tiny. There is no `EditorHost` with 40
  methods where callers use three.
- **D**ependency inversion: the app depends on `EditorHost` and `WorkspaceBrowser` abstractions, not on
  CodeMirror or `httpx`. Both are injected at the edges.

### DRY, concretely

Three places where duplication would be tempting and is forbidden:

1. **The fence.** Client and server must not have two implementations of *policy* — the client one is
   a display mirror, and a test asserts agreement over a corpus.
2. **The serializer.** It exists once, in `api/domain/notebook.py`, and the front end calls it (or
   mirrors it with the shared corpus test). Two serializers is two chances to corrupt a notebook.
3. **The cell model.** One `Cell` type, shared by the agent's `dbx_write_notebook` payload, the parser,
   the editor, and the diff. A second "editor cell" type would drift.

[Next: the implementation plan →](05-implementation-plan.md)
