# Seven design lenses and bounded complexity

[Index](README.md) · [Requirements](03-requirements.md) · [Architecture](05-architecture-api.md) · [Data](06-data-persistence.md) · [Edge cases](09-edge-cases.md) · [Plan](10-implementation-plan.md)

These are seven reviews of one design, synthesized for this specification. They are not claims that seven independent agents reviewed the implementation.

## Product Owner

The deliverable is a reusable SQL asset and reproducible execution evidence. Optimize the complete find → edit → run → save copy → reopen journey. A successful conversational SQL answer without an openable artifact is insufficient. Saved Queries and own run history need different names and navigation. Measure completion and recovery, not total tool calls. Native save/publish parity is a separate capability; explain the baseline honestly and do not block useful create/copy/run support on full native-editor replication. Own SQ-01–SQ-04, SQ-06–SQ-07 and SQ-24; review T01–T04/T18.

## Full Stack Developer

Extend the discriminated document/route/context/event types together. Exhaustive TypeScript switches and backend attachment validation must fail at build/test time when query cases are forgotten. Add small query components/services behind existing editor and shell seams. Keep dirty buffer/recovery in a document owner, not a tab's transient render. A backend operation ID, not a fetch promise, owns a run. Use injected repositories and typed outcomes; stage notebook migration behind parity tests. Own SQ-04–SQ-07, SQ-11, SQ-13, SQ-20; review T02–T09/T14/T15.

## Database Expert

Asset, draft, snapshot and attempt have different grains. Never join history to a mutable current query and call it executed SQL. Use principal/workspace prefixes on access and indexes; prefer keyset pagination with stable ordering. Maintain exact SQL values and NULL. App idempotency cannot guarantee external exactly-once execution. Data permissions remain in UC; a saved Query ACL is an additional boundary. Native draft/publish semantics and conditional writes must be verified before existing asset mutation. Own SQ-07–SQ-16/SQ-22–SQ-23; review T04–T12/T15.

## UX and UI Designer

Keep Queries and SQL Editor discoverable within one shell; users should not need to begin a chat to run a query. The visible Run label must describe its scope. Separate unsaved, running, cancel requested, unknown, failed, stale and expired output. Keep the warehouse and identity visible before execution. A spinner cannot communicate an unknown outcome. Use current app typography, icons, spacing and semantic tokens; pastel fills belong to documentation diagrams and soft surfaces with dark text. Preserve focus and reading position on completion. Own SQ-01–SQ-03, SQ-05, SQ-13–SQ-16, SQ-20–SQ-21; review all wireframes/T16.

## AI Engineer

Attach explicit query refs and revision-pinned selections, not arbitrary serialized browser descriptions. Resolve native content using the current user's token; represent denied/truncated context. Generated SQL is a proposal: Open as query → inspect diff → Apply locally → explicit Run. When the model suggests a table query, obtain actual schema first and state grain before aggregation; semantic correctness also needs join cardinality, NULL, timezone, duplicate and aggregation checks. Do not infer tables/columns from a title or truncated result. Treat comments, descriptions, errors and result cells as untrusted data. Include result rows only by deliberate selection, cap context and redact sensitive bindings. Different tool routes must not escape shared access policy. Own SQ-10/SQ-12/SQ-15/SQ-17–SQ-18; review T05/T10/T13.

## System Design Expert

Separate durable intent, remote dispatch and observed execution state. Reserve before dispatch; record the handle before returning recoverability. Design ambiguous creates/submits and cancel races before the happy path. R1 uses one active server owner, matching inspected deployment patterns; it does not promise transparent multiworker execution failover. A worker may resume polling known handles after reauthorization, but never replay uncertain dispatch. Capability flags degrade at operation granularity; a missing create permission should not break local authoring. Instrument only IDs/state/timing/error category. Own SQ-11–SQ-13/SQ-20/SQ-22–SQ-24; review T06–T10/T15/T18.

## O(n) and resource expert

Let `N` be all visible remote assets, `K` scanned/cached summaries (K ≤1,000), `P` requested page size (P ≤50), `L` SQL bytes (L ≤200KiB in baseline), `R` preview rows (R ≤1,000), `C` schema columns, `V` rendered rows (V ≤200), `W` rendered columns (W ≤50), and `A` active run observations. Name every bound; big-O alone does not prevent a 4MiB parse or a warehouse-wide scan from being expensive.

