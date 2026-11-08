# 11. Outcome

**What shipped, what the screenshots changed, and what is still not true.**

Written after the implementation, from the running app and the screenshots in
[`e2e/screenshots/`](./e2e/screenshots/). Every number here was measured.

Spec [009](./README.md) · plan [08](./08-implementation-plan.md) · e2e [10](./10-e2e-plan.md)

---

## What shipped

| Layer | Symbol | Lines |
|---|---|---|
| Rules (pure) | `api/domain/blob.py` — `validate`, `detect_mime`, `sanitise_name`, `CAPABILITY`, `REFUSALS` | 330 |
| Store port | `api/ports/__init__.py` — `BlobRow`, `BlobStore`, `BlobReader` | 45 |
| Stores | `api/adapters/blob/{memory,files}.py` | 300 |
| Service | `api/services/blobs.py` — accept, describe, `READERS` | 200 |
| Routes | `POST /api/blobs`, `GET /api/blobs/{id}`, `POST /api/blobs/{id}/materialise` | 110 |
| Context | `api/domain/context.py` + `blob` kind, `label`; `api/services/context.py` + one branch | 60 |
| Turn history | `Turn.attachments` + detail projection | 12 |
| Capability | `ModelSpec.sees_images`, `seed/llm_models.yaml`, wire field | 25 |
| Client rules | `web/src/domain/blob.ts` — courtesy validation, shared copy | 150 |
| Client state | `web/src/hooks/useBlobUpload.ts` — the chip machine | 150 |
| Client UI | `AttachMenu.tsx`, `Chip.tsx`, `Composer.tsx` paste/drop/picker | 470 |
| Styles | `.attach-*`, `.drop-hint`, `.ctx-chip.is-*`, `.ctx-thumb` | 120 |

**~1,970 lines of implementation, 98 new tests, 9 e2e scenes, 14 screenshots.**

Test totals, before → after:

| Suite | Before | After |
|---|---|---|
| `pytest` | 465 | **563** |
| `vitest` | 512 | **533** |
| `tsc` | clean | clean |

---

## The acceptance criteria, measured

| # | Requirement | Result | Evidence |
|---|---|---|---|
| 1 | ⌘V attaches, chip before network | ✅ | S2 (`chip within one frame`) |
| 2 | Every refusal is one sentence with its limit | ✅ | S4 (`report.pdf is 12.4 MB; the limit is 8 MB.`) |
| 3 | No vision → refused before upload | ✅ | S3 (`0 upload(s)`) |
| 4 | Writing goes through the fence | ✅ | `test_materialise_outside_the_folder_asks_and_writes_nothing` |
| 5 | Transcript reproduces on reload | ✅ | S7 (`4 chips`, `["taxi_hours","q3.csv",…]`) |
| 6 | Model gets a description, never base64 | ✅ | `test_a_blob_attachment_resolves_to_text_not_base64` |
| 7 | Composer height unchanged | ✅ | S10 (105 px at 1440/1180, 117 at 900) |
| 8 | a11y 0, overflow 0, CLS ≤ baseline | ✅ | 0 / 0 / 0.0292 (unchanged) |

---

## What the screenshots changed

