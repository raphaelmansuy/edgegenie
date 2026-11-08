# 01. Five whys, and first principles

**Why does this feature exist, and what is irreducible about it?**

Spec [009](./README.md) · requirements [AFC-*](./03-requirements.md) · decisions `[D1..D12]`

---

## The report

The user typed *"story"* into the composer of the coding agent, pressed the `+`, and got a menu that offers
*Attach files*, *Add context*, *Connectors*. There is no way to give the agent a picture. There is no way to
paste a screenshot.

The request: **attach a file or paste an image from the clipboard into a coding session.**

That is a small sentence. This document asks why it is not a small change.

---

## Five whys

### Why 1 — why can the user not attach a file?

Because the composer's context model is **references to workspace objects**. `domain/context.py` accepts
exactly five kinds — `notebook`, `file`, `folder`, `table`, `cell` — and each one is a *path* or a
*three-part name*. The chip in the composer is a label over `{kind, ref}`. There is no kind for "bytes the
user handed me", so there is no chip, no picker, no paste handler, and no field on the wire.

### Why 2 — why is it references rather than content?

Because that was the correct decision for the problem it solved. The header of `context.py` states it:
*"Attachments are references (kind + path); the server re-reads the object with the user's own token. The
browser never supplies content, so it cannot attach something it cannot read."*

The client cannot lie about what it attached, and it cannot attach a document it has no permission to read.
That is a **security property**, and it is the reason a file picker cannot simply POST base64 into the
conversation. Any design that keeps this property is better than one that does not.

### Why 3 — why did that rule become a limitation?

Because it assumes **every input already exists in the workspace**. A screenshot on the clipboard, a CSV a
teammate pasted into Slack, a design mock a designer exported — none of these are workspace objects. They
are bytes on the user's machine, and the user is the only one who can read them.

So the rule and the new requirement are in direct conflict on one axis: *who is the authority for the
content?* For an existing notebook, the workspace is. For a pasted screenshot, the browser is — and the
browser is exactly the party the original rule refused to trust.

### Why 4 — why not just trust the browser and POST the bytes?

Because "trust the browser" is not one decision, it is six, and five of them are security:

| If we trust the client blindly | The failure |
|---|---|
| Any size | A 2 GB body, or 10,000 small attachments, exhausts the server before any limit is reached |
| Any type | An `.html` or `.svg` served back later is stored XSS on our own origin |
| Any name | `../../etc/passwd`, or a name that overwrites `context.py` in the scratch folder |
| Any bytes labelled `image/png` | A file the renderer, the model, or a future export path trusts |
| Any content sent to a model | A prompt-injection payload the user did not knowingly submit |
| Any retention | A screenshot of a customer's data living in a session forever |

So the answer is not "trust the browser". It is: **the browser may supply bytes, but only through the same
fence, the same validation, and the same audit trail that every other write already goes through.**

### Why 5 — why does the *user* care, though?

Three reasons, in the order they actually occur:

1. **Speed.** Describing a broken chart in words takes four sentences; pasting it takes one keystroke.
   The agent's own README sells "reads, writes, runs, and proves" — but it cannot *see*.
2. **Fidelity.** "Revenue drops around hour 18" is a claim. A screenshot of the plot is evidence. A coding
   agent that only accepts prose forces the user to translate their evidence into prose, and translation
   loses exactly the detail that mattered.
3. **Trust.** The product's whole thesis is that the agent *proves* what it did (the evidence block, the
   audit log, the fence). A user who cannot show the agent what they are looking at is being asked to
   trust a blind collaborator.

And the root cause of *all five whys* is one sentence:

> **The context model has no representation for "bytes the user owns", and the security rule that protects
> references was written as if references were the only thing that could ever be attached.**

---

## First principles

Strip the feature to what cannot be argued away. Each principle below is either *load-bearing* (a design
that violates it is wrong) or *derived* (a consequence of one above it). Every requirement in
[03](./03-requirements.md) cites one of these.

### [P1] An attachment is a claim about the world, and the server must be able to check it

A reference is checkable today: the server re-reads the path with the user's token. Bytes are checkable
too, but only if the server validates them itself — size, type, magic bytes, name, and (for images)
decodability. **The browser's opinion about what it sent is not evidence.**

