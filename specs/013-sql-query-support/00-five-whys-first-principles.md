# Five whys and first principles

[Index](README.md) · [Evidence](01-databricks-assessment.md) · [Requirements](03-requirements.md) · [Decisions](12-decisions-open-questions.md)

## Five whys

| Why | Underlying need | Design consequence |
|---|---|---|
| Why make SQL prominent? | Analysts and engineers repeatedly work with SQL as their deliverable. | Add a persistent Queries entry and New SQL query action. |
| Why not rely on SQL in messages? | Chat turns do not provide a stable editable asset with a lifecycle. | Promote a proposed SQL block into an explicit local query draft. |
| Why not represent every query as a `.sql` file? | Saved Query permissions, identifiers, metadata, and downstream dependencies differ from file content. | Use a discriminated query document and native Query adapter. |
| Why separate a saved Query from execution? | One asset can run many times with different revisions, parameters, identities, and warehouses. | Persist run provenance independently; never label old output as current. |
| Why reuse domain services? | UI and AI can otherwise disagree about safety, result limits, or success. | Share policy and execution services behind narrow ports. |

## First principles

**P1 Identity precedes presentation.** Model local draft ID, native Query UUID, workspace object ID/path, and statement ID separately. Titles are mutable labels. Cross-workspace keys include workspace identity. Never infer a Query UUID from digits in a browser URL.

**P2 Input and observation are different objects.** Editing SQL cannot change an existing run. A run pins exact executable text and a hash, typed parameter bindings, execution context, initiator, and timestamps. An unsaved run is legitimate and visibly identified.

**P3 Permissions are conjunctive.** An operation must pass app policy, user authorization scopes, asset ACLs where applicable, warehouse permissions, and Unity Catalog checks. A run of a saved asset must not bypass its execution permission by fetching text and issuing arbitrary SQL. Approval cannot grant an absent platform permission.

**P4 Side effects need their own boundary.** Saving Query metadata does not execute SQL. Running does not save. Saving a copy does not update an existing asset or publish its downstream definition. Read-only SQL is established by a dialect-aware parser and allow-list; keyword regexes are not proof.

**P5 Remote uncertainty is state.** A lost submission response may mean execution started. A cancel acknowledgement means the request was received. Neither means a known terminal result. Preserve `submission_unknown`, `cancel_requested`, and `reconciling` states instead of guessing or automatically resubmitting.

**P6 Every bound is visible.** Listing may cover only scanned pages; rows may be truncated; results may expire; context may contain only an excerpt. Show the extent and recovery action. A preview limit is not a cost limit on a warehouse scan.

**P7 Duplication of behavior is a defect multiplier.** Reuse the editor host, document tabs, shell panels, context validation, error mapping, and durable-store patterns. Extract a shared execution service rather than copying notebook execution into a second router.

## Product boundaries

The baseline is a useful complete journey: find a Query or create a local draft; edit and inspect SQL; validate/bind parameters; run one allowed statement as the viewer; inspect a bounded result; cancel or reconnect; create a saved Query or save a copy; reopen it; ask the assistant about it.

Existing remote Queries remain runnable when platform permissions allow. Edits are local until explicit Save copy. In-place update is a separate capability gated on native saved/draft semantics and conflict protection. A generic REST PATCH plus a pre-read does not provide atomic conflict prevention.

Beyond baseline: multi-statement batches, transactional/session scripts, SQL mutations, collaborative editing, native shared result synchronization, charts, schedules, alerts, Git integration, ACL changes, ownership transfer, native favorites synchronization, and large exports. Keep native handoffs for these; do not present inert controls. [Requirements](03-requirements.md) specify exact scope and [the plan](10-implementation-plan.md) orders extensions.

## Success signals

Measure, with content-free telemetry: library-to-editor opens; draft-to-first-run completion; create-and-reopen success; surfaced permission failures by category; unknown submission count; duplicate submit count; run recovery after reload; successful keyboard-only journeys. Baseline release requires zero unauthorized platform calls and zero automatic execution retries after an ambiguous submit in fault-injection tests. Product conversion targets should be set after collecting a privacy-safe baseline, not invented here.
