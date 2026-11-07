# 04 · Edge cases, tests, risks

[Index](README.md) · prev: [03 Implementation plan](03-implementation-plan.md)

Each case has **what happens**, **the mitigation**, and **the test that fails if the mitigation is
removed**. Groups: **A** convergence properties · **B** the agent as a peer · **C** sequence and
interleaving · **D** offline and reconnect · **E** projection and the workspace · **F** presence.

---

## A · Convergence properties

These are not "edge cases" in the usual sense — they are the **definition** of correctness. If A
fails, nothing else matters.

| # | Property | Why it can fail | Test |
|---|---|---|---|
| A1 | **Commutativity**: applying two concurrent updates in either order gives the same state | A single `Y.Text` insert is commutative by construction; a *nested* type created out of order is the risk | 500 trials: random op pairs, both orders, assert equal state bytes |
| A2 | **Idempotence**: applying the same update twice changes nothing | A re-sent update after reconnect | apply update twice; assert state hash equal |
| A3 | **Convergence over permutations**: for N replicas with a shared op set, every delivery order converges | The core SEC claim | sort-free permutation test: 6 replicas × 40 ops × 20 permutations |
| A4 | **Causal delivery is required, and its absence is detected** | A websocket that reorders would silently break Theorem 2.2 | deliver out of causal order deliberately; assert the store **rejects** rather than corrupting |
| A5 | **No divergence across restart** | In-memory replica lost; ops replayed from the log | restart the process mid-stream; assert byte-identical state |
| A6 | **Export checksum**: the exported SOURCE parses to the same cells the CRDT holds | The projection is lossy in principle | on every export in tests, `parse(export) ≡ crdt.cells` |