*Load-bearing.* It is why [D3](#d3-bytes-are-validated-on-the-server-not-trusted-from-it) exists.

### [P2] A file the user hands us is untrusted input, in every sense

It is untrusted as *content* (prompt injection: an image can contain text saying "ignore your
instructions"), untrusted as *bytes* (a polyglot file), and untrusted as a *name* (path traversal). The
existing `render()` already fences attached text with `<attached-context>` and a warning; a pasted image
must carry the same warning, because the model will read whatever is in it.

*Load-bearing.* [AFC-9](./03-requirements.md), [AFC-14](./03-requirements.md).

### [P3] The fence is about paths, and a blob has no path yet

The security model is `scope.check_path`. An uploaded file is *outside the workspace* by definition until
it is written into it. So writing it is an `ASK`, not an `ALLOW` — unless the user has already named a
folder they own. The fence must decide, and the decision must be visible before the write, exactly as it
is for `Save`.

*Load-bearing.* [D5](#d5-a-blob-is-written-inside-the-fence-or-not-at-all).

### [P4] Every capability the product claims must be true of the input it accepts

Today the agent "reads, writes, runs, proves". If a user attaches a PDF and the feature accepts it, the
agent must be able to read it — or the feature must refuse it and say so. An accepted attachment that the
model silently cannot see is worse than a refused one, because the user believes the agent saw the picture.

*Load-bearing.* [D7](#d7-capability-is-declared-not-assumed), the capability matrix in
[03](./03-requirements.md).

### [P5] A message is a unit; an attachment is a reference to a unit

The transcript, the event log, the evidence block and the audit trail all reason about *turns*. An
attachment that lives only in the composer's React state would vanish from the transcript, would not
survive a reload, and could not be re-read by the model in turn 4. So the attachment must be **durable,
addressable, and referenced by the turn** — not carried inline.

*Load-bearing.* [D2](#d2-a-blob-is-a-row-first-a-path-second), [D8](#d8-references-not-bytes-on-the-wire).

### [P6] The cheapest correct thing is the thing the user already has

A pasted screenshot is 40 KB. Writing it to the workspace creates clutter; base64 in the event log
inflates every replay. The existing `MAX_READ_BYTES = 400_000` and `MAX_CHARS_TOTAL = 16_000` already
encode the answer: **store the bytes once, pass a reference, let the agent fetch what it needs.**

*Derived from [P5].*

### [P7] Every refusal must be actionable

An upload that silently fails, or a chip that disappears without explanation, is a support ticket. The
product already has the vocabulary for this — the fence chip, the composer error, the toast — and this
feature must use it. "That file is 12 MB; the limit is 8 MB" is a sentence; "upload failed" is not.

*Load-bearing.* [AFC-16](./03-requirements.md).

### [P8] Nothing about this may slow the composer

Paste is a keystroke on the keyboard the user types on. The paste handler must return in under one frame,
show the chip immediately, and do the upload behind it — with an honest state on the chip (uploading,
ready, failed). This is the same rule the rest of the shell follows: never make the user wait for
something they did not ask to wait for.

*Derived from [P7].*

---

## What "perfect" means here, concretely

Not an adjective. Six measurable claims, each with a test:

| Claim | Measure | Where |
|---|---|---|
| Paste never blocks typing | `keydown` → chip visible in < 50 ms | [S2](./10-e2e-plan.md) |
| A rejected file is explained | every refusal has a sentence naming the limit and the value | [S4](./10-e2e-plan.md) |
| The fence still decides | a blob outside the folder requires approval, exactly like `Save` | [S6](./10-e2e-plan.md) |
| The transcript is honest | a reload reproduces the chips, byte-identical | [S7](./10-e2e-plan.md) |
| The model really receives it | a turn whose answer quotes the attached text | [S8](./10-e2e-plan.md) |
| Nothing else regressed | a11y 0 findings, overflow 0, CLS ≤ baseline | [S10](./10-e2e-plan.md) |

---

## The one-sentence answer

> Let the browser hand the server bytes **through the same fence, limits, validation, and audit trail that
> every other write uses**, store them once as an addressable object, and attach them to the turn as a
> reference — so the composer stays instant, the transcript stays honest, and the security model is
> extended rather than bypassed.
