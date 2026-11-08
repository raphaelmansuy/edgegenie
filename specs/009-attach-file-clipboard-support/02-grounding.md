# 02. Grounded assessment

**What is actually in this repository, counted, with the command that counts it.**

Every number below was produced by running the command shown. If a number here disagrees with the code,
the code is right and this file is stale — that is the rule for the whole set.

---

## The attachment path as it exists today

Traced end to end, so the plan in [08](./08-implementation-plan.md) has something to be a diff against.

### ASCII: the current path, one arrow per hop

```
 USER                    BROWSER                            SERVER                        DATABRICKS
  │
  │  drag a file onto Files pane
  │──────────────────────▶ FilesPane.onDrop
  │                          ├─ file.arrayBuffer()             (bytes in the DOM, briefly)
  │                          ├─ btoa(...)                      (base64 in a JS string)
  │                          ├─ importFormat(name)             (extension → format/language)
  │                          └─ api.importObject(here, name, b64, format, lang)
  │                                     │
  │                                     ├──▶ POST /workspace/import
  │                                     │      ├─ _ws_path(parent) + _named(parent,name)
  │                                     │      ├─ _guard(path, home)      ← protected-root check
  │                                     │      ├─ browser.exists(path)    ← refuse overwrite
  │                                     │      └─ browser.import_content(path, raw, format)
  │                                     │                    │
  │                                     │                    └──▶ POST /api/2.0/workspace/import
  │                                     │                                     (AUTO/SOURCE/…)
  │                                     └◀── 201 {path}
  │                          load(here)  ← the file is now a WORKSPACE OBJECT
  │
  │  click "@" → search → choose chip
  │──────────────────────▶ Composer.choose({kind:"file", ref:path})
  │                          onAdd → App.attachments: [{kind, ref, name}]
  │
  │  press Enter
  │──────────────────────▶ api.send(id, text, key, attachments)
  │                                     ├──▶ POST /sessions/{sid}/messages
  │                                     │      attachments: [{kind, ref}]  ← REFERENCES ONLY
  │                                     │      ├─ ctx.parse(raw)      ← 5 kinds, path regex, ≤6
  │                                     │      ├─ ctx_service.resolve(items, ws, cat, token)
  │                                     │      │    └─ ws.read(ref, USER TOKEN)  ← re-read
  │                                     │      └─ orch.submit(text, ctx.render(resolved), …)
  │                                     │              └─ <attached-context> … </attached-context>
  │                                     └──▶ session/prompt {type:"text", text}
```

**The load-bearing fact in that diagram:** the only way a byte reaches the model today is by first
becoming a workspace object. There is no path from "clipboard" to "session" that does not pass through
`/workspace/import` and then `@`-search. That is *why* nothing can be pasted: not a missing handler, a
missing **stage**.

### What exists, file by file

| Concern | File | Lines | What it does |
|---|---|---|---|
| Attachment vocabulary | `api/domain/context.py` | 126 | 5 kinds, `Attachment`, `parse()` validation, `render()` fencing, 3 limits |
| Reference → text | `api/services/context.py` | 56 | re-reads each ref with the user's token; per-item failure isolation |
| Upload (existing) | `api/routers/api.py` `workspace_import` | ~25 | base64 in, `_guard`, `exists`, `import_content` |
| Upload client | `web/src/api/client.ts` `importObject` | 3 | `POST /workspace/import` |
| Drop handler | `web/src/components/FilesPane.tsx` | 15 | `arrayBuffer → btoa → importObject`, 8 MB cap |
| Composer | `web/src/components/Composer.tsx` | 306 | textarea, `@` picker, `/` commands, chips, history |
| Chip | `Composer.tsx` `Chip()` + `.ctx-chip` | 12 + 9 | pill with icon, name, optional `open` tag, `×` |
| Wire type | `web/src/domain/events.ts` | 1 | `Attachment = {kind, ref, name}` |
| Prompt transport | `api/adapters/acp/runtime.py` | 6 | `{type:"text", text}` — **text only** |

### Counted

```console
$ rg -n 'KINDS = ' apps/coding-agent/api/domain/context.py
21:KINDS = ("notebook", "file", "folder", "table", "cell")

$ rg -n 'MAX_' apps/coding-agent/api/domain/context.py
21:MAX_ATTACHMENTS = 6
22:MAX_CHARS_EACH = 6_000
23:MAX_CHARS_TOTAL = 16_000
```

```console
$ rg -n 'type.:"text"' apps/coding-agent/api/adapters/acp/runtime.py
197:  {"sessionId": h.session_id, "prompt": [{"type": "text", "text": text}]},
218:  {"sessionId": h.session_id, "prompt": [{"type": "text", "text": text}]},
```

