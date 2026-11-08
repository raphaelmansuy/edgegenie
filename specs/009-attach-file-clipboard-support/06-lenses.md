# 06. Six lenses

**The same feature seen by six owners, and what each one vetoes.**

The rule for this document: a lens that agrees with everything is not a lens. Each section ends with a
**veto** — a thing that must be true or that owner blocks the work — and each veto is traceable to a
requirement or an edge case.

Spec [009](./README.md) · requirements [03](./03-requirements.md) · edge cases [09](./09-edge-cases.md)

---

## 1. Product Owner

**What I am buying, in one sentence:** a user can show the agent what they are looking at, in one
keystroke, without leaving the conversation — and the agent's answer proves it saw the right thing.

### The value, ranked

| # | Value | Why it beats the alternative |
|---|---|---|
| 1 | **One keystroke, no modal** | Every competitor's attach flow is a picker. `⌘V` is the whole feature. |
| 2 | **Evidence the agent saw it** | The evidence row naming the image is the product's thesis, applied to a new input |
| 3 | **Refusal that teaches** | "Images need a vision model" is a *sales* sentence: it names the upgrade path |

### What I refuse to ship

| Not shipping | Because |
|---|---|
| Attaching a file silently writes it to my workspace | Clutter the user did not ask for; also a fence violation ([SEC-2](./03-requirements.md)) |
| An "Attached!" toast with no thumbnail | I cannot verify what I attached; the chip must show the picture |
| A generic "Upload failed" | A support ticket, not an error message ([AFC-16](./03-requirements.md)) |

### Success measure

> After this ships, a session that includes an image attachment should produce a turn whose evidence
> names the image, and the user should not have to type the word "screenshot" to achieve it.

### Veto

> **If a pasted image requires more than one action from the user, the feature has no value over
> "save it, then `@`-attach it".** The one-keystroke path must work end to end, and
> [S2](./10-e2e-plan.md) is the acceptance.

---

## 2. Full Stack Developer

**What I am actually writing.** Not "an upload feature" — five small pieces and one deletion.

```
web/src/domain/blob.ts          pure: validate(file) → {ok} | {refused, reason}; nameFor(file)
web/src/components/AttachMenu.tsx   the + menu (new, ~90 lines)
web/src/components/Chip.tsx      extracted from Composer.tsx, now renders 4 states
web/src/hooks/useBlobUpload.ts   paste/drop/pick → chip state machine
api/domain/blob.py               Blob, BlobError, validate(), sanitise_name(), LIMITS
api/ports/__init__.py            + BlobStore, BlobReader protocols
api/adapters/blob/memory.py      in-memory store (tests)
api/adapters/blob/files.py       file-system store (dev)
api/services/blobs.py            put/get/materialise; the only place that touches storage
api/routers/api.py               + POST /api/blobs, GET /api/blobs/{id}, POST /api/blobs/{id}/materialise
api/services/context.py          + one branch: kind == "blob"
mcp/databricks_notebook_mcp.py   + dbx_read_blob
```

**The deletion:** `Composer.tsx` currently owns the chip markup inline (lines 21–31). It moves to its own
file and gains states, which *reduces* Composer's length even as the feature adds capability.

### What makes this cheap

| Reused, not rebuilt | Existing symbol |
|---|---|
| Upload validation | pattern of `ImportObject` + `_guard` + `exists` |
| The fence decision | `POST /workspace/fence` → `scope.check_path` |
| Approval token | `approval.issue/verify`, bound to path+version |
| Untrusted-content fencing | `context.render()` — the blob branch returns `Resolved` |
| Chip rendering | `.ctx-chip` CSS, `KIND_ICON` |
| Error surface | `composer-error` with `role="alert"` |

### What I refuse to do

| Refused | Because |
|---|---|
| A second upload mechanism beside `/workspace/import` | Two paths to bytes = two places to get validation wrong (DRY) |
| A `useEffect` that uploads on chip mount | Effects that fire requests are how duplicate uploads happen |
| Base64 in the SSE event | It would inflate every replay; the event names the blob, nothing more |

### Veto

