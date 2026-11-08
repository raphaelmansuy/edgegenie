# 10. E2E plan

**The scenes, the screenshots, the pass criteria, and the inspection loop.**

Every scene produces a screenshot into `specs/009-attach-file-clipboard-support/e2e/screenshots/`, and every
screenshot is looked at. A scene that passes its assertions but renders badly is a **failed scene**, which
is the rule this repository learned in 006 and 007.

Spec [009](./README.md) · requirements [03](./03-requirements.md) · edge cases [09](./09-edge-cases.md) ·
outcome [11](./11-outcome.md)

---

## The runner

```console
$ APP_URL=http://127.0.0.1:8062 node web/scripts/attach-e2e.mjs
```

One file, the scenes in order, each in a fresh context so a draft or a blob from the previous scene cannot
mask a bug. Helpers from `parity-lib.mjs` (`launch`, `check`, `finish`) so the output format matches the
other suites.

```js
// web/scripts/attach-e2e.mjs — shape, not the whole file
const OUT = new URL("../../../../specs/009-attach-file-clipboard-support/e2e/screenshots/", import.meta.url).pathname;

await scene("S1", 1440, async (p) => { … });
```

`scene(name, width, body, {scheme})` — the same signature `model-picker.e2e.mjs` already uses, because two
runners with two shapes is how suites drift.

---

## The scenes

### [S1] The `+` menu exists and works

| | |
|---|---|
| **Width** | 1440, light |
| **Proves** | [AFC-3](./03-requirements.md), [AFC-19](./03-requirements.md) |
| **Steps** | open composer → Tab to `+` → Enter → assert three rows → ArrowDown → Escape → assert focus back on `+` |
| **Screenshot** | `S1-attach-menu.png` |
| **Pass** | menu visible, three `role=menuitem` rows, `Connectors` disabled, focus restored |

### [S2] Paste an image, one keystroke, end to end

