# 03. Requirements

**What must be true when this is done.** Every requirement has an id, a first principle it derives from,
and the test that proves it. A requirement without a test is a wish; there are none here.

Spec [009](./README.md) · why [01](./01-five-whys.md) · grounding [02](./02-grounding.md)

---

## How to read an id

| Prefix | Domain | Tested by |
|---|---|---|
| `AFC-` | Attach file / clipboard — the feature | backend unit + e2e |
| `BLB-` | Blob store — storage and lifecycle | backend unit |
| `CMP-` | Composer — the client surface | vitest + e2e |
| `CAP-` | Capability — what the model can actually do with it | backend unit + e2e |
| `SEC-` | Security — validation, fence, injection | backend unit |

Ids are defined **once**, here. Every other document cites them.

---

## The capability matrix [D7]

This table IS the requirement. It is derived in
[07 §capability](./07-architecture.md#d7-capability-is-declared-not-assumed), and it is the answer to
"what happens if I attach a PNG to a model that cannot see?" — **the picker refuses it, before the
upload, with a sentence.**

| Input | MIME family | Text models | Vision models | Max size |
|---|---|---|---|---|
| Screenshot, photo, diagram | `image/png`, `image/jpeg`, `image/webp`, `image/gif` (first frame) | ✅ accepted, chip says "not visible to this model" | ✅ accepted, described | 8 MB |
| Notebook file `.ipynb` | `application/json` | ✅ imported then attached as `notebook` | same | 8 MB |
| Data table `.csv`, `.tsv` | `text/csv` | ✅ attached as text, rows capped | same | 8 MB |
| Plain text, code, logs | `text/*` | ✅ attached as text, chars capped | same | 8 MB |
| PDF | `application/pdf` | ❌ refused: "convert to an image or text" | ⚠️ accepted, text-extracted only | 8 MB |
| Anything else | — | ❌ refused, names the detected type | ❌ same | — |

`CAP-1` — A file whose MIME type cannot be determined, or is not in this table, is refused with a message
naming what was detected. It is never accepted "to see what happens".

`CAP-2` — An image attached while the session's model has no vision capability is **accepted and labelled**
— never refused and never silently degraded. The chip reads *"not visible to this model"*, and the prompt's
manifest tells the model it cannot see the pixels and must say so rather than guess. A refusal was the first
implementation and it was wrong: it left a user in a text-only deployment no way to hand over a screenshot
at all, for an administrative reason they cannot act on. *First principle: [P4](./01-five-whys.md) — the
unacceptable case is an attachment the model **silently** cannot see.*

`CAP-3` — The capability is stated where it changes an outcome, not by disabling a control: images paste
and drop on any model, and the chip says whether the model can see inside them. A disabled affordance was
the first design; it made the composer look broken for the one action a user most wants.

`CAP-4` — If a vision model is switched mid-session, a previously refused image may be attached without a
reload; the attach affordance re-reads capability from the model control's state, which the app already
tracks.

---

## Upload

`AFC-1` — Pasting from the clipboard into the composer attaches the clipboard's file(s). If the clipboard
holds an image, it becomes an `image/png` attachment named `pasted-<timestamp>.png`. If it holds files,
each becomes an attachment. If it holds only text, **nothing happens** and the text pastes normally. *P8.*

`AFC-2` — Dragging files over the composer shows a drop target; dropping attaches them. Dragging over
anything else in the app keeps its existing behaviour (Files pane import). *P7.*

`AFC-3` — The `+` button in the composer opens a menu with *Attach files* (a real file picker,
`<input type="file" multiple>`), *Add context* (the existing `@` flow), and *Connectors* (a placeholder
that states what it will do). *P1.*

`AFC-4` — A file over the size limit is refused **before upload begins**, with a sentence naming both the
file's size and the limit: `report.pdf is 12.4 MB; the limit is 8 MB`. No bytes are sent. *P7.*

`AFC-5` — More than `MAX_ATTACHMENTS` attachments in one message is refused with a sentence naming the
limit. The existing `MAX_ATTACHMENTS = 6` applies to blobs and references **together**, not separately.

`AFC-6` — While an upload is in flight the chip shows an indeterminate state; the composer's Send button
is enabled only when every attached blob is `ready` or `failed`. A failed blob can be retried or removed
from the chip, and its failure is stated in the chip's text (not only its colour). *P8.*

`AFC-7` — Removing a chip before send deletes the blob if no other turn references it. Removing a chip
after send is not offered (the turn is history). *P5.*

`AFC-8` — An attachment survives a page reload: reopening a session re-renders the chips from the event
log, with the same names, kinds, and (for images) a thumbnail. *P5.*

---

## Content and injection

`AFC-9` — Every attached blob's content is fenced as data by the existing `render()`, and images carry an
explicit line telling the model that any text inside the image is data, not instructions. *P2.*

`AFC-10` — Text extracted from an image (when a vision model describes it) is labelled as
`model-description`, not as the user's words, and is stored so a later turn can see what the model was
told. *P2.*

`AFC-11` — A file whose name contains path separators, `..`, control characters, or characters illegal in
a workspace path is renamed deterministically for the stored blob, and the user's original name is kept as
display metadata. The workspace path (when written) is derived from the sanitised name only. *P1.*

`AFC-12` — A file that is entirely whitespace, zero bytes, or fails its own type's validity check (e.g. a
`.png` whose magic bytes are not a PNG) is refused with a sentence naming the mismatch. *P1.*

