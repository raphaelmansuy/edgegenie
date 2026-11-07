# 00 · Why, from first principles

[Index](README.md) · next: [01 Current state](01-current-state.md)

This document derives the design from the **formal definition** of a CRDT rather than from a library
API, because the formal definition tells you what you must supply and a library API tells you what
it will do for you. Where a claim comes from a source, the source is linked.

---

## The five whys

**1. Why do we want collaboration?**
Because two people cannot edit the same notebook in this app at the same time, and one of them is
usually an agent.

**2. Why can they not?**
Because a document is a **whole file** that is replaced: the agent calls `dbx_write_notebook(cells)`,
the human posts the entire text, and whichever lands second wins. 003 wrapped that in a version
token and a conflict dialog — which detects the collision and makes a human resolve it.

**3. Why is a conflict dialog the wrong answer for this product?**
Because the entity most likely to collide with you is *the agent you just asked to change the file*.
A dialog that says "somebody else changed this file" is, in the common case, a dialog that says "the
assistant did the thing you asked, and now you must reconcile it by hand." That is not a rare race;
it is the product's core loop failing at its most valuable moment.

**4. Why does a CRDT fix that where a dialog cannot?**
Because the collision is not between two *files*, it is between two *edits*. A CRDT merges edits.
A dialog can only choose between files. The difference is not quality — it is the unit of merge.

**5. Why is the unit of merge the whole design?**
Because everything follows from it: what the agent must emit, what the server must store, what the
client must hold, what can be promised to the user. Get the unit wrong and you build a very good
conflict detector. Get it right and conflict stops being a concept.

---

## First principles: the formal definition

