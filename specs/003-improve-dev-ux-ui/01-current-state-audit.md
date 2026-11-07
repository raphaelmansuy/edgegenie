# 01 · Current state audit

[Index](README.md) · prev: [00 Why](00-why-first-principles.md) · next: [02 Requirements](02-requirements.md)

Everything here was measured in the repository, not inferred. Line references are to
`apps/coding-agent` unless stated otherwise.

## The editing surface today

| Property | Value | Where |
|---|---|---|
| Editor | none — a `<pre><code>` | `web/src/components/Viewer.tsx:16-19` |
| Caret / selection / undo | impossible | a `<pre>` has no editing model |
| Syntax highlighting | 5 token classes (comment, string, number, keyword, plain) | `web/src/domain/highlight.ts:5` |
| Languages highlighted | 4 — python, sql, scala, r | `highlight.ts:19-22` |
| Languages falling back to plain | everything else, including markdown, json, yaml, shell | `highlight.ts:40` |
| Bracket matching, indent guides, folding, multi-cursor | none | no such code exists |
| File size limit | 400 000 bytes, then truncated with a note | `api/adapters/databricks/workspace.py:27` |
| Save | does not exist | no route, no client call |
| Local draft / crash recovery | none | `localStorage` holds only theme, layout and a stream cursor |

### The highlighter, precisely

`highlight.ts` is 55 lines and one regex per language. It is honest about its limits and its tests
assert the property that matters most (`tokenize(x).map(t => t.text).join("") === x`, so highlighting
can never corrupt text). But a regex tokenizer cannot do what an editor needs:

- no **context** — a `"` inside a comment, or a keyword inside a string, needs parser state that a
  single alternation cannot carry across a multiline construct;
- no **nesting** — SQL `CASE` inside a subquery inside a string is one token;
- no **bracket matching**, because there is no token nesting to match;
- no **indent guides**, because indentation is never computed.

This is not a criticism of the module. It was built to decorate a `<pre>`, and it does that
correctly. It is simply the wrong class of tool for a caret.

## The notebook surface today

`NotebookViewer` maps `WsObject.cells` to static blocks
(`Viewer.tsx:95-102`). Each cell gets a gutter with its index and language, a copy button, and either
`<Markdown>` or `<Code>`.

| Capability a notebook needs | Today |
|---|---|
| Add a cell | no |
| Delete a cell | no |
| Move / reorder a cell | no |
| Change a cell's type (code ↔ markdown) | no |
| Run a cell | no (read-only by design) |
| Edit a cell | no |
| Select a range of cells | no |
| Render markdown when out of edit, edit when in | no — always renders |

The good news: the **data model already exists and is pure**. `api/domain/notebook.py` parses
SOURCE format into `Cell(index, kind, language, source, truncated)` and carries the magic handling
(`%md`, `%sql`, `%sh`, …) and the language comment prefixes per language. It is 60 lines, has no
I/O, and is the right foundation. What is missing is the **inverse** — serialization — and an
editing surface that can produce cells.

```
current                               needed
───────                               ──────
parse_source(text) -> [Cell]          parse_source  (exists)
          │                                     ▲
          ▼                                     │
   static render                          serialize(cells)
                                                ▲
                                          editor produces cells
```

## The write path today

```
                 ┌──────────────────────────────────────────────┐
  agent tool ───►│  tools/databricks_notebook_mcp.py            │
  (dbx_write_*)  │    _check_path_scope()  ──► scope.check_path  │──► workspace API
                 └──────────────────────────────────────────────┘
                                    ▲
                                    │  the ONE fenced door
                 ┌──────────────────┴───────────────────────────┐
  browser      ──┼─► POST /api/workspace/mkdir   (mkdir only)    │──► workspace API
                 └──────────────────────────────────────────────┘
```

Two facts, both load-bearing for this spec:

