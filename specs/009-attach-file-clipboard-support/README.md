# 009. Attach a file, paste an image

**A specification, an implementation plan, and the implementation: give the agent the bytes the user is
already holding — by paste, drop, or picker — without ever breaking the fence, the limits, or the
transcript's honesty.**

> **Status:** specification complete; implementation in progress. 9 November 2026.
> **Scope:** the composer's attach surface (`web/src/components/Composer.tsx` and its neighbourhood), a new
> blob stage in the API (`api/domain/blob.py`, `api/services/blobs.py`, `api/adapters/blob/`), three routes,
> one context branch, one MCP tool, and one event type. It changes **no** existing attachment behaviour: the
> five reference kinds work exactly as they do today.
> **Relation to earlier specs:** extends the context model of [006 · On par with Genie Code](../006-databricks/README.md)
> and the shell of [007 · The shell, the keys, and the scroll](../007-ux-ui-improve/README.md). It reuses
> 007's audits (a11y, overflow, CLS) as its definition of "not clunky". It does not touch
> [008 · the public site](../008-github-page/README.md).
> **Audience:** product, full-stack, database, UX/UI, front-end, growth.

---

## The one sentence

> A user presses ⌘V with a screenshot on the clipboard, a chip appears in the same frame, and by the time
> they have typed their question the agent can see what they are looking at — and if it cannot, it says so
> in one sentence that names the limit.

Everything in this folder is an argument about that sentence.

---

## Read in this order

| # | Document | Answers |
|---|---|---|
| 01 | [Five whys and first principles](01-five-whys.md) | Why this is not a small feature, and the eight principles it must satisfy |
| 02 | [Grounded assessment](02-grounding.md) | What is actually in the code, traced end to end, with the commands that count it |
| 03 | [Requirements](03-requirements.md) | `AFC-*`, `BLB-*`, `CMP-*`, `CAP-*`, `SEC-*` — each with its test |
| 04 | [Wireframes (ASCII)](04-wireframes.md) | Every screen and state, drawn to the column |
| 05 | [Diagrams (Mermaid)](05-diagrams.md) | Sequences, the blob's state machine, the ER model, the ports |
| 06 | [Six lenses](06-lenses.md) | Six owners, and the one thing each vetoes |
| 07 | [Architecture and decisions](07-architecture.md) | `[D1..D12]`, where each rule lives, SOLID and DRY point by point |
| 08 | [Implementation plan](08-implementation-plan.md) | Ten phases, the files, the tests, the order |
| 09 | [Edge cases](09-edge-cases.md) | Thirty cases, their copy, their tests, two accepted limitations |
| 10 | [E2E plan](10-e2e-plan.md) | Ten scenes, the inspection loop, full traceability |
| 11 | [Outcome](11-outcome.md) | What shipped, what the screenshots changed, what is still not true |

Cross-reference convention: a requirement is cited as `[AFC-3]`, a decision `[D5]`, an edge case `[E-11]`,
a scene `[S2]`, a first principle `[P1]`, a veto `[V4]`. Every id is defined exactly once — in `03`, `07`,
`09`, `01`, or `06` — and linked from everywhere else.

---

## The problem

The composer can attach five kinds of thing, and all five are **references to workspace objects**:

```python
KINDS = ("notebook", "file", "folder", "table", "cell")
```

That is a good design with one consequence: *anything that is not already in the workspace cannot be
attached at all.* A screenshot on the clipboard, a CSV from a colleague's message, a diagram exported from
a design tool — none of these are workspace paths, so there is no chip, no picker, and no wire field for
them.

The security rule that produced this is worth keeping:

> *"Attachments are references (kind + path); the server re-reads the object with the user's own token. The
> browser never supplies content, so it cannot attach something it cannot read."*

