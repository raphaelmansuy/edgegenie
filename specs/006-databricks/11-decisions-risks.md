# 11 · Decisions and risks

[Index](README.md) · prev: [10 Edge cases](10-edge-cases-testing.md) · next: [12 E2E and screenshots](12-e2e-plan.md)

Two lists: what we decided and would defend, and what we are afraid of and have not solved.

---

## Decisions

Each decision names the alternative it beat. A decision with no alternative is not a decision, it is a
habit.

### D1 · The assistant is a zone, not a tab

**Chosen.** `rail | centre | dock` at wide widths, a drawer below.
**Rejected:** keeping the conversation a tab and adding a split view.
**Why:** a split view of two tabs is still one slot; the user still loses the file when scrolling, and
the stream would be duplicated ([03](03-architecture.md)). The zone model already exists and is tested.

### D2 · `Focus` is a domain value, not derived state

**Chosen.** `{docId, cellId?}` with pure transitions, in `domain/focus.ts`.
**Rejected:** deriving "what is in context" from whichever document happens to be rendered.
**Why:** that derivation is the root cause in [00 §5](00-why-first-principles.md#the-five-whys). It is
also untestable without a DOM.

### D3 · The run button is removed, not implemented

**Chosen.** Delete `.cell-run` and its handler; a cell can be *asked about*, not *run*.
**Rejected:** wiring the run button to a shell execution, or to `spark.sql` through the existing tool
server.
**Why:** NB-6 in [003](../003-improve-dev-ux-ui/03-architecture.md) says there must not be a second
executor, and the real one is the agent's tool path with its audit and fence. A cell that runs without
the fence, the approval and the audit would be a hole in the product's central promise. Implementing
it properly is its own spec.
**Consequence, stated plainly:** this spec makes the notebook *worse-looking* in one way — a button
disappears — and honest in exchange. Cell execution remains the largest functional gap
([03 §what this does not solve](03-architecture.md#what-this-architecture-does-not-solve)).

### D4 · The approval is inline in the dock, and stays a sheet in the centre

**Chosen.** Two renderings of one endpoint.
**Rejected:** moving every approval into the dock; or keeping the modal everywhere.
**Why:** the sheet covers the code the approval is about, which is a defect in the dock context and
fine in the chat-tab context. Both call `api.decide`, so they cannot disagree about the outcome. This
is a deliberate inconsistency, recorded so a reviewer does not "fix" it.

### D5 · One `EventSource`, two views

**Chosen.** The dock reads the state `useSessionStream` already owns.
**Rejected:** a dedicated stream for the dock.
**Why:** double fan-out, and two writers to one replay cursor in `localStorage`
([`useSessionStream.ts:76`](../../apps/coding-agent/web/src/hooks/useSessionStream.ts)).

### D6 · One `Composer`, a `variant` prop

**Chosen.** The dock renders the existing composer with narrower padding.
**Rejected:** a `DockComposer` specialised for the panel.
**Why:** the composer contains `@` search, `/` commands, history, chips, auto-sizing and stop. A second
one diverges within a sprint. The variant changes padding and where the model control sits, and
nothing else.

### D7 · Sessions persist in Lakebase, with memory as a declared fallback

**Chosen.** Migration `002` in the existing runner, `PgEventStore`, degrade to memory when the DSN is
absent or broken.
**Rejected:** a separate database for conversations; or no persistence at all.
**Why:** one database, one DSN, one migration runner, consistent degradation with [005](../005-llm-models/12-operations-runbook.md).
A deployed app restarts on redeploy, so "no persistence" means "every deploy ends every conversation".

### D8 · The model control moves into the composer

**Chosen.** The picker is reachable from the composer at every width; the top bar keeps it above 1100 px.
**Rejected:** keeping only the top bar and removing the hiding rule.
**Why:** above 1100 px the bar has room; below it, the bar is already crowded with search, three
toggles, theme and layout. The composer always has room for one secondary control, and it is where
the user is when the choice matters.

### D9 · The files list is added, last

**Chosen.** Tree **and** list, four columns, after everything else.
**Rejected:** replacing the tree; or skipping the list.
**Why:** Databricks users expect both [observed], and the list answers a different question. It is
sequenced last because it is parity, not advantage ([08 PO](08-lenses.md#1-product-owner)).

### D10 · `⌘J` rather than `⌘.` or `⌘⇧A`

**Chosen.** `⌘J` toggles the assistant.
**Rejected:** `⌘.` (often "cancel"), `⌘⇧A` (used by the composer's attach), `⌘U` (browser source).
**Why:** `⌘J` is free in the app, unused by browsers on macOS, and is the toggle key for a panel in
several editors. It is listed in the shortcut sheet, so it is learnable.

---

## Corrections the implementation forced

Three claims in the first draft of this spec were wrong. They were found by building it and are
recorded because a specification that quietly changes is worse than one that is visibly amended.

### C1 · Three columns do not fit at 1180 px

**The claim.** [03](03-architecture.md#the-geometry-a-third-zone-one-function) said all three side
zones take a column in `wide` (≥1180), and that only below 1180 does the dock become an overlay.

**What the arithmetic says.** 276 + 340 + 380 + 480 (`CENTRE_MIN`) = **1476 px**. At 1180 the centre
would be 204 px. The tests that were written from the spec failed for exactly this reason, which is
what tests written *before* the implementation are for.

**The correction.** The dock keeps its column and the **inspector yields** below 1476 px, because the
conversation outranks the facts. `ASSISTANT_COLUMN_MIN` in
[`layout.ts`](../../apps/coding-agent/web/src/domain/layout.ts) is derived from the four constants
rather than guessed, and `takesColumn()` applies it to every clamp — so no combination of drags can
produce a starved centre.

**What it changes for a reader.** "Three columns" in this spec means *rail + centre + dock*. The
inspector is a column only when a fourth fits.

### C2 · One conversation, one surface

**The claim.** [04](04-assistant-dock.md) kept the Chat tab in the centre *and* added the dock, and
the mock-ups in [06](06-ux-wireframes.md) drew a `Chat` tab beside the documents.

**What the screenshot showed.** The same conversation rendered twice, in two panes, 300 px apart. The
first pass also kept the centre's composer while the dock had one, so there were two message boxes for
one conversation.

**The correction.** The centre is the **work** (an open document, or the home screen); the dock is the
**conversation**. The `Chat` tab is gone from `DocTabs`. The centre keeps a composer *only when the
assistant is hidden*, so hiding a panel never removes the only way to type.

**Why this is the right resolution and not a compromise.** Genie Code works this way: the notebook
occupies the editor, the conversation occupies the dock. Two renderings of one conversation is not
"more accessible", it is two places to look for the same thing.

### C3 · The dock's drawer must not have a scrim

**The claim.** [04 §rules](04-assistant-dock.md#rules-that-are-easy-to-get-wrong) treated the
assistant's drawer like the rail's and the inspector's: an overlay with a scrim behind it.

**What the e2e found.** At 1024 px the scrim covered the centre composer's model control. Clicking
the model at that width hit the scrim, so the picker never opened — a control that was visible, and
unclickable. Scene 7 caught it; it is the single best argument in this spec for an e2e that clicks
rather than asserts.

**The correction.** Only the rail and the inspector take a scrim. The assistant is the surface being
used, so the document behind it stays undimmed; a soft shadow marks the edge instead.

---

## Risks

Ordered by expected damage, not likelihood.

### R-1 · Three columns are too tight at 1180 px — **high**

**The risk.** At exactly 1180 px: rail 276 + dock 380 + centre 524. 524 px is a narrow code column, and
the dock would be showing a conversation in a strip. If it feels wrong, the `mid` breakpoint is in the
wrong place and the dock should overlay from, say, 1280 px.

**Mitigation.** The breakpoint is a single number in `layout.ts`. [P2](09-implementation-plan.md#p2-the-dock-as-a-grid-column-m)
measures the real width at 1180 and 1280 before the CSS lands, and [12](12-e2e-plan.md) records
screenshots at both.

**Sign it went wrong:** a screenshot at 1180 where the code column is narrower than the dock.

### R-2 · The dock and the transcript diverge — **high**

**The risk.** Two renderers of one state drift: one shows a tool call, the other does not; one honours
`MAX_ANSWER`, the other does not.

**Mitigation.** Both render the same `TurnView` component. No second renderer is written. A vitest case
asserts that the dock renders `TurnView` and not a bespoke transcript.

**Sign it went wrong:** a bug fixed in one surface and not the other.

### R-3 · Persistence arrives with its own operational surface — **medium**

**The risk.** A DSN, a migration, a retention job and a degradation path are four new things that can
fail in production, for a feature (history survives a restart) that no user has asked for by name.

**Mitigation.** The fallback is the current behaviour (memory), the migration reuses 005's runner, and
retention is a single statement. If Lakebase is not available in the target workspace, P6 ships
disabled and everything else still works.

**Sign it went wrong:** an app that will not boot because a database for a different feature is down.

### R-4 · Two app instances break live fan-out — **medium, accepted**

**The risk.** Subscribers live in-process. With two containers, a client connected to A does not see a
turn driven by B.

**Mitigation:** none in this spec. A Databricks App runs one container today, and a replay from the
durable log recovers anything missed on reconnect. Cross-instance fan-out needs `LISTEN/NOTIFY` or a
queue and belongs to [004](../004-crdt-collaboration/README.md).

**Sign it went wrong:** a turn that streams only half its events under load, i.e. after the app scales
out.

### R-5 · "On par or superior" is still an adjective — **medium**

**The risk.** The measurement covers five numbers and misses the thing a person actually feels.

**Mitigation.** [12](12-e2e-plan.md) pairs every number with a screenshot and a task sequence, and the
five-minute test in [08 PO](08-lenses.md#1-product-owner) is the human check. Stated as a limit: a
number is not a feeling.

**Sign it went wrong:** all numbers green, and the app still feels worse to use.

### R-6 · Focus management in three overlay/dock combinations — **medium**

**The risk.** Drawer + dock + palette + approval is a combination space where focus escapes, or a
hotkey fires in the wrong scope. The repo already had one bug of this class (two `⌘S` listeners,
[`EditorSurface.tsx:250-270`](../../apps/coding-agent/web/src/components/EditorSurface.tsx)).

**Mitigation.** One drawer mechanism, one hotkey registry, one `Esc` owner determined by the focused
element. The a11y audit runs at 1600 and 760 with the dock open.

**Sign it went wrong:** `Esc` closing two things, or focus landing on `document.body`.

### R-7 · Cell execution expectations rise — **low but real**

**The risk.** Shipping "ask about this cell" invites the expectation that a cell can be run. Removing
the run button without a word is confusing.

**Mitigation.** The cell's `ask` tooltip says what it does (`Ask about this cell`), and the dock's
suggestion for a cell is *"Fix cell N"* — a review, not an execution. The shortcut sheet does not claim
execution anywhere.

**Sign it went wrong:** a support question asking why ⏎ in a cell does not run it.

### R-8 · The files list duplicates the tree's logic — **low**

**The risk.** Two components that both list a folder, both handle errors, both open a menu.

**Mitigation.** `FilesPane` owns both views over one `list()` call and one `WorkspaceMenu`. The tree
component keeps only the recursion. FL-4 is the test that both entry points open the same menu.

---

## What would change our mind

| If we learned | We would |
|---|---|
| Users rarely keep a conversation open while reading code | Revert to a tab and delete the dock (the evidence against: the request itself is about updating a file in context) |
| The centre column at 1180 px is unusable with three zones | Move the dock's overlay breakpoint to 1280 |
| Lakebase is not available in the target workspace | Ship P6 disabled, keep memory, document it in `/api/ready` |
| The model is normally chosen once per user, not per session | Move the control to settings and leave only a read-only label in the composer |
| Cell execution lands | Restore a run affordance that calls the agent's tool path — never a local executor |

---

## What we have not verified

Stated so nobody quotes it as fact:

| Claim | Status |
|---|---|
| The dock's write volume against a real Lakebase | **not measured**; arithmetic only ([05](05-data-model-lakebase.md#write-volume-and-why-it-is-acceptable)) |
| That 320 px is the right minimum for the dock | **a design judgement**, not a study |
| That `⌘J` is the best key | **a judgement**; it is free and conventional |
| Databricks' exact chrome heights | **observed from screenshots**, not measured in their DOM |
| That removing the run button reduces confusion rather than adding it | **unverified**; R-7 is the risk |
| Two-container fan-out behaviour | **untested**; R-4 is the accepted gap |
| The five-minute user test's outcome | **not run**; it is the [08](08-lenses.md#1-product-owner) acceptance |
