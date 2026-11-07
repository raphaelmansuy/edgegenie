# 03 · Implementation plan

[Index](README.md) · prev: [02 Architecture](02-architecture.md) · next: [04 Edge cases and risks](04-edge-cases-risks.md)

Six phases. Ordering principle: **prove the hard properties before building the surface.** The
interleaving test and the convergence property come before the websocket UI, because if YATA fails
our access pattern there is no point building around it.

```
P0 probe ──► P1 durable store ──► P2 convergence harness ──► P3 transport
                                                                   │
                                                     P4 operation tools
                                                                   │
                                                     P5 projection + presence
                                                                   │
                                                     P6 delete 003's conflict path
```

---

## P0 · The websocket probe

**Goal:** know the transport before designing for it. Half a day.

| Work | Acceptance |
|---|---|
| add `GET /api/ws-echo` returning a single frame | local: connects, echoes |
| deploy to Databricks Apps | deployed: connects, echoes |
| send 200 × 1 KB frames, measure inter-arrival | frames arrive **individually**, not coalesced into one |

**Exit criterion:** either websockets work (proceed to P3 as designed) or they do not (P3 becomes
long-polling, and this document is amended *before* further code).

**If it fails:** the fallback keeps C5 — a long-poll that carries `(state vector → update)` pairs in
order per document. Worse latency, same convergence. Record the measured latency so the decision is
evidence-based.

---

## P1 · Durable CRDT store

**Goal:** a `Y.Doc` survives a process restart.

| Work | File | Acceptance |
|---|---|---|
| `pycrdt` + `pycrdt-websocket` pinned in **both** `requirements.txt` and `pyproject.toml` | — | `tests/test_packaging.py` passes; deploy installs them |
| `CrdtStore` port | `api/domain/crdt.py` | protocol: `append(doc_id, update, at)`, `since(doc_id, seq)`, `snapshot(doc_id, state, seq)` |
| `MemoryCrdtStore` | `api/adapters/memory/crdt.py` | used by tests and demo |
| `LakebaseCrdtStore` | `api/adapters/lakebase/crdt.py` | migration; append is idempotent on `(doc_id, seq)` |
| snapshot policy | `api/services/crdt.py` | snapshot every N updates **or** after 1 MB of log, whichever first |

**Test that matters:** create a doc, apply 100 updates, **restart the process**, reopen — the
document is byte-identical. If this fails, everything downstream is unsound.

---

## P2 · The convergence harness (before any transport)

**Goal:** prove SEC on our data type *without* a network, because a network bug and a CRDT bug look
identical from the outside.

| Work | Acceptance |
|---|---|
| `tests/crdt/convergence.py` — generate N replicas, random ops, converge pairwise in a random order | for 500 trials: every permutation reaches the same state |
| **the interleaving regression** (see below) | PaPoC scenarios pass |
| property: apply the same update set twice = once | idempotence (CvRDT side) |
| property: causal vs. shuffled delivery | shuffled-but-causal converges; *non-causal* is detected, not silently accepted |

### The interleaving test, spelled out