Shapiro, Preguiça, Baquero and Zawirski define the target property, **Strong Eventual Consistency**,
in two parts ([*Conflict-free Replicated Data Types*, INRIA RR-7687, §2.2](https://hal.science/inria-00609399/document)):

> **Definition 2.2 (Eventual Consistency).**
> *Eventual delivery:* an update delivered at some correct replica is eventually delivered to all
> correct replicas.
> *Convergence:* correct replicas that have delivered the same updates eventually reach equivalent
> state.

> **Definition 2.3 (Strong Eventual Consistency).** Eventual delivery *and*: any two correct
> replicas that have delivered the same updates **have equivalent state**, immediately — no
> further communication required.

The difference between EC and SEC is the word *immediately*. Under EC, replicas agree eventually;
under SEC, once they have seen the same updates they **already** agree. No rollback, no consensus,
no arbiter.

They then give two sufficient conditions, and this is the part that constrains our design:

> **Theorem 2.1 (CvRDT).** Any **state-based** object whose payload forms a **monotonic semilattice**
> under merge — where merge `m` is the least upper bound, and therefore *commutative*, *idempotent*
> and *associative* — is SEC.

> **Theorem 2.2 (CmRDT).** Any **operation-based** object whose concurrent operations **commute**,
> given causal delivery, is SEC.

Read those two theorems as an **obligation**. To claim SEC, this system must supply either:

```
state-based     a join semilattice:        merge is LUB, monotonic, idempotent, commutative
operation-based concurrent ops commute,    with causal delivery guaranteed
```

**This is the first principle of the whole spec: convergence is not a feature you add, it is a
property your data type must have.** Every design decision below is either "we satisfy one of these
two conditions" or "we are not claiming SEC here".

---

## Axioms for this design

Each axiom is a consequence of the above, applied to *this* product.

### C1 · Merge must operate on edits, not documents

From Theorem 2.2. Two whole-file replacements do not commute — they overwrite, which is a
last-writer-wins register, which is not a CRDT for text. So:

**The agent must emit operations, not files.** This is the single largest change in the spec and it
is forced by the theorem, not chosen for elegance.

```
not a CRDT:   write(path, full_text)            ← last writer wins
a CRDT:       insert(cell, at), delete(cell),   ← concurrent ops commute
              replace(range, text)
```

### C2 · Yjs is a sequence CRDT, so the *sequence* is the unit

Yjs "is a list CRDT. Everything is squeezed into a list in order to reuse the CRDT resolution
algorithm" ([Yjs INTERNALS](https://github.com/yjs/yjs/blob/main/INTERNALS.md)). Each item carries an
`ID(clientID, clock)` — a Lamport timestamp — plus `origin` and `originRight` references used to
resolve concurrent inserts at the same position.

**Consequence:** the notebook must be modelled as a `Y.Array<Y.Map>`, not as a JSON blob. A blob
would merge at the wrong granularity — one cell edit would replace the whole array.

### C3 · Interleaving is the failure mode to design against, and Yjs's algorithm is the right one

This is where "best knowledge in the world" changes the design. Kleppmann, Gomes, Mulligan and
Beresford, [*Interleaving anomalies in collaborative text editors* (PaPoC '19)](https://martin.kleppmann.com/papers/interleaving-papoc19.pdf):

> "Several published algorithms for collaborative text editing exhibit an undesirable anomaly in
> which concurrently inserted portions of text with a well-defined order may be randomly interleaved
> on a character-by-character basis, resulting in **an unreadable jumble of letters**."

They show that **Logoot and LSEQ suffer this** (their identifiers are dense positions in a rational
interval, so two concurrent insertions in the same gap interleave arbitrarily), and that **RGA has a
lesser variant** ("text may be interleaved if insertions are not sequential"), with the worst case
when a user types back-to-front.

Yjs does not use RGA. Yjs implements **YATA** — Nicolaescu, Jahns, Derntl and Klamma,
[*Near Real-Time Peer-to-Peer Shared Editing on Extensible Data Types*, GROUP '16](https://doi.org/10.1145/2957276.2957310),
whose stated properties are "ensures convergence, **preserves user intentions**, allows offline
editing".

> **This is a load-bearing choice, and it must be tested rather than assumed.** YATA's
> `origin`/`originRight` design is intended to prevent interleaving, but "intended" is not "proved
> for our access pattern". [04](04-edge-cases-risks.md#c-sequence-and-interleaving) therefore includes
> an executable interleaving regression built from the PaPoC scenarios. If Yjs fails one, we would
> know before shipping — and would know that the PaPoC '19 finding applies to our engine.

### C4 · Deletion is state-based and *cannot* be undone by merge

From the Yjs internals: "Insertions are implemented as a sequential operation based CRDT, but
deletions are treated as a simpler state based CRDT… Yjs does not record metadata about a deletion…
the clientID's clock is not incremented."

**Consequences, which are user-visible:**

- delete is **irreversible by merge**: no concurrent insert can resurrect a deleted item;
- with garbage collection on, the content is replaced by a `GC` struct and the text is **gone**;
- therefore **restore is an application concern**, not a CRDT one. This is why 003's draft store is
  retained rather than deleted ([02 §What survives](02-architecture.md#what-survives)).

### C5 · Causality is required, so the transport is part of the correctness argument

Theorem 2.2 needs **causal delivery**. Yjs's protocol supplies the mechanism: a *state vector* — a
set of `(client, clock)` pairs — exchanged to compute the minimal missing update
([INTERNALS §Network protocol](https://github.com/yjs/yjs/blob/main/INTERNALS.md)).

**Consequence:** the websocket is not an optimisation, it is a correctness dependency. If the
platform cannot carry it, the design must fall back to HTTP long-polling *that still preserves
causal order per document* — not to "sync occasionally".

### C6 · The workspace is a projection, not the truth

Because the CRDT is the thing that converges, and the workspace API only accepts whole-file imports,
the workspace must become an **export target**. Its content is a *lossy projection* of the CRDT at a
point in time.

**Consequence, stated as a limitation:** between exports, the workspace and the CRDT differ. Any
reader outside this app sees the last export. That is acceptable only because the export is frequent
and the window is bounded — and it must be visible in the UI, not hidden.

### C7 · Offline is a consequence, not a feature

YATA's paper claims offline editing as a property. It falls out of C1–C5: a client with a `Y.Doc` in
`y-indexeddb` can accept local edits while disconnected and converge on reconnect, because the ops
commute and the state vector lets the peer compute exactly what is missing.

**Consequence:** "offline" needs no separate mechanism, but it does need **durable local storage** and
a **reconnect that replays nothing twice** — both are edge cases with tests
([04 D](04-edge-cases-risks.md#d-offline-and-reconnect)).

---

## What the first principles rule out

| Temptation | Which principle kills it | Why |
|---|---|---|
| Store the notebook as one `Y.Text` of the whole file | C2 | A single sequence means a cell move is a huge splice, and the cell model from 003 is lost |
| Keep whole-file agent writes and *also* add a CRDT | C1 | The file write is last-writer-wins; it destroys the merge and you are back to a conflict dialog with extra steps |
| Use `Y.Map` for cells keyed by id, no array | C2, C3 | Maps have no order. Order is half of a notebook |
| Treat delete as reversible by merge | C4 | It is not, by construction. Restore must be ours |
| Assert "no interleaving" because we use Yjs | C3 | YATA is *designed* for it; we must still **test** it for our access pattern |
| Skip the websocket and "sync every 30 s" | C5 | Without causal delivery per document, Theorem 2.2 does not apply and the convergence claim is unfounded |
| Claim the workspace file is always current | C6 | It cannot be. Say "exported 4 s ago" instead |
| Build presence on a separate polling loop | C5 | Presence rides the same causal channel; a second channel can show a caret at a stale position |

---

## The cost, stated up front

A CRDT is not free, and the honest accounting is:

| Cost | Magnitude | Why it is worth it here |
|---|---|---|
| The agent's write path changes | every write tool | It is the entire point (C1) |
| A new stateful service | 1 websocket + 1 replica per open doc | Required by C5 |
| Persistence | update log + snapshots in Lakebase | Replicas are memory; a restart must not lose ops |
| A projection layer | export on save + timer | C6 |
| Tombstones | grow with deletions | Yjs GC handles content; ids remain |
| Testing | convergence is a *property*, so properties must be tested | [04](04-edge-cases-risks.md) |

And the benefit is one sentence: **the moment the agent edits the file you are editing stops being
an error case.**

---

## Sources

All links are to primary sources, checked 7 November 2026. Where a publisher's DOI resolver
returns 403 to a script (bot protection, not a dead link), an open mirror is given and marked
*verified 200*. Two hosts — `hal.science` and `researchr.org` — refused the connection from this
machine; the equivalent PDF is linked from `lip6.fr` instead.

| Claim | Source |
|---|---|
| SEC definition; CvRDT/CmRDT sufficient conditions | Shapiro, Preguiça, Baquero, Zawirski — [*CRDTs*, INRIA RR-7687 (PDF, verified 200)](https://www.lip6.fr/Marc.Shapiro/papers/RR-7687.pdf) · [SSS 2011 (PDF, verified 200)](https://www.lip6.fr/Marc.Shapiro/papers/2011/CRDTs_SSS-2011.pdf) · HAL record `inria-00609399` |
| Interleaving anomaly; Logoot/LSEQ/RGA affected | Kleppmann, Gomes, Mulligan, Beresford — [*Interleaving anomalies in collaborative text editors*, PaPoC '19](https://martin.kleppmann.com/papers/interleaving-papoc19.pdf) |
| YATA algorithm; convergence + intention + offline | Nicolaescu, Jahns, Derntl, Klamma — GROUP '16, pp. 39–49, **doi:10.1145/2957276.2957310** · [open copy, verified 200](https://dl.eusset.eu/items/b52fa5b8-306d-4727-9769-4057262152a7) |
| Yjs internals: list CRDT, Lamport IDs, state vectors, deletion semantics | [yjs/yjs INTERNALS.md](https://github.com/yjs/yjs/blob/main/INTERNALS.md) |
| `Y.Doc` API: transactions, `update` events, `gc` | [docs.yjs.dev/api/y.doc](https://docs.yjs.dev/api/y.doc) |
| Mechanised proofs for RGA, OR-Set, counters | Gomes, Kleppmann, Mulligan, Beresford — OOPSLA '17, **doi:10.1145/3133933** · [arXiv:1707.01747, verified 200](https://arxiv.org/abs/1707.01747) |
| Local-first framing, offline as a first-class goal | Kleppmann, Wiggins, van Hardenberg, McGranaghan — [*Local-first software*, Onward! '19](https://martin.kleppmann.com/2019/10/23/local-first-at-onward.html) |

[Next: what exists today, and what blocks it →](01-current-state.md)