The feature is therefore not "add an upload button". It is: **let the browser supply content through the
same fence, limits, validation, and audit trail that every other write uses** — which is
[P1](./01-five-whys.md#p1-an-attachment-is-a-claim-about-the-world-and-the-server-must-be-able-to-check-it).

---

## The shape of the answer

```
  clipboard / drag / picker
        │
        ▼  bytes (validated twice: client courtesy, server rule)
  ┌──────────────┐
  │  BlobStore   │  durable, addressable, swept, never in the event log
  └──────┬───────┘
         │  {kind:"blob", ref:"blb_7f3a"}
         ▼
  turn.attachments ──▶ context.render() ──▶ the model
         │                                    │
         │                                    └── dbx_read_blob for the rest
         ▼
  the transcript (chips) + the evidence (what was read)
```

Four properties fall out of that shape, and each is a test:

| Property | Test |
|---|---|
| The composer never waits for the network | [S2](./10-e2e-plan.md#s2-paste-an-image-one-keystroke-end-to-end) — chip in ≤ 1 frame |
| The model never receives base64 | `test_binding.py` — no `/9j/` in the prompt |
| The fence still decides writes | [S6](./10-e2e-plan.md#s6-save-to-folder-goes-through-the-fence) |
| A missing attachment is never silent | [S9c](./10-e2e-plan.md#s9-every-failure-path-visible) |

---

## The honest limitation, up front

The ACP wire this app speaks carries `{type: "text"}` and nothing else (`api/adapters/acp/runtime.py:197`
and `:218`), and none of the 27 tools reads a byte range from a binary file. So "attach an image to a vision
model" cannot mean "send the pixels".

It means: **the server describes the image and exposes its bytes to a tool**, and the manifest says exactly
what the model was given. On a model with no vision the image is still accepted — the chip says *"not
visible to this model"* and the manifest tells the model to ask rather than guess — because a refusal would
leave the user no way to hand over a screenshot at all.

Sending a real image content block is [D7 option B](./07-architecture.md#d7-capability-is-declared-not-assumed)
— named, not done, and repeated in [11](./11-outcome.md#what-is-not-true-yet) so nobody discovers it later
and calls it a bug.

---

## What must be true when this is done

The short form; the long form is [03](./03-requirements.md).

1. ⌘V with an image attaches it, and the chip exists before the upload starts.
2. Every refusal is one sentence naming the limit and the value.
3. An image on a model that cannot see is refused **before** the upload, naming the model.
4. Writing a blob into the workspace goes through the fence, with the same approval as `Save`.
5. The transcript reproduces on reload, from the event log, with the same chips.
6. The model receives a fenced description, never base64, and can page the rest through a tool.
7. The composer's resting height does not change by a pixel.
8. a11y 0, overflow 0, CLS ≤ baseline — the 007 bar, unchanged.

---

## What this changes in code, at a glance

| Layer | New | Changed |
|---|---|---|
| domain | `api/domain/blob.py` | `context.py` (+1 kind) |
| ports | `BlobStore`, `BlobReader` | — |
| adapters | `blob/memory.py`, `blob/files.py` | — |
| services | `blobs.py` | `context.py` (+1 branch), `orchestrator.py` (tool count) |
| routes | `POST /api/blobs`, `GET /api/blobs/{id}`, `POST /api/blobs/{id}/materialise` | — |
| MCP | `dbx_read_blob` | tool count 19 → 20 |
| web domain | `blob.ts` | `events.ts` (+1 kind, +1 event), `api/client.ts` (+3) |
| web components | `AttachMenu.tsx`, `Chip.tsx`, `useBlobUpload.ts` | `Composer.tsx`, `styles.css` |

≈ 1,830 lines of implementation, ~124 unit tests, 10 e2e scenes. The estimate and its risk per phase are in
[08 §effort](./08-implementation-plan.md#effort-honestly).

---

## Status of the documents

| Doc | State |
|---|---|
| 01–10 | complete, reviewed against the code |
| 11 | written after the implementation, from the screenshots |
| `e2e/screenshots/` | filled by the loop in [10](./10-e2e-plan.md#the-inspection-loop) |