> **If any byte-validation rule exists in both `blob.ts` and `blob.py`, I refuse.** The client's rule is a
> courtesy that must produce the *same sentence* as the server's, and the sentence is generated once
> ([09 §copy](./09-edge-cases.md#the-copy-register)). A test asserts the two tables match.

---

## 3. Database Expert

**What is persisted, and what is not.** The answer is deliberately small.

### Persisted

| Store | What | Why there |
|---|---|---|
| `llm.*` schema (existing Postgres) or a file directory | blob **metadata + bytes** | already the durable store for this app's state |
| `events` table (existing) | `blob.attached` event | the transcript must replay without a second source |
| `turn.attachments` (existing JSON) | `{kind:"blob", ref:blobId, name}` | **no schema change** |

### Not persisted

| Not persisted | Why |
|---|---|
| The image bytes in the event log | 40 KB × every replay ([BLB-2](./03-requirements.md)) |
| The prompt containing the image | derived on every turn from the blob; storing both is a second source of truth |
| A `blobs` table in Unity Catalog | a later `BlobStore` implementation; the port exists so it is additive |

### Indexes that matter

| Query | Frequency | Index |
|---|---|---|
| `meta(blob_id)` | every turn with an attachment | primary key |
| `refcount(blob_id)` | every sweep pass | `TURN_ATTACHMENT(blob_id)` |
| `sweep(now)` | hourly | `BLOB(state, created_at)` |
| `list(session_id)` | on session open | `BLOB(session_id, created_at)` |

### The one migration

```sql
-- only when the third (Postgres) implementation lands; the memory and file stores need none
CREATE TABLE blobs (
  id            TEXT PRIMARY KEY,
  session_id    TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  user_id       TEXT NOT NULL,
  original_name TEXT NOT NULL,
  stored_name   TEXT NOT NULL,
  mime          TEXT NOT NULL,
  bytes         INTEGER NOT NULL CHECK (bytes > 0),
  sha256        TEXT NOT NULL,
  storage_key   TEXT NOT NULL,
  state         TEXT NOT NULL CHECK (state IN ('pending','ready','attached','swept')),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  attached_at   TIMESTAMPTZ
);
CREATE INDEX blobs_sweep ON blobs (state, created_at);
CREATE TABLE turn_attachments (
  turn_id      TEXT NOT NULL,
  blob_id      TEXT NOT NULL REFERENCES blobs(id),
  display_name TEXT NOT NULL,
  position     INTEGER NOT NULL,
  PRIMARY KEY (turn_id, blob_id)
);
CREATE INDEX turn_attachments_blob ON turn_attachments (blob_id);
```

`ON DELETE CASCADE` on `session_id` is the one decision with teeth: **archiving a session must not orphan
bytes.** [BLB-3](./03-requirements.md) depends on it, and [E-9](./09-edge-cases.md) tests it.

### Veto

> **If a sweep can delete a blob referenced by a turn, I refuse.** The refcount must be computed from the
> join table in the same transaction as the delete, and a test must attempt exactly that race.

---

## 4. UX Designer

**What the user must be able to predict.** Not "what it looks like" — what happens next.

### The three predictions

1. **"If I press ⌘V, it attaches."** Nothing else. No modal, no confirmation.
2. **"If it is refused, I am told why, in words I can act on."** The sentence names the value and the
   limit.
3. **"If I send it, I can still see it."** The chip is in the transcript, with the picture.

### Flow, and where it must not interrupt

```
  intent: show the agent this picture
      │
      ├── ⌘V ────────────────▶ chip (0 ms) ──▶ ready (1 s) ──▶ send
      │                          ▲
      │                          └── the ONLY moment the user waits is if they
      │                              press send before "ready" — and then the Send
      │                              button says why, rather than doing nothing.
      │
      └── if refused ─────────▶ sentence + one action, and the message is preserved
```

### What I refuse

| Refused | Because |
|---|---|
| A modal preview | The user is mid-sentence; a modal steals the caret |
| The chip pushing the textarea | It goes **above** the field, in the existing `ctx-row` slot |
| A progress bar as the only signal | Progress plus a word, so it survives a colour-blind check |
| "×" on a `pending` chip | A half-uploaded file the user cannot finish is a trap |

### Veto

> **If the composer's resting height changes by even 1 px when the `+` button is added, I refuse.**
> Measured by [S10](./10-e2e-plan.md): the composer box's height at 1440, 1180, 900, 760, before and
> after, must be identical.

---

## 5. Front-end Developer

**What I am building, technically.** The parts that are easy to get subtly wrong.

### The paste handler

```ts
// the ONLY correct shape: check first, preventDefault only when we will handle it
onPaste={(e) => {
  const files = Array.from(e.clipboardData?.files ?? []);
  if (files.length === 0) return;         // text paste is untouched (AFC-1)
  e.preventDefault();
  void attach(files);                     // synchronous chip, async upload (P8)
}}
```

Three ways to get this wrong, all of them shipped by real products:

| Wrong | Symptom |
|---|---|
| Always `preventDefault()` | Pasting text into the composer stops working |
| `await` before adding the chip | The UI freezes for the duration of the upload |
| Reading `clipboardData` after the event | `clipboardData` is empty outside the handler |

### The chip's state machine, in React terms

```
const [chips, setChips] = useState<Chip[]>([])   // Chip = {key, file?, blob?, state, reason?}
```

One reducer, four transitions, **no effect that uploads**. The upload is started by the event handler and
reports back into the same setter. This is what prevents the double-upload that a `useEffect([file])`
always eventually produces in StrictMode.

### Rendering cost

A chip row with 6 chips re-renders on every keystroke if `Composer` passes a new array each render. The
chip is `memo`'d on `{key, state, name}`, and `attach` is `useCallback`'d — the same discipline the file
already applies to `Chip`.

### Accessibility specifics

| Element | Requirement |
|---|---|
| `+` button | `aria-haspopup="menu"`, `aria-expanded`, 24×24 |
| Menu | `role="menu"`, rows `role="menuitem"`, Escape closes and returns focus to `+` |
| Chip remove | `aria-label="Remove report.png"` |
| Drop zone | `aria-describedby` → live region "drop to attach" |
| Failure | `role="alert"`, `aria-live="assertive"` (it needs interrupting: the send is blocked) |

### Veto

> **If an image is rendered by putting its bytes in a `data:` URL in the DOM, I refuse.** A 8 MB data URL
> in the transcript is a memory leak per turn. Thumbnails come from `GET /api/blobs/{id}?thumb=1` at
> 40×40, cached by the browser, and the full bytes are never in the DOM.

---

## 6. Marketing and Growth

**What this unlocks, stated without adjectives.**

### The demo that was impossible

> "Watch — I paste the dashboard, ask why the number dropped, and the answer cites the chart." — nine
> seconds, one keystroke, no setup.

Before this, the equivalent demo required saving a file, importing it, searching for it, and attaching
it: four interactions a viewer stops following after two.

### The claim it lets us make, honestly

| Claim | Backed by |
|---|---|
| "Show it, don't describe it" | [S2](./10-e2e-plan.md): paste → answer, one keystroke |
| "It proves what it read" | the evidence row naming the image ([AFC-15](./03-requirements.md)) |
| "It will not lie about a file it cannot read" | [E-8](./09-edge-cases.md): the refusal is in the prompt *and* the evidence |

That third claim is the marketable one: every competitor's agent will happily hallucinate about an image
it never received. A visible "could not read" is a trust artifact.

### What I will not let the feature say

| Not claiming | Because |
|---|---|
| "Supports any file" | the capability matrix is the truth ([CAP-1](./03-requirements.md)) |
| "Understands PDFs" | we text-extract; the model does not see the page |
| "Screenshots are private" | they leave the workspace to reach the model; the copy must say so exactly as the existing egress notice does |

### Veto

> **If the accepted-file copy promises a type the capability matrix refuses, I refuse to publish it.** The
> picker's `accept` attribute, the drag-over text, and the marketing page must be generated from the same
> table, or they will drift within one release.

---

## The vetoes, collected

Six owners, six refusals, all testable:

| # | Owner | Veto | Test |
|---|---|---|---|
| V1 | Product | one keystroke end to end | [S2](./10-e2e-plan.md) |
| V2 | Full stack | one source for validation copy | `test_blobs.py::test_copy_tables_match` |
| V3 | Database | no sweep of a referenced blob | `test_blobs.py::test_sweep_respects_refcount` |
| V4 | UX | composer height unchanged | [S10](./10-e2e-plan.md) |
| V5 | Front-end | no data-URL images in the DOM | [S5](./10-e2e-plan.md) |
| V6 | Growth | copy generated from the matrix | `test_capability_matrix.py` |