---

## Blob storage

`BLB-1` — A blob is stored once, addressed by an opaque id, with: id, session id, user id, original name,
sanitised name, MIME type, byte length, SHA-256, storage key, created time, and lifecycle state. *P5.*

`BLB-2` — Blob bytes are never stored in the event log, never base64 in a JSON body larger than the upload
itself, and never re-encoded on read. *P6.*

`BLB-3` — A blob's lifecycle is `pending → ready → attached`, with `failed` reachable from `pending`. A
`pending` blob older than 1 hour is swept. A blob no turn references and older than 24 hours is swept.
*P5.*

`BLB-4` — Reading a blob requires the owning user's identity; a blob id from another user returns 404, not
403 (existence is not disclosed). *P1.*

`BLB-5` — The store is an interface (`BlobStore` port) with two implementations: an in-memory one for
tests and a file-system one for development. A database-backed one is a third implementation of the same
port, not a migration of the feature. *SOLID: dependency inversion.*

---

## The fence

`SEC-1` — Writing a blob into the workspace goes through `scope.check_path` exactly as `Save` does. Inside
the folder: `ALLOW`. Outside: `ASK`, and the approval token is bound to the exact destination path.
`DENY` is honoured. *P3.*

`SEC-2` — The blob can be attached to a message **without** being written to the workspace. Writing is a
separate, explicit action ("Save to folder"), never a side effect of attaching. *P3.*

`SEC-3` — A blob's declared MIME type is verified against its magic bytes on the server; a mismatch is a
refusal, and the detected type is named. The browser's `File.type` is advisory only. *P1.*

`SEC-4` — Uploaded bytes are never served back with a content type that a browser will execute. Images are
served as their verified image type with `Content-Disposition: inline` and `X-Content-Type-Options:
nosniff`; everything else is `application/octet-stream` with `attachment`. *P2.*

`SEC-5` — The attachment's text representation is size-capped by the existing `MAX_CHARS_TOTAL`, and a cap
that truncates says so in the prompt, naming the tool that reads the rest. *P6.*

---

## Server-side resolution

`AFC-13` — `ctx_service.resolve` gains a `blob` branch: for a text-like blob it returns the decoded text
(capped); for an image it returns a description block naming the file, its size, and that the bytes are
available to the agent under a stable reference. It never returns base64 into the prompt.

`AFC-14` — A new MCP tool `dbx_read_blob(blob_id, offset, max_chars)` returns: for text, a paged window
with `next_offset`; for binary, a manifest (name, type, bytes, sha256) and a refusal to inline bytes,
naming what the agent should do instead. Registered in `TOOL_COUNT_CORE`. *P4.*

`AFC-15` — A blob that failed to upload never reaches the prompt; the turn's evidence notes it was
attached and could not be read, so the user can see the agent did not silently miss it. *P7.*

---

## Honesty and error copy

`AFC-16` — Every refusal is one sentence, present tense, naming the limit and the value, with no
exclamation mark and no blame. The complete set is enumerated in
[09 §copy](./09-edge-cases.md#the-copy-register). Tested as a table, not per case.

`AFC-17` — The chip's state is readable without colour: `uploading` shows a progress affordance,
`failed` shows the word "failed" and a retry control, `ready` shows nothing extra.

`AFC-18` — An attachment that is accepted and then disappears (swept, or deleted by another tab) renders
in the transcript as "this attachment is no longer available" rather than vanishing.

---

## Accessibility

`AFC-19` — The paste, drop, and picker paths are all reachable without a mouse: the `+` menu is keyboard
navigable, the file picker opens from the keyboard, and focus returns to the textarea after an attachment
is added. *WCAG 2.1.1.*

`AFC-20` — The drop target announces itself: during a drag the composer's `aria-describedby` points at a
live region reading "drop to attach". *WCAG 4.1.3.*

`AFC-21` — Every chip has an accessible name that includes the file name and its state; the remove
control's name includes the file name (`Remove report.png`). *WCAG 2.5.3.*

`AFC-22` — The attach affordances meet the 24×24 CSS px pointer minimum, as the rest of the shell now
does. *WCAG 2.5.8.*

---

## Non-goals

Explicitly out of scope, so a reviewer can tell a missing feature from a refused one:

| Not doing | Why |
|---|---|
| Sending image bytes to the model as an image block | The ACP wire here carries `{type:"text"}` only; see [D7](./07-architecture.md#d7-capability-is-declared-not-assumed) |
| OCR in the browser | A second inference path, unmeasurable cost, and the model already does it better |
| Virus scanning | A real AV integration is its own spec; the fence + type validation + no-execution is what this spec owns |
| Resumable/chunked upload | 8 MB does not need it; adding it adds a state machine for no user benefit |
| Attachments in the *Files pane* (already works) | That path imports to the workspace and is unchanged |
| A blob store in Unity Catalog | The port makes it a later implementation; nothing here forecloses it |

---

## Traceability

Every requirement maps to a test. The map is the table in
[10 §traceability](./10-e2e-plan.md#traceability), and a test that cites no requirement is either
unnecessary or is documenting a requirement not yet written down.
