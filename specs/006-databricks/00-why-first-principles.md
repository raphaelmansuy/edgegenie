# 00 · Why, from first principles

[Index](README.md) · next: [01 Current-state audit](01-current-state-audit.md)

Most UI work starts from "the other product has a right-hand panel, so let us add a right-hand
panel". That produces a copy that is worse than the original, because the panel is a symptom of a
constraint we have not found yet. This document finds the constraint first, in five steps, and then
derives the design from it.

---

## The five whys

The complaint, as stated: *"how does Genie Code open a conversation on the right side of a file, to
be in context to update?"*

**1 · Why does that interaction matter?**
Because the user's task is **cyclic**: read the file, decide on a change, ask for it, look at the
result, read the file again. Genie Code keeps the whole loop visible at once. EdgeGenie breaks it at
the second step.

**2 · Why does EdgeGenie break it?**
Because the conversation and the document occupy the **same slot**. `App` holds one `view` string
([`App.tsx:62`](../../apps/coding-agent/web/src/App.tsx)); when a file is opened, `view` becomes the
file id and the transcript is not rendered
([`App.tsx:523-535`](../../apps/coding-agent/web/src/App.tsx)). To ask a question about the file you
are reading, you must navigate *away* from it.

**3 · Why are they in the same slot?**
Because the original design treated the conversation as a **document among documents** — a tab you
open, like a notebook. That is a defensible choice for a chat product and a wrong one for an editor:
a tab is something you switch to, and an assistant is something that stays with you.

**4 · Why was that wrong conclusion reached?**
Because the *binding* was implicit. The app infers what a prompt is about from whichever document
happens to be on screen (`asAttachment(viewDoc)`,
[`App.tsx:183-188`](../../apps/coding-agent/web/src/App.tsx)). With an implicit binding, the
conversation has to be on screen at the same time as the document for the context to be right — so
they were merged. The merge is a workaround for a missing concept.

**5 · Why is the binding implicit?**
Because nothing in the domain names it. There is a `Doc` (kind, ref, rev) and there is an
`Attachment` (kind, ref, name), and the translation between them is a function that reads "the
document that is open". There is no object that says *this conversation is about this document, and
this cell*. Without that object, "in context" can only mean "what is visible".

**The root cause:** *the product has no first-class notion of what a conversation is about.* Every
symptom in [01](01-current-state-audit.md) follows from that: the tab that replaces the transcript,
the inspector that cannot talk, the `@` search that only looks at the home folder, the cell-level
"ask" button that was never wired to anything.

---

## First principles

Reduced until each statement is either true by construction or is a product decision someone can
argue with. There are six.

### P1 · A conversation has a subject, and the subject is data

A conversation is not "a chat window"; it is **a sequence of turns about a subject**. Genie Code's
right pane makes the subject visible (`in context: <file>`); ours makes it a side effect of the
viewport. The subject must be a value the app holds, renders, and sends — not a thing inferred from
what happens to be on screen.

*Consequence:* a `Focus { docId, cellId }` becomes a domain object with its own tests. It is a
dependency of the prompt, of the dock header, and of the tab strip's active state — one source of
truth instead of three coincidences.

### P2 · Two surfaces that must be watched together cannot share a slot

This is a layout axiom, not a preference. Reading code and reading the answer are two glances the
user alternates between at a rate of seconds; forcing a navigation between them costs a state loss
each time (which tab was I on? where was I in the file? what did I have selected?). [001](../001-perfect-shell/README.md)
already established the discipline for this: a zone is geometry, and geometry is one function
(`columns()`), so "two things at once" is a width question and nothing else.

*Consequence:* the assistant is a **zone** in the grid, not a tab in the centre. Its width obeys the
same bounds as every other zone, and the centre column keeps its `CENTRE_MIN` guarantee.

### P3 · Below some width, two at once is a lie, so one is an overlay the user summons

A 900 px window cannot hold a 276 px rail, a 480 px document and a 340 px assistant. Pretending
otherwise produces three slivers. The honest response is an overlay, but an overlay that opens by
itself destroys the thing the user was looking at. Therefore: **an overlay opens only when asked, and
the asking is a fixed control** — a key that is printed on the surface, and a button that is always
present.

*Consequence:* `⌘J` toggles the dock; the top bar carries a pressed-state toggle for it; the dock
never auto-opens on a resize. This is the same rule [001 SH-C](../001-perfect-shell/02-requirements.md)
applied to the drawers that already exist.

### P4 · A control that cannot act must not be shown

The audit found two: a per-cell run button whose handler is never passed
([`NotebookEditor.tsx:141-144`](../../apps/coding-agent/web/src/components/NotebookEditor.tsx)), and
an in-cell `ask` that forwards to a prop `Viewer` never supplies
([`EditorSurface.tsx:51`](../../apps/coding-agent/web/src/components/EditorSurface.tsx)). Both are
worse than absent: they teach the user that the app is unreliable, in the surface where reliability
is the product.

*Consequence:* the dock makes `ask` real (it is the whole point of a cell scope), and `run` is
removed until a real executor exists ([11 D3](11-decisions-risks.md)). The rule is testable: every
button in the shell has a handler that can be observed doing something.

### P5 · State that the user created is the product's responsibility

A deployed Databricks App restarts on every redeploy; a browser tab is closed many times an hour.
Today a session lives only in memory ([`main.py:41`](../../apps/coding-agent/api/main.py)), so a
redeploy ends every conversation, and the transcript is reconstructed by replaying an in-memory
event log that no longer exists. The dock *increases* the number of turns that would be lost,
because it makes it easy to keep a conversation open for a whole working session.

*Consequence:* sessions, turns, bindings and the model pin persist ([05](05-data-model-lakebase.md)),
and the client's replay cursor becomes meaningful rather than decorative.

### P6 · Parity is a measurement, not an adjective

"On par or superior" is unfalsifiable unless it is stated as numbers and captured as evidence. The
numbers that matter for this work are all obtainable: chrome height before the first line of code,
the widths at which the assistant is available, the number of interactions to change the model, the
number of dead controls, and the number of user-visible actions lost to a reload.

*Consequence:* [01](01-current-state-audit.md) records both products on the same five measures, and
[12](12-e2e-plan.md) re-measures them after.

---

## What follows, as a single claim

> If the subject of a conversation is a value, then the conversation does not need to occupy the
> document's slot; it can live in a zone beside it, bound to that value, summoned by a key when the
> window is too narrow to show both.

Everything else in this spec is engineering under that claim. The dock is the zone. `Focus` is the
value. `⌘J` is the summoning. The Lakebase tables are how the value outlives a container.

---

## What would falsify this

Stated so the design can be argued with rather than merely followed:

| If this were true | Then the design is wrong |
|---|---|
| Users ask about a document far more often than they edit one, and rarely look back at it while reading the answer | A tab is fine; the dock is wasted width. The evidence against: the request itself is about *updating* a file while in context. |
| Wide screens are rare in this audience | The dock would be a drawer for everyone, and the rail would be the better investment. The evidence against: the deployed app is used at 1512 px and above (`e2e` screenshots). |
| The turn record is cheap enough to reconstruct from the agent's own session | Persisting it is duplicate state. The evidence against: the agent process is per-session and is destroyed on restart ([`orchestrator.py:434`](../../apps/coding-agent/api/services/orchestrator.py)). |

These are revisited in [11 §What would change our mind](11-decisions-risks.md#what-would-change-our-mind).
