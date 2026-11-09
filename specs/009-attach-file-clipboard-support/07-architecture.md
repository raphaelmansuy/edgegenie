# 07. Architecture and decisions

**Where each rule lives in the code, and why there.** The decisions `[D1..D12]` are defined here and cited
everywhere else.

Spec [009](./README.md) · requirements [03](./03-requirements.md) · diagrams [05](./05-diagrams.md) ·
plan [08](./08-implementation-plan.md)

---

## [D1] One stage added, none replaced

**Decision.** Bytes get a *stage* — `BlobStore` — rather than a second upload route or a widened
`Attachment` kind with content inline.

**Why.** [02 §the gap](./02-grounding.md#the-gap-stated-as-a-diff) shows the only path from clipboard to
session today runs through "become a workspace object". Adding a store beside it is additive; widening
`Attachment` to carry content would change the type used by five existing code paths and make every one of
them responsible for size and validity.

**Rejected alternatives.**

| Alternative | Why not |
|---|---|
| POST base64 straight into `/messages` | Every message becomes an upload; retries re-upload; the event log carries bytes |
| Write to workspace, then attach as `file` | Pollutes the workspace ([SEC-2](./03-requirements.md)); unreadable as binary ([02 §Experiment 2](./02-grounding.md#experiment-2--what-does-the-viewer-return-for-a-png)) |
| A new endpoint that does both | Two validation paths, one of which will drift |

**Consequence.** `BlobStore` is a port ([BLB-5](./03-requirements.md)); the in-memory implementation is
what the tests use, and it is the reference for any future one.

---

## [D2] A blob is a row first, a path second

**Decision.** A blob exists in the store with an opaque id before *anything* is written to the workspace.
Writing to the workspace is a separate, explicit action.

**Why.** [P5](./01-five-whys.md) and [P3](./01-five-whys.md): the turn must reference something durable,
and the fence must be consulted before any write. If the workspace write came first, the fence would be
consulted *after* the user had already committed to the action.

**Consequence.** The transcript's chip references `ref: "blb_7f3a"`, not a path. A blob that is later
written to the workspace keeps its id; the chip *also* records the path it was written to, as metadata.

---

## [D3] Bytes are validated on the server, not trusted from it

**Decision.** The server performs the authoritative validation, in this order, before storing anything:
size → magic bytes → declared-vs-detected MIME → name → emptiness → capability → count.

**Why.** [P1](./01-five-whys.md) and [SEC-3](./03-requirements.md). The browser's `File.type` is a
three-letter guess from a file extension.

**How.** A pure function in `api/domain/blob.py`:

```python
def validate(name: str, declared: str, raw: bytes, limit: int = MAX_BYTES) -> BlobSpec
```

Pure means: no I/O, no clock, no store. That is what makes it a property test rather than an integration
test — the same rule the repository already applies to `domain/notebook.py` and `domain/scope.py`.

**Magic bytes, the whole table** (a closed set is a security property, so it is enumerated, not sniffed):

| Family | Prefix | Verified as |
|---|---|---|
| PNG | `89 50 4E 47 0D 0A 1A 0A` | `image/png` |
| JPEG | `FF D8 FF` | `image/jpeg` |
| GIF | `47 49 46 38` | `image/gif` |
| WebP | `52 49 46 46 … 57 45 42 50` | `image/webp` |
| PDF | `25 50 44 46` | `application/pdf` |
| ZIP (for `.ipynb`) | `50 4B 03 04` | `application/zip` → parsed as JSON if the extension says notebook |
| Everything else | — | refused, naming what was detected or "unrecognised" |

**Why not a sniffing library.** `python-magic` reads its own config files, can return different answers on
different hosts, and would make the validation non-pure and non-testable. A closed table is auditable in one
screen and cannot surprise anyone on a new machine.

**Consequence.** [SEC-3](./03-requirements.md) is satisfied by a function that 40 unit tests can cover in
milliseconds.

---

## [D4] Limits are named numbers, not a feeling

**Decision.** Every limit is a module constant, exported, with the sentence that names it generated from
the same constant.

```python
MAX_BYTES          = 8 * 1024 * 1024     # per file
MAX_BYTES_TOTAL    = 24 * 1024 * 1024    # per message
MAX_ATTACHMENTS    = 6                   # blobs + references together (unchanged)
MAX_IMAGE_EDGE     = 2048                # px; larger images are downscaled for description
MAX_THUMB_EDGE     = 96                  # px; what the chip renders
```

**Why 8 MB.** A full-screen retina screenshot is 2–4 MB; a phone photo is 3–6 MB; a scanned A4 page at
300 dpi is ~6 MB. 8 MB covers the realistic cases and refuses the pathological one (a 60 MB RAW file) before
it reaches the network. It also matches the cap `FilesPane.tsx` already enforces (`file.size > 8_000_000`),
so the two paths state the same number. **That match is asserted by a test**, because two constants that
happen to be equal are two constants.

**Why 2048 px.** Vision models tile images into roughly 512 px patches; beyond ~2048 px the extra pixels
cost tokens and add nothing to a description of a chart's shape.

**Why not reuse `MAX_CHARS_TOTAL = 16_000`.** That budget is for *text in the prompt*. A blob does not
consume it — the prompt carries a manifest, not the bytes ([D8](#d8-references-not-bytes-on-the-wire)).

---

## [D5] A blob is written inside the fence, or not at all

**Decision.** `POST /api/blobs/{id}/materialise` calls `scope.check_path` exactly as `workspace_save` does,
and honours `ALLOW` / `ASK` / `DENY` with the same approval token bound to the same path.

**Why.** [P3](./01-five-whys.md). The fence is the product's central safety claim; a second write path that
skipped it would be a hole, and the hole would be found by whoever wanted it.

**How.** The route is a **thin caller**, in this order (copied from `workspace_save` deliberately):

```
1. sanitise the destination path          → 422
2. check_path(scope, path)                → DENY 403, ASK requires approval
3. verify approval bound to path+version  → 403
4. blob_store.get(id, user)               → 404 (existence not disclosed)
5. browser.import_content(path, bytes)    → whatever Databricks says
6. record document.saved in the event log
```

**Rejected alternative.** A branch inside `workspace_save` taking a `blobId` instead of `text`. It would
make one route responsible for two content sources, and the version-conflict logic (which is about text)
does not apply to a blob. Separate route, same fence.

---

## [D6] The transcript is the source of truth; the composer is a draft

**Decision.** Chips in the transcript are rendered from the turn's `attachments` (already persisted). Chips
in the composer are UI state, discarded on send.

**Why.** The composer's array is not durable, and duplicating it into the event log would create two
sources for the same list. The turn already stores `[{kind, ref, name}]`, and `blob` is the same shape.

**Consequence.** A reload shows the transcript's chips with no extra code ([AFC-8](./03-requirements.md)),
and the composer's row is empty after a reload, which is correct: there is nothing unsent.

---

## [D7] Capability is declared, not assumed

**Decision.** The model's ability to consume each blob family is a **declared property of the model spec**,
checked on the client (fast refusal) and on the server (authoritative refusal). A family no active model can
consume is not offered.

**Why this is the hardest decision in the spec.** [02](./02-grounding.md) shows both ACP call sites send
`{type: "text"}` and nothing else. There is no image block on this wire, and no binary read tool among the
27 tools. So "attach an image to a vision model" cannot mean "send the pixels to the model". It has to mean
one of three things, and the choice must be explicit:

| Option | What the model gets | Cost | Verdict |
|---|---|---|---|
| A. Send base64 in the prompt text | A wall of characters it cannot decode | tokens, no benefit | ❌ never |
| B. Extend the ACP wire with an image content block | Real pixels | requires the child agent to support it; not verifiable here | ⏸ not this spec |
| C. The server describes the image, and exposes the bytes to a tool | A description + a reference | one extra pass; honest about what the model saw | ✅ **this spec** |

**Decision: C, with B available where the agent supports it.** Concretely:

- `BlobReader` for an image family returns a `Resolved` whose text is a **manifest**: file name, verified
  MIME, pixel dimensions, byte length, sha256, and (when the workspace model has vision) a description
  produced by the vision model as a separate call. The description is labelled
  `model-description` ([AFC-10](./03-requirements.md)).
- `dbx_read_blob(blob_id, offset, max_chars)` lets the agent page through *text* families, and returns a
  manifest (never bytes) for binary ones ([AFC-14](./03-requirements.md)).
- The capability matrix in [03](./03-requirements.md) is generated from one table,
  `api/domain/blob.py::CAPABILITY`, which both the picker's `accept` list and the tests read.

**Option B is implemented — and it took two fixes.** Measured with a logging proxy between opencode
1.18.19 and the Databricks endpoint:

1. **opencode resolves capabilities on the CLIENT, before any request.** For a custom
   `@ai-sdk/openai-compatible` provider the default is `attachment: false`, so an attached image is
   rewritten into the literal text *"ERROR: Cannot read image (this model does not support image
   input)"* and never leaves the process. The fix is to declare it per model in the generated config:

   ```json
   "attachment": true,
   "modalities": { "input": ["text", "image"], "output": ["text"] }
   ```

   Both fields are required and neither is sufficient. `ModelSpec.sees_images` is their one source, and
   `agent_config.model_entry` is the one place that writes them.

2. **The manifest must not contradict the picture.** It said "you cannot see the pixels" for *every*
   image, so a model holding a perfectly good `image_url` block read the sentence instead and answered
   *"I can't see the image."* Whether the model can see is a fact about the MODEL, not about the blob's
   family; the sentence now depends on it, and on nothing else.

With both fixed, a solid-blue 64×64 PNG sent through opencode produced `Blue`, and the proxy recorded an
`image_url` part in the request: the pixels reached the model.

The limitation that remains is narrower and stated plainly. opencode's own `bash` and `read` tools are
denied by this app's least-privilege config, so an agent asked to look at a *path* (`./chart.png`) tries a
denied tool and gives up. An image **attached to the message** — which is what this feature sends — travels
correctly. On a text-only model the image is still accepted and labelled: the chip says "not visible to
this model" and the manifest says so too, because refusing would leave the user no way to hand the file
over at all.
[11 §what is not true yet](./11-outcome.md#what-is-not-true-yet) repeats this in the outcome document,
because a spec that hides its own limit is a trap.

---

## [D8] References, not bytes, on the wire

**Decision.** `POST /messages` carries `{kind: "blob", ref: "<blobId>"}`. The base64 crosses the wire exactly
once, into `/api/blobs`.

**Why.** [P6](./01-five-whys.md). A 40 KB image becomes ~54 KB of base64; storing that in the turn, the
event, and every replay multiplies it. The reference is 20 bytes.

**Consequence.** `ctx.parse()` gains one kind and one validation rule (a blob id matches `^blb_[0-9a-f]{12}$`),
and `Attachment` gains no new field. `render()` is unchanged in shape.

---

## [D9] The reader is a strategy, not a branch

**Decision.** What a *read* means for a blob is decided by a `BlobReader` chosen from the verified MIME
family — not by an `if` inside `resolve()`.

```python
READERS: dict[str, BlobReader] = {
    "image/*":  ManifestBlobReader(),      # manifest; bytes via tool only
    "text/*":   TextBlobReader(),          # decoded, capped, paged
    "application/pdf": PdfTextBlobReader(),# extracted text, capped
}
```

**Why.** [06 §Full stack](./06-lenses.md#2-full-stack-developer) veto V2: adding a family must not edit a
shared function. Open/closed, and it makes each reader separately testable against the same contract.

**Consequence.** `resolve()`'s blob branch is three lines: look up the reader, call it, wrap the result.

---

## [D10] The client validates a courtesy, the server validates a rule

**Decision.** `web/src/domain/blob.ts` implements the same checks as `api/domain/blob.py`, and a test asserts
the **copy tables** match — the sentence strings, not the implementation.

**Why.** [AFC-4](./03-requirements.md) needs a refusal with zero network latency (a 12 MB file should not be
uploaded to be rejected). But two implementations of one rule drift. The mitigation is that the *sentences*
are generated from one shared list, and a test fails if the two lists differ in length or content.

**Consequence.** The client file is ~60 lines and contains no policy the server does not also have.

---

## [D11] Thumbnails are served, not inlined

**Decision.** `GET /api/blobs/{id}?thumb=1` returns a ≤96 px image; the raw route is `/api/blobs/{id}` with
`Content-Disposition` per [SEC-4](./03-requirements.md). The DOM never contains a `data:` URL for user content.

**Why.** [06 §Front-end](./06-lenses.md#5-front-end-developer) veto V5. A transcript with ten 4 MB
attachments, each rendered from a data URL, is 40 MB of DOM strings per session, and every re-render copies
them.

**Consequence.** Thumbnails are cached by the browser (`Cache-Control: private, max-age=3600`) and cost one
small request per chip.

---

## [D12] Nothing new on the event vocabulary except one event

**Decision.** Add exactly one event type, `blob.attached`, carrying `{blobId, name, mime, bytes}` — no
content. Everything else reuses `turn.started` / `session.created` shape.

**Why.** `web/src/domain/events.ts` and `api/domain/events.py` must list the same types, asserted by
`test_event_parity.py`. Every added event is a parity risk and a reducer case. One event is the minimum that
lets the client show a chip before the turn's completion event arrives.

**Consequence.** Two files change (`events.ts`, `events.py`), one test extends, one reducer case is added.

---

## Where each decision lives

| Decision | Module | Symbol |
|---|---|---|
| D1 stage | `api/services/blobs.py` | `put`, `get`, `materialise` |
| D2 row-first | `api/domain/blob.py` | `Blob` |
| D3 validation | `api/domain/blob.py` | `validate`, `detect_mime` |
| D4 limits | `api/domain/blob.py` | `MAX_*` |
| D5 fence | `api/routers/api.py` | `blob_materialise` |
| D6 transcript truth | `web/src/components/Transcript.tsx` | existing `TurnView` |
| D7 capability | `api/domain/blob.py` | `CAPABILITY` table |
| D8 references | `api/domain/context.py` | `parse`, `Attachment` |
| D9 readers | `api/services/blobs.py` | `READERS` |
| D10 shared copy | `api/domain/blob.py` + `web/src/domain/blob.ts` | `REFUSALS` |
| D11 thumbs | `api/routers/api.py` | `blob_bytes` |
| D12 one event | `api/domain/events.py` + `events.ts` | `blob.attached` |

---

## Layering

```
  web/src/components/Composer.tsx        presentation only
  web/src/hooks/useBlobUpload.ts         the chip state machine, no fetch policy
  web/src/domain/blob.ts                 pure validation (courtesy)
  web/src/api/client.ts                  the only place that knows the URLs
        │
        ▼  HTTP
  api/routers/api.py                     thin: parse, delegate, translate errors
  api/services/blobs.py                  orchestration: validate → store → record
  api/services/context.py                resolve a reference into text (one new branch)
  api/domain/blob.py                     pure: validate, sanitise, capability (no I/O)
  api/ports/__init__.py                  BlobStore, BlobReader protocols
  api/adapters/blob/{memory,files}.py    implementations
```

The arrow only points down. `domain/blob.py` imports nothing from `services` or `adapters`; a test asserts
this with `ast` (the repository already does this for `domain/scope.py`).

---

## SOLID, point by point, with the file that demonstrates it

| Principle | Demonstration |
|---|---|
| Single responsibility | `domain/blob.py` (rules) ≠ `services/blobs.py` (orchestration) ≠ `adapters/blob/*` (storage) |
| Open/closed | a new family is a `BlobReader` registered once (`READERS`), no branch edited |
| Liskov | `test_blobs.py` runs the same contract against `MemoryBlobStore` and `FileBlobStore` |
| Interface segregation | `BlobReader` has one method; `BlobStore` has no read-of-content method |
| Dependency inversion | `resolve()` takes `dict[str, BlobReader]`; the router takes `BlobStore` from app state |

## DRY, point by point

| Duplication that is avoided | How |
|---|---|
| Upload validation | `validate()` is called by the router; the client's copy is generated from the same table and asserted |
| The fence | `materialise` calls `check_path`, it does not re-implement it |
| Untrusted fencing | `render()` is reused; the blob branch returns `Resolved` like every other kind |
| Chip rendering | one `Chip` component with four states, used by composer and transcript |
| Limits | one constant per limit; the error sentence interpolates it |
