# 01 · Current state, and what blocks this

[Index](README.md) · prev: [00 Why](00-why-first-principles.md) · next: [02 Architecture](02-architecture.md)

Measured in the repository, not inferred. Every line reference is to `apps/coding-agent`.

---

## What exists after 003

| Piece | State | Reusable? |
|---|---|---|
| Notebook model + exact round trip | `api/domain/notebook.py`, `web/src/domain/notebook.ts`, 69 property tests across both | **yes** — it is the projection format |
| The write fence | `api/domain/scope.py`, `api/domain/approval.py`, mutation-tested | **yes** — orthogonal to merge |
| Fenced save route | `POST /api/workspace/save`, version token, 409 path | **partly** — the route survives as the *export*; the version check dies |
| Conflict UI | `web/src/components/ConflictPanel.tsx` | **deleted** |
| Draft store | `web/src/domain/drafts.ts`, TTL + cap + debounce | **yes** — it is the undo for C4 |
| Editor seam | `web/src/editor/host.ts`, 5 methods, CodeMirror behind it | **yes** — `y-codemirror.next` goes behind the same interface |
| Event vocabulary | `document.saved` added, parity-tested in both languages | **yes** |

That is a better starting point than it looks: the two things hardest to retrofit — an exact
notebook round trip and a write fence — already exist and are tested.

---

## What does not exist, and is required

### The websocket question

**This is unverified and it is the first blocker.** Databricks Apps serves the API through a platform
proxy. Whether that proxy carries a WebSocket upgrade, and whether it buffers frames, decides the
transport — and C5 makes the transport part of the correctness argument.

Evidence so far: **none**. The app uses SSE (`GET /api/sessions/{id}/stream`), which is not a
websocket, so the platform's behaviour with one is unknown. There is no `websocket` import anywhere
in `api/`
```
$ grep -rn "websocket\|WebSocket" api/  →  no matches
```

The probe in [README §The first probe](README.md#the-first-probe-before-any-code) settles it. **Do not
start phase 2 before it returns.**

### No durable store

`api/main.py` wires exactly one store:

```python
store = MemoryEventStore()
```

There is no Postgres adapter, no `psycopg`, no Lakebase client anywhere in `api/` — confirmed by
grep. 003's `MemoryEventStore` is honest for a transcript, which can be rebuilt by replaying turns.
**A CRDT cannot be rebuilt**: unreplayed updates are lost and replicas diverge permanently. So this
spec must add durable persistence, and it must be the first infrastructure task, not a later one.

### No Python CRDT runtime pinned

`pycrdt` 0.14.13 (Yrs bindings) and `pycrdt-websocket` 0.16.8 both require **Python ≥ 3.11**; the
venv is 3.12, so they are candidates. Neither is in `requirements.txt`, and `requirements.txt` is
**load-bearing**: the app crashed on its first deploy with `ModuleNotFoundError: pydantic_settings`
because `pyproject.toml` alone installs nothing
(`tests/test_packaging.py` enforces the file). Any new dependency must land in **both** files or the
deploy fails.

### The agent emits whole files

`tools/databricks_notebook_mcp.py` exposes `dbx_write_notebook(path, cells, source, language)` and
`dbx_write_file(path, content, overwrite)` — both whole-object writes. There is no operation-level
tool. C1 says this is the work.

---

## The write mechanics, as measured

These were discovered by running against the workspace, and they constrain the projection layer:

| Behaviour | Evidence |
|---|---|
| `overwrite` **cannot** be combined with `format=SOURCE` | `INVALID_PARAMETER_VALUE: Overwrite cannot be used for SOURCE format when importing a folder.` |
| Therefore an overwrite is **delete, then import** | implemented in `workspace.py::import_source`, tested in `tests/test_workspace_write.py` |
| After that delete, `language` is **required** | without it: `BAD_REQUEST: The zip archive contains no items.` |
| A notebook's `get-status` reports **`size: 0`** | so the version token had to drop `object_id` and rely on `modified_at` |

**Consequence for export:** every export is a delete-then-import, which means for a brief window the
object **does not exist**. A reader in Databricks during that window sees a missing notebook. The
export must therefore be:

1. write to a temp path (`<path>.exporting`),
2. delete the original,
3. rename the temp into place — or, if rename is unavailable, import directly and accept the window.

This is a real, user-visible consequence of C6 and belongs in the UI ("saving…" state), not in a
comment.

---

## What 003 learned that carries over

Three defects found while building the editor, all relevant here:

1. **Two `⌘S` handlers caused a double save**, and the second raced the first into a 409. A CRDT
   makes this harmless (idempotent re-send) but the *pattern* — one key, one owner — still applies to
   any new transport.
2. **A stale version token made every first save 409.** The root cause was a prop captured at mount.
   In this design the equivalent bug is a **stale state vector**, which is worse: it causes silent
   divergence rather than a visible error. Hence the sync-on-connect assertion in
   [04 A](04-edge-cases-risks.md#a-convergence-properties).
3. **A fresh document showed as dirty** because adopting a value fired the change callback. Here the
   equivalent is a **remote update echoed back as a local edit**, which causes an update storm. The
   fix is the same in spirit: distinguish `origin`.

---

## Cost, against what exists today

| Metric | Now | After |
|---|---|---|
| Bundles | `index` 98 KB gz + `codemirror` 228 KB gz (lazy) | `+ yjs/y-protocols ≈ 60–80 KB gz` (lazy with the editor) |
| Processes | 1 FastAPI | 1 FastAPI (websocket in-process) |
| Durable stores | 0 (memory only) | 1 (Lakebase: update log + snapshots) |
| Write tools | 2 whole-file | 7 (2 whole-file + 5 operation-level) |
| Requirements with tests | 003's set | 003's set minus CX, plus convergence properties |

[Next: the architecture →](02-architecture.md)