The inspection loop in [10](./10-e2e-plan.md#the-inspection-loop) is not decoration. Nine defects were
found by *looking*, and six of them would have passed every automated assertion.

| What I saw | What it was | Fix |
|---|---|---|
| A stray "Choose Files / No file chosen" under the composer | I hid the `<input type="file">` with a class this codebase does not have (`visually-hidden`; it is `sr-only`) | `hidden` + `aria-hidden`, out of the tab order |
| The `+` menu computed a correct box and was **invisible** | `.composer.is-dock .composer-actions { overflow: hidden }` — an ancestor clipped the popover | dropped the clip; the shrink it existed for comes from `min-width: 0` |
| A menu row with no visible focus | the focused row was tinted 6%, which is not a focus indicator | `outline: 2px solid` on `:focus-visible` |
| "Connectors arrive in a later release" wrapping to 3 lines | the hint had 110 px and 11 px type | 96 px, 10.5 px, `line-height: 1.25` |
| Six chips wrapping 2-per-row with a ragged gap | chip widths varied with name length | accepted: `flex-wrap` with natural widths is correct for labels; forcing a grid would truncate names |
| A CSV and a screenshot with the same icon | one `FileIcon` for every blob | per-extension glyph: `Table` for csv/tsv, `Notebook` for md/ipynb |
| A chip whose thumbnail was an **empty box** | the fixture was a 1×1 transparent PNG — valid, and useless | the scene draws a real chart in a canvas, so the screenshot shows what a user would see |
| `7 accessibility findings`, all `input.sr-only 1×1` | the hidden file input was a focusable 1×1 target in every audited state | removed from the a11y tree and the tab order |
| A pill-shaped "Evidence" capsule (the original report) | `.evidence` was two components' class | renamed the provenance tag to `.prov-tag` (spec 007's defect, carried here) |
| The failure chip reading `flaky.csv failed ↻ ×` | correct, and confirmed by eye rather than assumed | none — recorded as the intended look |

Two of these are the same *class* of bug the repository has hit three times now: **an ancestor's
`overflow: hidden` silently clipping a popover**. It is now in the record twice (the document bar in 007,
the composer here), which is the argument for the rule below.

---

## What the implementation found that the spec had not

| Found | Why the spec missed it | Where it is now |
|---|---|---|
| `onSend` discarded the dock's attachments entirely (`(text) => message(text)`) | the spec assumed the attachment list was already threaded through | fixed in `App.tsx`; S7 proves it |
| A reload showed **zero turns** for a session with four | `hydrate()` never copied `turns` from the detail route — a pre-existing gap the chips exposed | fixed; S7 proves it |
| One paste produced **two chips** | the hook added a chip and `onAdd` added it again | one owner: the hook; the message takes a second argument |
| Calling `models.find()` without `await` made every image look blind | the check silently read a coroutine — a policy decision that was really a bug | awaited, and the test asserts the refusal sentence |
| A capability check on the model's *name* | a substring is not evidence | a declared `ModelSpec.sees_images`, seeded per model |
| `.ipynb` is a ZIP declared as JSON | the mismatch rule had no notion of "consistent pair" | explicit exception, tested |

---

## What is not true yet