1. **The agent's writes pass through `scope.check_path`.** The tool server calls it; out-of-fence
   targets become `Verdict.ASK` and require an approval (`scope.py:120-125`).
2. **The browser can only create folders.** `POST /api/workspace/mkdir` is the sole write route from
   the UI (`api.py:378`), and its docstring states the rule: *"Creation only: the app never deletes
   or overwrites."*

So there is no unfenced web write **inside this app**. That is a genuinely good property and this
spec must preserve it exactly — the new save route must be a *third* call to the same function, not
a parallel implementation.

## The conflict surface today

`Doc` carries a `rev: number` (`web/src/domain/docs.ts:5`), and it looks like a version. It is not:

```ts
// App.tsx:157 — after a tool call wrote something, bump the local counter so the viewer reloads
setDocs((cur) => cur.map((d) => (written.some((w) => d.id === d.rev ... ) ? { ...d, rev: d.rev + 1 } : d)));
```

`rev` increments **only** when this browser notices that a tool wrote the file. It is never compared
against the server. A write from another tab, or from a person in the workspace editor, is invisible
until a manual reload — and today that is harmless precisely *because nobody can save*. The moment
editing exists, `rev` becomes the thing standing between the user and silent data loss. This is
[06 C1–C6](06-edge-cases-testing.md#c-concurrency-conflict-and-loss).

## What the Databricks workspace API gives us

| Need | Endpoint | Notes |
|---|---|---|
| Read a file/notebook | `GET /api/2.0/workspace/export?format=SOURCE` | already used; returns base64 |
| Read stats | `GET /api/2.0/workspace/get-status` | returns `object_id`, `language`, `size` |
| Write | `POST /api/2.0/workspace/import` | `format=SOURCE`, `overwrite=true` |
| Move / rename | `POST /api/2.0/workspace/delete` + import, or `create` + delete | **delete is required** — see [06 A5](06-edge-cases-testing.md#a-the-write-path-and-the-fence) |
| Version check | `object_id` + `size` + `modified_at` from `get-status` | **no ETag / no optimistic-lock header** |

The last row is the important one: **the workspace API has no conditional write.** There is no
`If-Match`. So optimistic concurrency has to be built on our side from `get-status` immediately
before the import, and even then it is time-of-check-to-time-of-use racy. This is a real constraint
on what "conflict detection" can promise, stated honestly in [07 R1](07-decisions-risks.md#r1-no-conditional-write-in-the-workspace-api).

## Where the cost actually is

| Concern | Weight | Why |
|---|---|---|
| Editor bundle | **decided** | CodeMirror 6 ≈ 1.9 MB unpacked for the packages we need; Monaco 101 MB ([07 D1](07-decisions-risks.md#d1-codemirror-6-not-monaco)) |
| Serialization round trip | **high** | must be exactly inverse or a save silently reformats a notebook |
| Concurrency | **high** | no server-side conditional write; we must design the guarantee we *can* keep |
| Fence as a second door | **highest** | the whole reason the viewer was read-only |
| Cell identity | medium | needed for per-cell diff and reorder; derives from the parser |
| Bundle size for the app | low | the editor is lazy-loaded per open document |
| Test surface | medium | property tests for round trip, e2e for the save path |

## What this audit changes about the plan

Three findings move the design:

1. **E7 is worse than it looks.** `rev` is not a version, so conflict handling is not "add a check",
   it is "design the guarantee". → [03 §Concurrency](03-architecture.md#concurrency-what-we-can-and-cannot-promise)
2. **The parser already exists and is pure.** We do not need a new document model; we need its
   inverse and a surface. → [03 §The document model](03-architecture.md#the-document-model)
3. **There is no server-side conditional write.** So a last-write-wins save is the only *honest*
   primitive available, and the product must make losing a write **visible and reversible** rather
   than claim to prevent it. → [06 C2](06-edge-cases-testing.md#c-concurrency-conflict-and-loss)

[Next: what must be true when we are done →](02-requirements.md)