| | |
|---|---|
| **Width** | 1440 |
| **Proves** | [AFC-1](./03-requirements.md), [P8](./01-five-whys.md), [V1](./06-lenses.md#the-vetoes-collected) |
| **Steps** | build a PNG with `page.evaluate` + `DataTransfer` → dispatch `paste` on the textarea → assert a chip exists **on the next animation frame** → wait `ready` → type a question → Enter → wait turn → assert the answer's evidence names the attachment |
| **Screenshot** | `S2-pasted-chip.png`, `S2-answer-with-evidence.png` |
| **Pass** | chip ≤ 1 frame after paste; `ready` within 3 s; evidence row mentions the file; no page errors |

The `DataTransfer` construction is the part that must be real:

```js
await p.evaluate(async () => {
  const blob = await (await fetch("/__fixture/png")).blob();      // served by the stub below
  const dt = new DataTransfer();
  dt.items.add(new File([blob], "shot.png", { type: "image/png" }));
  document.querySelector(".composer textarea")
    .dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
});
```

### [S3] An image on a text-only model is refused, and says why

| | |
|---|---|
| **Width** | 1440 |
| **Proves** | [CAP-2](./03-requirements.md), [E-7](./09-edge-cases.md) |
| **Steps** | select `llama-4-maverick` (no vision) → paste a PNG → assert a refusal sentence naming the model → assert **no** blob was uploaded (network listener) |
| **Screenshot** | `S3-refused-no-vision.png` |
| **Pass** | the sentence matches `REFUSALS["no_vision"]` with the model name substituted; zero `/api/blobs` requests |

### [S4] Refusals, four kinds, in one screen

| | |
|---|---|
| **Width** | 1440 |
| **Proves** | [AFC-4](./03-requirements.md), [AFC-16](./03-requirements.md), [E-1](./09-edge-cases.md), [E-3](./09-edge-cases.md), [E-5](./09-edge-cases.md), [E-8](./09-edge-cases.md) |
| **Steps** | paste a 12 MB file; paste 7 small files; paste an empty file; paste a PDF → screenshot each refusal |
| **Screenshot** | `S4a-too-big.png`, `S4b-too-many.png`, `S4c-empty.png`, `S4d-pdf.png` |
| **Pass** | each sentence names the value and the limit; each has `role="alert"`; the message text in the box is preserved |

### [S5] Six chips, both themes, two widths

| | |
|---|---|
| **Width** | 1440 and 900 |
| **Proves** | [E-24](./09-edge-cases.md), [E-16](./09-edge-cases.md), [E-25](./09-edge-cases.md), [V5](./06-lenses.md#the-vetoes-collected) |
| **Steps** | attach 6 files of mixed type (png, csv, txt, gif, jpg, md) → screenshot light 1440, dark 1440, light 900 |
| **Screenshot** | `S5-chips-1440.png`, `S5-chips-dark.png`, `S5-chips-900.png` |
| **Pass** | row wraps without overflow; every thumbnail rendered; **no `data:` URL in the DOM**; overflow audit 0 |

### [S6] Save to folder goes through the fence

| | |
|---|---|
| **Width** | 1440 |
| **Proves** | [SEC-1](./03-requirements.md), [SEC-2](./03-requirements.md), [E-17](./09-edge-cases.md) |
| **Steps** | attach a PNG → "Save to folder" → `/Shared` (outside scope) → assert ask banner → Allow once → assert the file exists |
| **Screenshot** | `S6-fence-ask.png`, `S6-saved.png` |
| **Pass** | nothing written before approval; path present after; the existing ask banner is reused, not a new one |

### [S7] The transcript reproduces on reload

| | |
|---|---|
| **Width** | 1440 |
| **Proves** | [AFC-8](./03-requirements.md), [D6](./07-architecture.md#d6-the-transcript-is-the-source-of-truth-the-composer-is-a-draft), [E-28](./09-edge-cases.md) |
| **Steps** | send with 2 attachments → reload → assert both chips render in the transcript with the same names → assert the composer's chip row is empty |
| **Screenshot** | `S7-transcript-after-reload.png` |
| **Pass** | names identical; thumbs load; composer empty; no duplicate chips |

### [S8] Dark mode and a dark screenshot

| | |
|---|---|
| **Width** | 1440, `colorScheme: "dark"` |
| **Proves** | [E-26](./09-edge-cases.md), [E-27](./09-edge-cases.md) |
| **Steps** | attach a dark-terminal PNG and a light image in dark mode |
| **Screenshot** | `S8-chips-dark-both.png` |
| **Pass** | a11y contrast 0 findings; both thumbnails distinguishable from the chip background |

### [S9] Every failure path, visible

| | |
|---|---|
| **Width** | 1440 |
| **Proves** | [AFC-6](./03-requirements.md), [AFC-15](./03-requirements.md), [AFC-17](./03-requirements.md), [AFC-18](./03-requirements.md), [E-9](./09-edge-cases.md), [E-11](./09-edge-cases.md), [E-20](./09-edge-cases.md) |
| **Steps** | route-abort the upload → assert `failed` chip with the word and a retry → retry succeeds → delete the blob server-side → send → assert the evidence says unavailable |
| **Screenshot** | `S9a-upload-failed.png`, `S9b-retried.png`, `S9c-unavailable-in-evidence.png` |
| **Pass** | the word "failed" is in the chip's text; retry re-sends; the unavailable case is visible in evidence, not silent |

### [S10] Nothing regressed

| | |
|---|---|
| **Widths** | 1440, 1180, 900, 760 |
| **Proves** | [V4](./06-lenses.md#the-vetoes-collected), [AFC-22](./03-requirements.md) |
| **Steps** | measure `.composer-box` height at rest at each width with the feature built; compare against the recorded baseline; run `a11y-audit`, `overflow-audit`, `cls-audit` |
| **Screenshot** | `S10-composer-{1440,1180,900,760}.png` |
| **Pass** | height identical to baseline at every width; a11y 0; overflow 0; CLS ≤ 0.0292 |

The baseline heights are recorded in [11](./11-outcome.md) as measured, not asserted from memory.

---

## The inspection loop

A screenshot is a test result that needs a reader. The loop, run for every scene:

```
  ┌─────────────────────────────────────────────────────────────────┐
  │  1. run the scene                                               │
  │  2. open the PNG and look at it                                 │
  │  3. write down what is wrong, in one line, even if it is small   │
  │  4. change one thing                                            │
  │  5. re-run the scene, go to 2                                   │
  │  6. when nothing is wrong, record the change list in 11-outcome │
  └─────────────────────────────────────────────────────────────────┘
```

What "look at it" means here, concretely — the six questions asked of every screenshot:

| # | Question | A failure looks like |
|---|---|---|
| 1 | Is anything clipped, wrapped mid-token, or ellipsised that should not be? | `dbx_write_noteb…` |
| 2 | Is anything the same colour as its background? | a thumbnail disappearing into the chip |
| 3 | Does every element line up with its neighbours? | a chip 2 px taller than its sibling |
| 4 | Is the smallest text still readable at 100% zoom? | 9.5 px grey on grey |
| 5 | Is a control's state visible without hovering? | a focused menu row with no visible focus |
| 6 | Would a person know what to do next? | a refusal with no action |

A scene is only "done" when all six answers are "no problem", and the change list in
[11](./11-outcome.md) records what step 3 produced. A scene whose screenshot needed no change is recorded
as such — that is evidence too.

---

## Traceability

Every requirement and every edge case, mapped to the test that proves it.

| Id | Scene | Also covered by |
|---|---|---|
| AFC-1 | S2 | `Composer.test.tsx::paste_image_attaches` |
| AFC-2 | S5 | `Composer.test.tsx::drop_attaches` |
| AFC-3 | S1 | `Composer.test.tsx::menu_rows` |
| AFC-4 | S4a | `blob.test.ts::too_big` |
| AFC-5 | S4b | `test_blob_rules.py::test_too_many` |
| AFC-6 | S9a | `Composer.test.tsx::retry` |
| AFC-7 | — | `test_blobs.py::test_remove_unreferenced_deletes` |
| AFC-8 | S7 | `events.test.ts::blob_attached_replay` |
| AFC-9 | S2 | `test_binding.py::test_blob_is_fenced` |
| AFC-10 | S2 | `test_binding.py::test_image_description_labelled` |
| AFC-11 | — | `test_blob_rules.py::test_name_traversal` |
| AFC-12 | S4c | `test_blob_rules.py::test_zero_bytes` |
| AFC-13 | S2 | `test_binding.py::test_blob_resolves` |
| AFC-14 | S2 | `test_mcp.py::test_read_blob_paged` |
| AFC-15 | S9c | `test_binding.py::test_missing_blob_reported` |
| AFC-16 | S4 | `test_blob_rules.py::test_copy_register` |
| AFC-17 | S9a | `Chip.test.tsx::failed_states_the_word` |
| AFC-18 | S9c | `Transcript.test.tsx::unavailable_chip` |
| AFC-19 | S1 | `a11y-audit` |
| AFC-20 | S5 | `Composer.test.tsx::drag_live_region` |
| AFC-21 | S5 | `Chip.test.tsx::remove_label_names_file` |
| AFC-22 | S10 | `a11y-audit` targets |
| BLB-1..5 | S7, S9 | `test_blobs.py` (contract, both stores) |
| CAP-1..4 | S3 | `test_capability_matrix.py` |
| SEC-1..3 | S6 | `test_api.py` fence cases |
| SEC-4 | S9 | `test_api.py::test_content_disposition` |
| SEC-5 | — | `test_binding.py::test_cap_is_named` |
| E-1..E-30 | see [09 matrix](./09-edge-cases.md#the-matrix-as-a-table) | per row |

The rule: a row with an empty "Scene" and an empty test is a requirement nobody will notice is missing. There
are none.

---

## What the suite must not do

| Not doing | Why |
|---|---|
| Assert a specific pixel width of a chip | it will change with the font, and the assertion will be noise |
| Screenshot without looking | the whole point of the loop |
| Use a real 12 MB file in git | generate it at runtime with `Buffer.alloc` |
| Depend on a vision model being configured | [S3] proves the refusal path, which needs no vision model at all |
| Leave a blob on disk after the run | teardown deletes the temp folder it created |