**A4 deserves emphasis.** With state-based sync, order does not matter (that is Theorem 2.1). With
operation-based, it does (Theorem 2.2). Yjs is a **hybrid**: inserts are op-based, deletes are
state-based ([INTERNALS](https://github.com/yjs/yjs/blob/main/INTERNALS.md)). So the honest statement
is: *Yjs is robust to reordering because its insert resolution uses origin references, not arrival
order* — and A4 exists to test that claim rather than trust it.

---

## B · The agent as a peer

| # | Case | Mitigation | Test |
|---|---|---|---|
| B1 | Human typing in cell 2 while the agent replaces cell 2's source | The agent's `doc_replace_source` targets a range; the human's concurrent inserts inside that range survive as a `Y.Text` merge | two clients + a tool call; assert both texts present |
| B2 | Agent deletes the cell the human is typing in | Delete wins (C4: deletion is not resurrectable). The human's text must be **recoverable** | the draft store keeps it; assert restore works |
| B3 | Agent writes a whole notebook over a live doc | One `transact`; concurrent human text inside survives | B1's assertion with `doc_write_notebook` |
| B4 | Agent and human both add a cell at index 3 | Both cells exist; order is deterministic per YATA | assert 2 cells, order stable across both replicas |
| B5 | Agent's tool call arrives after its session was cancelled | The tool checks the session is live before opening the doc | cancelled session → tool returns "not applied", no write |
| B6 | Agent replaces a range the human has *selected but not yet typed over* | Proposal path (02 §Proposals) | assert the proposal state appears, and reject restores byte-identical |
| B7 | Agent loops: replaces the same range 100× in a second | Each is one transaction; the log grows | assert compaction triggers; assert no update storm > 50/s |
| B8 | Agent writes outside the fence while collaborating | `check_path` runs before the doc is opened | out-of-fence tool call → ASK, no doc mutation |
| B9 | Two agent turns write at once | Server replica serialises per `docId` | parallel tool calls; assert both applied, no lost update |

---

## C · Sequence and interleaving

The group that "best knowledge in the world" says to worry about. From
[PaPoC '19](https://martin.kleppmann.com/papers/interleaving-papoc19.pdf): Logoot and LSEQ interleave
arbitrarily; RGA has a lesser variant; YATA is designed to avoid it.

| # | Case | What the literature says | Test |
|---|---|---|---|
| C1 | Two concurrent word insertions at the same offset | Logoot/LSEQ produce "an unreadable jumble of letters". RGA gives two clean outcomes | assert **each inserted run is contiguous**; either order allowed |
| C2 | RGA's lesser anomaly: one user types ahead, then back | RGA interleaves if insertions are non-sequential (worst case: typed back-to-front) | the PaPoC Figure 4 sequence; assert readable word order |
| C3 | Character-by-character typing from two clients at the same offset | The pathological case for any position-based scheme | 20 chars from A, 20 from B, interleaved in time; assert both runs contiguous |
| C4 | Concurrent insert inside a **markdown** cell while a code cell is edited | Nested `Y.Text`s must not interfere | assert both cells correct, no cross-talk |
| C5 | Concurrent edit of the same character (one deletes, one edits after it) | Delete is state-based and wins; the edit anchors to a tombstone | assert the edited text appears, no crash, no orphan |
| C6 | Cell moved by A while B types in it | The `Y.Map` moves; the nested `Y.Text` moves with it | assert the text follows the cell and is not lost |

**How C1–C3 are asserted.** Not "equals `Hello Alice Charlie!`" — YATA may legitimately choose the
other order. The assertion is the paper's clause 1(d): **the insertions are not interleaved**. In
practice:

```python
def assert_contiguous(merged: str, runs: list[str]) -> None:
    """Each concurrently inserted run must appear as one uninterrupted substring."""
    for run in runs:
        assert run in merged, f"{run!r} was split or lost: {merged!r}"
```

This is the test that would have caught the Logoot-class bug, and it is cheap.

---

## D · Offline and reconnect

| # | Case | Mitigation | Test |
|---|---|---|---|
| D1 | Offline for 5 min, 200 local ops, reconnect | state vector exchange delivers exactly the missing ops | go offline, edit, reconnect; assert convergence and op count |
| D2 | Reconnect delivers the same ops twice | A2 idempotence | force a duplicate sync; assert state unchanged |
| D3 | Two offline clients edit the same cell, then both reconnect | Both merge; C1-style contiguity applies | assert no loss, contiguous runs |
| D4 | Browser closed with unsaved ops, reopened | `y-indexeddb` retains them | close/reopen; assert the text is there |
| D5 | `y-indexeddb` rejected (private mode, quota) | degrade to memory; the session is still usable | stub a throwing IndexedDB; assert no fatal error |
| D6 | System clock changes | Yjs IDs are `(clientID, clock)` — logical, not wall-clock | skew the clock; assert convergence |
| D7 | Two tabs, same user, same doc | Same `clientID` would be a bug; each tab is its own client | assert distinct clientIDs, both converge |
| D8 | A very long offline period (days) | log replay bounded by snapshot | assert load time stays under a threshold with a large log |
| D9 | Stale local state after a server-side compaction | snapshot seq is authoritative; client re-syncs from its vector | compact then reconnect; assert convergence |

---

## E · Projection and the workspace

| # | Case | Mitigation | Test |
|---|---|---|---|
| E1 | Export while a reader is looking at the notebook | temp-path export, then swap (01 §write mechanics) | assert the object never 404s during export |
| E2 | Export fails mid-way (delete succeeded, import failed) | Retry; the CRDT still holds the truth, so nothing is lost | inject an import failure; assert the CRDT is unchanged and the next export succeeds |
| E3 | Workspace edited **outside** the app during a session | **The projection overwrites it.** This is the cost of C6, stated in the UI | assert the UI warns when `modified_at` moved since the last export |
| E4 | Notebook deleted in the workspace while open | export recreates it | delete then export; assert created |
| E5 | Export of a document whose CRDT has a truncated cell | refuse to export (003 D7) | assert export blocked with a reason |
| E6 | A 400 KB+ document | export works; the *import* path refuses it read-only | assert the size guard still applies |
| E7 | Two app instances export the same doc | last export wins; content converges because both project the same CRDT | assert identical bytes from both |
| E8 | Export storms (edit every 100 ms) | debounce: 5 s after the last update | assert ≤ 1 export per debounce window |

**E3 is the honest limitation of this whole design** and must appear in the UI, not just the spec: a
person editing the same notebook in the Databricks workspace editor, concurrently with this app, will
have their changes overwritten at export. There is no mechanism to merge them — the workspace has no
CRDT. The mitigation is a warning, not a fix.

---

## F · Presence

| # | Case | Mitigation | Test |
|---|---|---|---|
| F1 | Two users, carets in the same cell | both rendered, distinct colours | assert 2 carets |
| F2 | User disconnects | caret expires after 30 s | kill the socket; assert gone |
| F3 | Caret at an offset that no longer exists | clamp to the cell's end | delete text under a remote caret; assert clamped |
| F4 | 20 participants | presence is throttled; document updates never blocked | assert update latency unaffected |
| F5 | Participant with a stale document | presence carries the doc version; a stale caret is shown greyed | assert greyed state |
| F6 | Colour collision | colour is derived from `clientID`, collisions allowed and acceptable | n/a — documented |

---

## The test map

| Group | Harness | Gate |
|---|---|---|
| A1–A6 | `pytest` — `tests/crdt/test_convergence.py` | all permutations converge, 500 trials |
| B1–B9 | `pytest` with two replicas + tool calls | both texts present, no loss |
| C1–C6 | `pytest` — `tests/crdt/test_interleaving.py` | **contiguity**, not equality |
| D1–D9 | Playwright two-context + `pytest` | convergence after reconnect, no duplicate |
| E1–E8 | `pytest` with a fake workspace | no 404 window; refusal on truncated |
| F1–F6 | Playwright | carets, expiry, clamping |
| all | `audit:a11y` (both themes), `audit:cls`, `audit:overflow` | 0 findings, 0.0000, 0/20 |

---

## Risks, in order of how much they hurt

| # | Risk | Impact | Mitigation | Residual |
|---|---|---|---|---|
| 1 | Websockets refused by the platform | high | P0 probe; long-poll fallback keeping C5 | latency |
| 2 | YATA interleaves for our access pattern | high | P2 before UI; cell-level typing lock as fallback | reduced concurrency |
| 3 | `pycrdt` unavailable on the deploy image | high | P1 deploys a trivial endpoint using it *first* | a Node sidecar: worse |
| 4 | E3 — external writer overwritten | medium | warn in the UI | **unavoidable**: the workspace has no CRDT |
| 5 | Divergence that tests miss | critical | permutation tests + export checksum | unknown-unknowns |
| 6 | Tombstone growth | medium | GC + compaction | history loss (accepted) |

### The one residual risk we cannot engineer away

**E3.** If a colleague edits the notebook in the Databricks workspace editor while this app has the
document open, the next export overwrites them, silently, from their point of view. A CRDT cannot
help: the workspace is not a replica and cannot carry a merge.

The only honest mitigations:

1. show "exported 4 s ago" so the window is visible;
2. compare `modified_at` before export and **refuse** if it moved since our last export, surfacing
   "this file was changed outside the app" — the one place 003's version check survives, repurposed
   from *conflict* to *foreign-write detection*;
3. document it.

Option 2 is worth doing: it keeps 003's version token alive for exactly the case where it is still
the right tool.