From Kleppmann et al., [PaPoC '19](https://martin.kleppmann.com/papers/interleaving-papoc19.pdf),
adapted to our model. The scenario that breaks Logoot/LSEQ:

```
base:      "Hello|!"            (| = insertion point)
replica A: insert " Alice"      at |
replica B: insert " Charlie"    at |
merge must be ONE of:
   "Hello Alice Charlie!"
   "Hello Charlie Alice!"
must NEVER be:
   "Hello AChlairliece!"        ← character interleaving
```

And the RGA lesser-anomaly variant, which we must also test because it is subtler:

```
base:  "Hello|!"
A: types " reader", then moves the caret back and types " dear"
B: (idle)
merge must produce a readable word order, not "de ar rea der"
```

**Assertion style:** not "equals one expected string" — YATA is allowed to pick either order — but
**"each inserted run appears contiguously"**. That is the property the paper's added clause 1(d)
states, and it is exactly what a naive equality test would miss.

**If Yjs fails this**, the finding is: our access pattern (concurrent inserts in one `Y.Text`) is
outside YATA's guarantee for these cases, and the mitigation is to make cell-level concurrency the
unit — a cell is locked while one participant is *typing in it*, which is a UI-level fix, not a
protocol one. Record the result either way.

---

## P3 · Transport

**Goal:** two browsers converge through the server.

| Work | Acceptance |
|---|---|
| `pycrdt-websocket` mounted at `/api/ws/documents/{docId}` | connects; two clients converge under 200 ms on localhost |
| auth at connect (workspace ACL) | a user without access is refused with 4403, not a silent empty doc |
| state-vector sync on connect | a client with 0 knowledge receives exactly the missing bytes, not the whole doc |
| reconnect with backoff | kill the socket: rejoins and converges without duplicating ops |
| awareness channel | two carets visible; a disconnect removes the caret within 30 s |

---

## P4 · Operation tools for the agent

**Goal:** C1. The agent stops writing files.

| Tool | Replaces |
|---|---|
| `doc_insert_cell(path, at, cell)` | — |
| `doc_replace_source(path, cell_id, from, to, text)` | `dbx_write_notebook` for small edits |
| `doc_set_kind(path, cell_id, kind)` | — |
| `doc_move_cell(path, cell_id, to)` | — |
| `doc_delete_cell(path, cell_id)` | — |
| `doc_write_notebook(path, cells)` | `dbx_write_notebook`, now **one transaction** |

| Work | Acceptance |
|---|---|
| handlers in `tools/crdt_tools.py`, each one transaction | a tool call is atomic: a failure mid-way leaves nothing |
| fence preserved | `check_path` still runs; an out-of-fence path still asks |
| `doc_write_notebook` expressed as operations | property: applying it to an empty doc yields exactly `cells` |
| **merge test:** human types in cell 2 while the agent replaces cell 2 | both survive, or the agent's change is proposed (see 02 §Proposals) |

That last acceptance is the whole spec in one test.

---

## P5 · Projection and presence

**Goal:** C6 made honest.

| Work | Acceptance |
|---|---|
| export on save / 5 s idle / close | workspace content converges to the CRDT within the interval |
| temp-path export to avoid the delete-window | a reader never sees a missing notebook |
| "exported 4 s ago" in the editor bar | the age is shown, not guessed |
| presence carets | visible, coloured, clipped to the cell |
| stale caret clamped | a caret at a stale offset lands at the end of the cell, not mid-word |

---

## P6 · Delete 003's conflict path

**Goal:** the CRDT is load-bearing, not decorative.

| Work | Acceptance |
|---|---|
| delete `ConflictPanel.tsx`, its CSS, its tests | **no test asserts conflict behaviour**, because there is none |
| delete `version.py`, the 409 branch in `save` | `grep -r "409" api/` finds only unrelated uses |
| withdraw CX-1..CX-5 in `specs/003` | a note points here |
| the e2e `conflict` scene is replaced by a **concurrent-edit** scene | two contexts type in the same cell; both texts present |

> If `ConflictPanel` cannot be deleted, this project has failed regardless of what else works.

---

## Risk table

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Websockets refused by the platform** | medium | **high** | P0 first; long-poll fallback preserves C5 |
| **YATA interleaves for our access pattern** | low-medium | high | P2 tests it before any UI; mitigation is cell-level typing lock |
| Lakebase adapter adds deploy weight | medium | medium | memory store stays default in demo mode |
| `pycrdt` wheel unavailable on the deploy image | medium | high | P1 pins and deploys early; fallback is a Node sidecar (worse: second runtime) |
| Agent tool latency (open doc per call) | high | medium | cache the server replica per `docId` for the process lifetime |
| Tombstone growth on a long-lived doc | medium | medium | GC on + snapshot compaction |
| Two replicas diverge in a way tests miss | low | **critical** | P2's permutation tests + a checksum assertion on every export |

---

## Definition of done

1. Two clients type in the same cell; neither character is lost. Tested.
2. The agent edits the cell a human is editing; both survive, or a proposal is offered. Tested.
3. A process restart loses nothing. Tested.
4. Offline for 5 minutes, then reconnect: no duplicate application, no loss. Tested.
5. The workspace file matches the CRDT within one export interval, and the UI says how old it is.
6. `ConflictPanel.tsx` and `version.py` no longer exist.
7. Every standing audit from 001/003 is still green: `a11y` 0 findings both themes, `cls` 0.0000,
   `overflow` 0/20.

[Next: edge cases, tests, risks →](04-edge-cases-risks.md)
