# 004 · CRDT collaboration

**A specification and implementation plan for real-time collaborative editing in the Databricks
Coding Agents app — replacing the version-token concurrency model in
[003](../003-improve-dev-ux-ui/07-decisions-risks.md#d9-no-crdt-in-this-design) with a convergent one.**

> **Status:** specification · 7 November 2026
> **This document reverses 003 D9.** That decision said "no CRDT, and here is when to reverse it".
> This is that reversal, taken deliberately and with the conditions from D9 checked off.
> **Scope:** `apps/coding-agent` — new collaboration service, a new persistence adapter, and a
> change to how the agent writes documents.
> **Supersedes:** 003 CX-1..CX-5 (version token, 409, conflict panel). Those requirements are
> **removed**, not kept alongside — see [§What dies](02-architecture.md#what-dies).

---

## Why this exists

003 shipped a **detect-then-choose** concurrency model: hold a version token, refuse a stale save
with 409, show both versions, let the human decide. It works, it is tested, and it has a written
limitation:

> "We ship the promise *recoverable*, not *impossible*." — 003 R1

D9 named the reversal trigger as a **product condition**, not scale:

> "Two people editing the same notebook at once and expecting to see each other's carets."

That is now the goal. Which means 003's concurrency model is not "insufficient" — it is **aimed at
the wrong question**. It asks *"who wins?"*. Collaboration asks *"why should anyone lose?"*.

---

## The one-paragraph version

The document stops being a file that two clients overwrite and becomes a **Yjs document** that two
clients merge. The browser holds a `Y.Doc`; the server holds an authoritative `pycrdt` replica in the
same FastAPI process; Lakebase persists the update log and periodic snapshots. The agent stops
emitting whole-file writes and starts emitting **operations** — insert a cell, replace a range,
delete a cell — so its edits merge with a human's keystrokes instead of clobbering them. The
workspace API becomes an **export target**, not the source of truth: a notebook is written out on
demand and on a schedule, and imported once, at open. The version token, the 409 path, and the
conflict panel are deleted.

The hard parts are not the merge. They are: **the agent's write path must become operation-based**,
**the workspace must be reconciled from a CRDT that outlives it**, and **Databricks Apps must accept
a websocket** — which is unverified and is the first thing to probe.

---

## What changed in the world since 003 D9

D9 rejected a CRDT on three grounds. Each is re-checked here rather than hand-waved.

| D9's objection | Status now | Verdict |
|---|---|---|
| "Both writers produce a whole-file replacement; there is nothing to merge" | Still true — *this is the work* | **Accepted, and it is the main engineering task** ([§Agent as a peer](02-architecture.md#agent-as-a-peer)) |
| "Storage mints a new identity on every write" | Still true (`overwrite` + `format=SOURCE` is refused, so save is delete-then-import) | **Dissolved**: identity moves to the CRDT document id, which we control. The workspace stops being the identity authority. |
| "No channel for deltas" | **False now** — `pycrdt` (Yrs bindings, Python ≥3.11) + `pycrdt-websocket` run in the existing FastAPI process | **Accepted**: one process, one language, no sidecar |

Measured, on this machine, 7 November 2026:

| Package | Version | Unpacked | Weekly downloads |
|---|---|---|---|
| `yjs` | 13.6.33 | 2.3 MB | 15 518 847 |
| `y-protocols` | 1.0.7 | 1.1 MB | 8 564 246 |
| `y-indexeddb` | 9.0.12 | 1.1 MB | 1 257 544 |
| `@hocuspocus/server` | 4.8.0 | 0.8 MB | 1 872 047 |
| `pycrdt` | 0.14.13 | — | (PyPI) |
| `pycrdt-websocket` | 0.16.8 | — | (PyPI) |

The client bundle cost is **yjs + y-protocols + y-indexeddb ≈ 4.5 MB unpacked**, which after gzip is
in the same class as the CodeMirror chunk already shipped (228 KB gz). That is affordable, which it
would not have been if we were also carrying Monaco.

---

## Scope

**In scope**

- A Yjs `Y.Doc` per document, with cells as a `Y.Array<Y.Map>` — ids, kinds, languages, sources.
- A websocket collaboration service inside the existing FastAPI app (`pycrdt`), authoritative.
- Presence: who is here, where their caret is, what they have selected.
- Agent writes as **operations** against the live document.
- Persistence in Lakebase: update log + snapshot cadence.
- Export to the workspace on save and on a timer; import once on first open.
- Offline editing via `y-indexeddb`, converging on reconnect.
- Removing 003's version token, 409 path, and conflict panel.

**Out of scope, and why**

| Not doing | Reason |
|---|---|
| CRDT history / time travel UI | The workspace keeps notebook revisions; a second history is a product, not a feature |
| Rich-text (ProseMirror) cells | Cell sources are plain text. `y-prosemirror` is the wrong tool for code |
| Cross-document transactions | Two documents are two documents. Multi-doc atomicity is a database feature, not an editor one |
| Replacing the CodeMirror binding | `y-codemirror.next` exists; the editor host from 003 D6 already isolates the swap |
| Permissions inside the CRDT | Unity Catalog and workspace ACLs stay the authority. The CRDT carries no ACL, only document content |

---

## Reading map

| # | Document | The question | Lead lens |
|---|---|---|---|
| 00 | [Why, and the trade](00-why-first-principles.md) | What does collaboration buy that a conflict dialog cannot? | PO + AI |
| 01 | [Current state and the blockers](01-current-state.md) | What exists, measured? What breaks? | Full-stack |
| 02 | [Architecture](02-architecture.md) | How is it built? What dies? | Compiler + AI |
| 03 | [Implementation plan](03-implementation-plan.md) | In what order, with what acceptance? | Full-stack |
| 04 | [Edge cases, tests, risks](04-edge-cases-risks.md) | What can go wrong? | all |

---

## The first probe, before any code

**Does Databricks Apps accept a websocket?** Everything here depends on it, and it is not documented
in a way we can rely on. This is not a design question — it is a 20-line test:

1. add a `/api/ws-echo` endpoint to the existing app;
2. `databricks apps deploy`;
3. connect from a browser and from `websocat`;
4. record the result in [01](01-current-state.md#the-websocket-question).

If websockets are refused or silently buffered by the platform proxy, the fallback is **long-polling
deltas over HTTP** — worse latency, same convergence, and the architecture in
[02](02-architecture.md) survives with one transport swapped. If they work, proceed as designed.

> **Do not start phase 2 before this probe returns.** A CRDT design that assumes a channel it does
> not have is exactly the mistake [003 D9](../003-improve-dev-ux-ui/07-decisions-risks.md#d9-no-crdt-in-this-design)
> was written to prevent.

---

## The five sentences this spec must satisfy

1. **Two people typing in the same cell never lose a character.** Not "usually"; convergence is a
   property of the data structure, and it is tested as one.
2. **The agent and a human can edit the same cell at the same time** and both edits survive, because
   neither is a whole-file write.
3. **A notebook is still a notebook on disk**: what the workspace holds is parseable SOURCE, and
   what it holds converges to the CRDT within one save interval.
4. **Going offline loses nothing** and nothing is replayed twice on reconnect.
5. **The conflict panel is gone**, and with it the sentence "your changes were discarded" — there is
   no longer a code path that can produce it.