Both call sites send **one** content block, of type `text`. Whatever the model can see, it sees through
that string. This single fact drives [D7](#d7-capability-is-declared-not-assumed): a picture cannot be a
picture on this wire — it can only be a *description the server wrote about* the picture.

```console
$ rg -n 'MAX_READ_BYTES' apps/coding-agent/api/adapters/databricks/workspace.py
27:MAX_READ_BYTES = 400_000          # what the viewer shows; the agent has its own paged reader
157:    truncated = len(raw) > MAX_READ_BYTES
```

The viewer decodes bytes as UTF-8 with `"replace"`. A PNG read through this path becomes a string of
U+FFFD. That is why an image must never be attached as a `file` reference — the tool that reads it will
return garbage that looks like content.

### The tool surface the agent has

```console
$ rg -c '^def dbx_' mcp/databricks_notebook_mcp.py
27
```

27 tools. Relevant ones for attachments:

| Tool | Signature | Can it read a binary blob? |
|---|---|---|
| `dbx_read_notebook` | `(path, offset, max_chars)` | No — `export` `format=SOURCE`, decoded as text |
| `dbx_grep_notebook` | `(path, pattern, context)` | No |
| `dbx_list_notebooks` | `(path)` | Lists names only |

There is **no** `dbx_read_file`, and no tool takes a byte offset into a binary. So a blob written into the
workspace is *visible by name* and *readable as text*, and readable as text it is meaningless.

### The baseline the change must not regress

```console
$ cd apps/coding-agent && .venv/bin/python -m pytest tests -q
465 passed, 1 skipped, 16 warnings in 11.47s

$ cd apps/coding-agent/web && npx vitest run
Test Files  46 passed (46)
     Tests  512 passed (512)

$ npx tsc -b --noEmit
(no output)
```

And the audits this repository already runs on itself (from spec 007, re-verified in 009):

| Audit | Command | Baseline |
|---|---|---|
| Accessibility | `node scripts/a11y-audit.mjs` | 0 findings |
| Overflow | `WIDTHS=1480,1180,900 node scripts/overflow-audit.mjs` | 0 problems |
| Layout shift | `node scripts/cls-audit.mjs` | worst 0.0292 |
| Shell e2e | `node scripts/shell-e2e.mjs` | all passed |

---

## What the code makes easy, and what it makes hard

### Easy (reuse, do not rebuild)

1. **A validated-upload endpoint already exists** (`/workspace/import`) with a base64 body cap of
   12 MB, format validation, an overwrite refusal, and a protected-root guard. A blob upload is a second
   caller, not a second mechanism.
2. **The fence already has a verdict API** (`POST /workspace/fence` → `verdict`, `action`, `reason`,
   `approval`). Writing a blob inside the folder is `ALLOW`; outside is `ASK` with an approval token. The
   feature must *use* this, and gets the whole approval flow for free.
3. **`render()` already fences untrusted text** with `<attached-context>` and an explicit instruction to
   treat it as data. A new attachment kind inherits the warning by construction.
4. **The chip already renders any `{kind, ref, name}`** through `KIND_ICON`, with a title and a remove
   button. A new kind is an icon and a preview thumbnail.
5. **The event store is already a durable, sequenced log** (`EventStore.append` / `since`). A blob's
   lifecycle belongs there, not in component state.

### Hard (must be designed, not discovered)

| Hard thing | Why it is hard | Where it is decided |
|---|---|---|
| The wire has no image block | ACP `session/prompt` here sends `{type:"text"}` only | [D7](#d7-capability-is-declared-not-assumed) |
| No binary read tool | 27 tools, none takes a byte range | [D7](#d7-capability-is-declared-not-assumed) |
| `MAX_CHARS_TOTAL = 16_000` | A base64 image blows through it instantly | [D4](#d4-limits-are-named-numbers-not-a-feeling) |
| `read()` decodes UTF-8 | Binary becomes U+FFFD | [D3](#d3-bytes-are-validated-on-the-server-not-trusted-from-it) |
| References are trusted, bytes are not | The security model assumed no client content | [P1](./01-five-whys.md), [D3](#d3-bytes-are-validated-on-the-server-not-trusted-from-it) |
| The fence is path-based | A blob has no path until written | [D5](#d5-a-blob-is-written-inside-the-fence-or-not-at-all) |
| Chat apps set the expectation | Paste-anywhere, thumbnail, drag, reorder | [04](./04-wireframes.md) |

---

## Is the hard part actually hard? Three experiments

Rather than assume, I measured the three facts the design hinges on.

### Experiment 1 — does the workspace accept arbitrary bytes?

Read `workspace_import`: it base64-decodes, validates `format ∈ {SOURCE, HTML, JUPYTER, DBC,
R_MARKDOWN, AUTO}`, calls `browser.import_content(path, raw, format)`. `AUTO` is accepted. So **yes**: a
PNG can be written to the workspace today through the existing endpoint, with no new code. That is what
makes [D5](#d5-a-blob-is-written-inside-the-fence-or-not-at-all) cheap.

### Experiment 2 — what does the viewer return for a PNG?

`workspace.py:156` — `raw[:MAX_READ_BYTES].decode("utf-8", "replace")`. A PNG's first bytes
(`\x89PNG\r\n\x1a\n`) decode to `\ufffdPNG\r\n\x1a\n`, and the rest is replacement characters. So the
viewer path is **lossy and must not be used for blobs.** Blobs need their own read route that returns
bytes, or a thumbnail route. Recorded as [E-4](./09-edge-cases.md).

### Experiment 3 — can a size limit be enforced before the bytes are read?

`ImportObject.content: str = Field(min_length=0, max_length=12_000_000)`. Pydantic rejects the body before
any handler runs, so the cap is enforced by the framework, not by a check the handler might forget. That
pattern is reusable: the blob route declares its own `max_length`, and the *semantic* limit (a decoded
8 MB, not a 12 MB base64 string) is checked in the domain function that also names the limit in the error.

---

## The gap, stated as a diff

| Today | After 009 |
|---|---|
| 5 attachment kinds, all references | + `blob`, a reference to bytes the server holds |
| Bytes enter only via Files drag → workspace object | Bytes enter via paste, drag, or picker → blob store, then optionally the workspace |
| The model receives text from `render()` | The same, plus a real description of each image, and a `dbx_read_blob` tool for the bytes |
| No image on the wire, no binary tool | Capability is **declared per model** and the UI refuses what cannot work, with a reason |
| Client state holds the chips | Blobs are rows with an id; the turn references them; reload reproduces them |

The next document turns that diff into numbered requirements.