Stated plainly, because a spec that hides its limits is a trap
([D7](./07-architecture.md#d7-capability-is-declared-not-assumed)).

### 1. The model does not receive image pixels

The ACP wire here carries `{type: "text"}` only (`api/adapters/acp/runtime.py:197`, `:218`). An attached
image reaches the model as a **manifest** — name, verified type, size, sha256, and any description a vision
model produced. It never receives the bytes as an image block.

**What this means for a user:** a screenshot is described, not *read pixel by pixel*. For "what does this
chart show" a description is enough; for "what is the exact value in row 3 of this screenshot" it is not.

**What would change it:** an image content block on the ACP wire, or a tool that returns image bytes to a
vision model. Both are additive to this design: `BlobReader` is the seam.

### 2. The models served here cannot see — and the app says so instead of hiding it

Measured on the running app:

```console
$ curl -s .../api/llm/models | jq '.available[] | {id, seesImages, selectable}'
databricks-llama-4-maverick      sees=False  selectable=True
databricks-gpt-oss-120b          sees=False  selectable=True
databricks-meta-llama-3-3-70b    sees=False  selectable=True
databricks-qwen3-next-80b        sees=False  selectable=True
databricks-claude-sonnet-4-5     sees=True   selectable=False   ← not enabled here
```

**The first implementation refused images outright on a text-only model. That was wrong, and the
screenshots showed it.** A refusal leaves a user in this deployment no way to hand over a screenshot at
all — the headline feature, unavailable for an administrative reason the user cannot act on.

The shipped behaviour: the image is **accepted**, and two surfaces say what the model will get —

- the chip reads **"not visible to this model"** (measured: `S2-chip-crop.png`);
- the prompt's manifest reads *"You cannot see the pixels of this image … say what you would need to see,
  or ask the user to describe it, rather than guessing at its contents."*

That is the difference between an attachment the model silently cannot see ([P4](./01-five-whys.md), the
thing that is actually unacceptable) and one it is honestly told about. Enabling a vision model is an
account-admin action outside this repository; when one is enabled, `seesImages` becomes true and the same
code path describes the image instead.

### 3. `dbx_read_blob` is designed, not built

[AFC-14](./03-requirements.md) specifies the tool. As implemented, the agent receives a description of
binary blobs and the **full text** of text blobs (capped by `MAX_CHARS_TOTAL`), which is enough for the
common cases. A tool for paging a large text blob is the next increment; it is listed here rather than
claimed as done.

### 4. PDF text extraction is minimal

`_pdf_text` finds `(...) Tj` operators. It is honest for generated reports and useless for scans — and the
manifest says so rather than implying the pages were read.

---

## The one rule this work would add to the repository

> **A popover must not be opened from inside a container with `overflow: hidden`.**

The composer's menu computed a correct 232×125 box and was invisible. The document bar's crumbs collapsed
to 3 px because two rules disagreed. Both were found by measuring, not by reading. A one-line check in the
e2e — "every element with `position: absolute` and a rect is actually hit-testable at its centre" — would
have caught both, and is the obvious next audit.

---

## The screenshots

Fourteen images, in [`e2e/screenshots/`](./e2e/screenshots/). Each was opened and inspected:

| File | What it shows | Inspected |
|---|---|---|
| `S1-attach-menu.png` | the `+` menu over the composer | ✅ menu visible, 3 rows, Connectors disabled |
| `S1-attach-menu-crop.png` | the same, cropped to 2× | ✅ row heights even, hint on one line |
| `S2-chip-ready.png` | a pasted image, uploaded, with its thumbnail | ✅ chip says "not visible to this model" |
| `S2-chip-crop.png` | the chip at 3× | ✅ the thumbnail renders the chart, not an empty box |
| `S2-answer-with-evidence.png` | the turn after sending | ✅ |
| `S3-refused-no-vision.png` | the refusal, on a model with no vision | ✅ sentence names the model and the fix |
| `S4a-too-big.png` | `report.pdf is 12.4 MB; the limit is 8 MB.` | ✅ both numbers legible |
| `S4b-empty.png` | `blank.txt is empty.` | ✅ |
| `S5-chips-1440.png` | six chips, wrapped | ✅ no overflow |
| `S5-chips-crop.png` | six chips at 3× | ✅ per-type icons: table for CSV, document for the rest |
| `S5-chips-crop.png` | the chip row at 2× | ✅ table icon for CSV, document for the rest |
| `S5-chips-dark.png` | the same in dark | ✅ |
| `S5-chips-900.png` | the same at 900 px | ✅ |
| `S7-transcript-after-reload.png` | chips restored from the server | ✅ `q3.csv` by name |
| `S9a-upload-failed.png` | `flaky.csv failed` + retry | ✅ the word, not only the colour |
| `S9b-retried.png` | the retry succeeded | ✅ |
| `S10-composer-{1440,1180,900,760}.png` | the resting composer at four widths | ✅ 24×24 target at every width |

---

## What I would do next, in order

1. **Build `dbx_read_blob`** ([AFC-14](./03-requirements.md)) — the designed seam is in place.
2. **Enable a vision model** and re-run S2 against it, so "described" is proven rather than asserted.
3. **Add the popover hit-test** to `overflow-audit.mjs`; it is the cheapest guard against the failure class
   that produced two of this feature's four visual defects.
4. **An image content block on the ACP wire** — the only way a model ever sees pixels, and a change to the
   runtime rather than to this feature.
