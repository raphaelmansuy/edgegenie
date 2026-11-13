# Product and acceptance requirements

[Index](README.md) · [Why](00-five-whys-first-principles.md) · [Wireframes](04-ux-wireframes.md) · [Contracts](05-architecture-api.md) · [Edge cases](09-edge-cases.md) · [Test traceability](11-test-e2e-plan.md)

## Vocabulary and release scope

**SQL** is source text. A **local query draft** is an OpenGenie buffer, independent of any chat. A **SQL Query** is a native saved Databricks asset. A **run** is a durable execution attempt of one immutable input. A **result** is an expiring observation belonging to one run. A `.sql` **file** remains a workspace file even when executed using the SQL service.

R1 is the baseline: library, editor, create/save-copy, single-statement read-only execution, parameters, result preview, own history, assistant context and recovery. R2 capabilities require the [spikes and gates](12-decisions-open-questions.md); a disabled gate has actionable copy and native handoff, not a misleading Save button. This is a target specification, not shipped behavior.

## Functional acceptance

| ID | Requirement | Observable acceptance | Release |
|---|---|---|---|
| SQ-01 | Persistent SQL navigation | Queries in navigator and command palette; New SQL query on Home, library and tab menu. SQL editor restores last permitted query or shows landing. No chat session required. | R1 |
| SQ-02 | Query asset library | List accessible assets with title, owner, modified time, warehouse and native identity. Page sequentially; expose scan coverage and Load more. Distinguish empty, filtered-empty, partial, loading and denied. | R1 |
| SQ-03 | Honest search and filters | Search title/description and filter owner/modified/OpenGenie favorites over currently cached scanned metadata only. Show retained-window scope separately from total scanned count; no global sort/completeness claim when pages are unseen or evicted. Cancel stale requests. Favorites are explicitly app-specific. | R1 |
| SQ-04 | Stable identity and routes | Native UUID, numeric workspace object ID, path and statement ID remain distinct. Query links/tabs/recents deduplicate by workspace and asset ID; rename does not create a new tab. Unknown cross-workspace links never auto-connect. | R1 |
| SQ-05 | SQL authoring | Reuse EditorHost, app themes, undo/redo, keyboard escape, syntax and schema-backed completion. Preserve draft/caret/dirty state across tabs. Truncated/unsupported assets cannot be overwritten. | R1 |
| SQ-06 | Durable drafts and explicit persistence | Local edits recover after reload when recovery storage is available. Save copy/create explicitly names destination and resulting native asset. Opening/editing/running never writes remotely. Clear cache failure notice and downloadable SQL fallback. | R1 |
| SQ-07 | Safe native persistence | Create and save-copy preserve supported text/context and verify the returned native ID via GET. Existing asset update is disabled unless draft/publish semantics and conflict guard are established. No delete/import overwrite. | R1 create/copy; R2 update |
| SQ-08 | Execution context | Display selected warehouse, catalog/schema and viewer identity before Run. A saved warehouse preference does not silently fall back if denied/missing. A new draft may propose a running warehouse; user sees the choice. | R1 |
| SQ-09 | Deterministic run scope | Run selection if nonblank; otherwise require the buffer to contain exactly one supported statement. Button label says Run selection or Run query. Multiple selections, incomplete fragments and scripts produce clear validation. No implicit split or Run all. | R1 |
| SQ-10 | Typed parameters | Recognize markers outside strings/comments; bind STRING, integer, DECIMAL, DATE, TIMESTAMP and explicit NULL. Missing values block submit. Do not interpolate strings or persist sensitive bindings by default. Legacy/unsupported widgets prompt native handoff or explicit conversion into a copy. | R1 |
| SQ-11 | Server-owned execution | Submit asynchronously, persist operation and statement handle, poll boundedly, recover after browser reload. A run pins source/context/parameters/identity; no success without upstream evidence. | R1 |
| SQ-12 | Execution and authorization safety | Enforce shared read-only grammar allow-list, saved-asset CAN RUN, warehouse CAN USE, user scopes and UC. Reject unknown constructs; never elevate identity. SQL mutations remain disabled in R1 even if the tool server permits writes. | R1 |
| SQ-13 | Cancel semantics | Cancel marks requested, then reconciles final outcome. A concurrent success remains success. Closing a tab or losing connection never claims cancellation; stop scope names the selected run. | R1 |
| SQ-14 | Lossless bounded results | Show schema, NULL versus empty, exact integer/decimal strings, duplicate column labels by ordinal, counts and truncation. Distinguish success with no rows from result expiry. Keyboard-accessible result table; bounded memory and DOM. | R1 |
| SQ-15 | Provenance and stale output | Run details display source snapshot/hash, saved versus local revision, warehouse/context, start/end and parameter names/redacted values. Editing any pinned input marks output stale without mutating the run. | R1 |
| SQ-16 | Own run history | Recent app runs remain accessible without chat or open editor. Reopen source snapshot explicitly as a draft; never re-execute on history navigation. Native workspace history is a labeled handoff. | R1 |
| SQ-17 | Query-aware AI context | Attach a query by verified native ref or own draft snapshot/selection. Server resolves authorized content with revision/hash and excerpt labels. SQL comments, metadata and rows are untrusted data. Sending result rows is an explicit user action. | R1 |
| SQ-18 | AI-to-artifact promotion | SQL code block has Open as query; preview changes before Apply to local buffer; no automatic remote save/run. Created native assets emit typed artifact refs and refresh matching documents without overwriting dirty buffers. | R1 |
| SQ-19 | Native interoperability | Copy OpenGenie link and Open in Databricks use verified workspace host and documented native UUID handoff. Tree/file entries with uncertain identity remain files/unsupported assets. Shared links convey no access grant. | R1 |
| SQ-20 | Error/recovery model | Distinguish scope configuration, expired identity, ACL/UC denial, missing asset, validation, conflict, rate limit, expired output, storage failure and uncertain remote outcome. Preserve draft; retry only operations known safe. | R1 |
| SQ-21 | Accessible responsive UI | Keyboard-only core journey, focus restoration, named controls, live status without polling spam, light/dark/forced-color legibility; no page-wide overflow at 320px or 200% zoom. Query content uses current panel resolver. | R1 |
| SQ-22 | Resource bounds and privacy | Apply payload/page/concurrency/result/retention budgets from [data](06-data-persistence.md) and [complexity](08-lenses-complexity.md). No tokens/SQL/bindings/results/presigned URLs in routine telemetry. Owner-scoped caches and run reads. | R1 |
| SQ-23 | Persistence conflict and dependency protection | Never represent pre-read/PATCH as atomic compare-and-swap. Preserve unknown metadata. In-place update/publish requires verified protocol, dependency impact review and concurrent native-editor tests; otherwise Save copy. | R2 gated |
| SQ-24 | Extensible parity without false promises | Multi-statement, mutations, collaboration, charts, export, native widget edits, ACL writes, Git and schedules remain explicit future capabilities. Native handoffs work today; capability flags are returned by the server. | R1/R2 |

## Non-functional targets

Targets are OpenGenie budgets, not observed performance: editor interactive within 1s of source delivery for a 200KiB document on the agreed reference laptop; typing-to-paint p95 under 50ms; metadata page render p95 under 200ms after response for 50 items; no more than 200 rendered rows and 50 rendered columns at once. Timings exclude warehouse startup and upstream query execution. [The complexity lens](08-lenses-complexity.md) defines benchmark workload and hard safety bounds.

Telemetry must distinguish time awaiting warehouse from app/network latency. Automated release evidence includes the [E2E scenarios](11-test-e2e-plan.md), security contract tests and state-machine transitions; a happy-path screenshot alone cannot satisfy an SQ requirement.