| Operation | Algorithm/cost | Required protection |
|---|---|---|
| Library initial page | One upstream page; O(P) normalize, memory O(P) | No per-row GET/query-text retrieval/ACL fan-out. Metadata includes unknown permission until open if not provided. |
| Full accessible inventory | O(N/P) sequential requests and O(N) normalization overall | Never on initial render or each search key; explicit scan action, cancellation, coverage and eviction. |
| Local library search/filter | O(K) over normalized metadata after 250ms debounce | Abort previous generation; avoid O(K²) nested duplicate checks. Use Map keyed by identity. |
| Tab/recent/artifact lookup | Expected O(1) identity Map; O(number of tabs) ordered display | No full transcript scan per keystroke; incrementally merge typed artifact events. |
| SQL parsing/binding | Target O(L) lexical scan plus bounded dialect parser | Cache by source hash; authoritative validation on Run. Reject deeply nested/pathological input within a 250ms server parser budget using an isolated worker/process if necessary. Do not assume a third-party parser has linear worst-case behavior. |
| Parameter matching | O(L + B), B ≤100 bindings | Build name Map; string/comment-aware tokenizer; no recursive regex backtracking. |
| Result decode | O(returned bytes + R×C), bounded by transport and decoded-byte caps | No all-result materialization beyond cap; retain row arrays rather than keyed objects that lose duplicate labels. |
| Result paint | O(V×W), bounded window/page | Accessible paging or virtualization; fetch only requested chunks; stable keys by ordinal. |
| Run history | Indexed O(log M + P) retrieval for M own retained attempts | Keyset ordering; no OFFSET scan or payload column in list query. |
| Polling | O(A) per cadence, bounded concurrency | Coalesce observers of same run; terminal states stop; hidden views slow/detach; no busy loops. |

## Numeric budgets

All are proposed app limits, not Databricks guarantees. Server validates regardless of client settings.

| Resource | Baseline budget |
|---|---|
| Source/payload | SQL text 200KiB UTF-8; run request 256KiB; 100 parameters, at most 16KiB/value within request cap; deeply nested parse rejected by time/depth budget. |
| Listing | Native requests ≤50 assets/page, one list request at a time per principal/workspace; scan action ≤5 pages; ≤1,000 metadata records/session cache; metadata strings capped with truncation indicators. |
| Execution | One active run per document; four per principal; 32 known active attempts per server; refuse excess before dispatch. Unknown attempts occupy a slot until resolved/explicitly acknowledged. |
| Observation | Poll 1s initially, 2–5s later with jitter; hidden view 15s or detached. At most 2 concurrent status fetches/principal and 4/server; respect Retry-After. |
| Deadline | 15min app run deadline proposes cancel while user authorization is live; token absence records pending cancel intent and native handoff. Never claim automatic cancellation happened without confirmation. |
| Result | Default/hard R1 row limit 1,000; requested byte limit 4MiB; decoded response cap 8MiB; no unbounded external download; at most two resident chunks/view and 24MiB cached rows/principal, 48MiB/server. |
| Wide schemas | Display up to 50 columns at once with column paging; over 200 columns uses bounded schema summary and native handoff for complete browsing. Never claim omitted columns are absent. |
| Rendering | ≤200 rows ×50 columns, 10,000 cells in DOM; fixed viewport; copy action names loaded/selected extent. |
| Recovery/context | Browser recovery ≤5MiB; reuse current attachment count/character limits; never auto-attach all result rows. |

Result row/byte limits constrain output, **not** bytes scanned, warehouse startup, UDF side effects or query cost. Restricting baseline SQL and rejecting unknown external functions reduces risk, but warehouse policies and user review still govern analytical cost.

## Benchmarks to make the lens enforceable

T17 uses 10,000 generated remote summaries in a fake paged source, a 200KiB SQL document, 100 bindings, a 1,000×200 result under byte cap, and oversized/pathological variants. Assert initial call count is one page, memory remains bounded during scan/eviction, source hashing is once per captured revision, stale search cannot win, DOM remains under 10,000 result cells, and detached observers stop polling. Measure frontend p95 timings over 30 warm interactions on a recorded laptop/browser; retain raw timings and hardware info. These targets are unmeasured until implemented.
