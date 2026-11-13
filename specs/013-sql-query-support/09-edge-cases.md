# Edge cases, controls and test coverage

[Index](README.md) · [Requirements](03-requirements.md) · [State charts](07-sequences-statecharts.md) · [E2E scenarios](11-test-e2e-plan.md) · [Residual risks](12-decisions-open-questions.md)

This is the envisioned failure inventory, not a proof that every possible platform failure is known. New incidents add an EC row, a control and a regression. Severity: H risks unauthorized access, incorrect execution, data loss or false evidence; M degrades usability/availability. Every test ID below is defined in the [test plan](11-test-e2e-plan.md).

## Discovery, identity and drafts

| ID | Case | Mitigation and expected observation | Severity | Test |
|---|---|---|---|---|
| EC-01 | No assets versus zero matches | Different empty copy; show active filters and scan coverage; Load more/Clear filters. | M | T01 |
| EC-02 | Only first page loaded | Explicit partial flag; page token followed only by demand; no global absence claim. | M | T01, T17 |
| EC-03 | Page token invalid/expired/repeated | Detect loops; bounded restart with new generation; preserve filters, mark coverage reset. | M | T01 |
| EC-04 | Duplicate, renamed or moved query | Dedup by workspace/native ID, update label, retain tab; paths are metadata. | M | T02 |
| EC-05 | Same title/UUID string from another workspace | Workspace-scoped identity; mismatched ref rejected; no credential switching. | H | T02, T10 |
| EC-06 | Search response arrives out of order | Abort/generation guard; older result cannot replace new scope. | M | T01, T17 |
| EC-07 | Favorite or recent points to inaccessible/deleted query | Revalidate on open, clear inaccessible cache, preserve only policy-approved preference tombstone. | H | T01, T10 |
| EC-08 | Numeric editor ID, `.sql`, `.dbquery.ipynb`, unknown workspace kind | No identity guessing/conversion; explicit unsupported/native handoff. Ordinary SQL file retains file save behavior. | H | T02, T14, T18 |
| EC-09 | Empty/comment-only/whitespace SQL | Refuse before operation dispatch; actionable editor message. | M | T05 |
| EC-10 | Oversized or partially loaded source | Size/truncation flags, read-only or explicit excerpt copy; no overwrite of unseen tail. | H | T03, T12 |
| EC-11 | Tab switch, close, browser reload with dirty buffer | Document-owned recovery, dirty-close decision, no implicit execute or native write. | H | T03, T09 |
| EC-12 | Storage quota/private browsing/encryption unavailable | Clear “recovery unavailable”; offer SQL download; no false durable run acknowledgement. | H | T03, T09 |
| EC-13 | Two tabs edit same app draft | Revision CAS + conflict UI/separate recovered draft; never silent last-write-wins. | H | T03, T15 |
| EC-14 | Source changed externally while local dirty | Mark conflict and preserve local text; explicit reload/merge/copy; no forced replacement. | H | T04, T15 |
| EC-15 | Native create succeeds but GET verification fails | Keep created_unverified with known ID; reconcile GET; do not create again. | H | T04, T07 |
| EC-16 | Native create response lost/title collides | Unknown-create state and operation status; no title-only inference or blind retry; returned resolved name displayed. | H | T04, T07 |

## Dispatch, cancellation and authorization

| ID | Case | Mitigation and expected observation | Severity | Test |
|---|---|---|---|---|
| EC-17 | Double click/keyboard repeat/same key | Transactional unique reservation; one upstream POST; same response handle. | H | T07 |
| EC-18 | Same key, different SQL/context/bindings | Hash mismatch →409 before remote request. | H | T07 |
| EC-19 | Crash/lost response after remote acceptance | SubmissionUnknown; durable pre-dispatch intent; never replay the same operation. | H | T07, T09 |
| EC-20 | Store fails before or after dispatch | Before: no submit. After: uncertain status incident, preserve buffer/operation, no auto-resubmit. | H | T07, T09 |
| EC-21 | Cancel races with success or failure | CancelRequested then authoritative terminal state; retain cancel intent/time separately. | H | T08 |
| EC-22 | Cancel ACK lost or user closes page during cancel | Reconcile known ID; tab closure does not mean canceled. Repeat cancel only under verified idempotent adapter contract. | H | T08, T09 |
| EC-23 | Old poll arrives after newer terminal response | Observation CAS/terminal monotonicity; success never regresses to running. | H | T06, T15 |
| EC-24 | Warehouse stopped/starting/queueing/unavailable | Display waiting context; never switch warehouses silently; selection and native permission govern startup. | M | T06, T10 |
| EC-25 | No warehouse or stored warehouse denied/deleted | Run disabled with choose/contact-owner action; no service-principal or “first available” fallback. | H | T10 |
| EC-26 | Token expires/missing required OAuth scope | Separate sign-in versus app configuration action; pause polling; no elevation. | H | T09, T10 |
| EC-27 | Query CAN VIEW but cannot run/edit/manage | Server verifies each ability; read does not imply run or in-place save. Copy-origin provenance retains access constraints. | H | T10 |
| EC-28 | UC denial, row filters, masks, grants change | Surface platform denial; fetch new data only as current user; stop retries; never switch identity. Already-delivered rows are not retroactively revocable. | H | T10, T11 |
| EC-29 | Another user guesses run/draft/operation/chunk ID | Own principal/workspace lookup required before any upstream request; uniform unavailable response. | H | T10 |
| EC-30 | 429/Retry-After, 5xx or prolonged network partition | Bound safe-read retries/backoff; preserve state; never POST replay after possible dispatch. | M | T06, T07, T12 |
| EC-31 | Browser/server disconnect or worker ownership loss | Known-handle reconcile only; require renewed same-user auth; owner-fenced dispatch. | H | T09, T15 |
| EC-32 | Fifteen-minute app deadline without usable token | Record cancel intent; request cancellation only when authorized; show native handoff and unknown status. | H | T08, T09 |
| EC-33 | Unrecognized engine status or HTTP200 FAILED | Typed protocol/outcome mapping, raw status retained safely, never green success from HTTP alone. | H | T06 |

## SQL, parameters and persistence semantics

| ID | Case | Mitigation and expected observation | Severity | Test |
|---|---|---|---|---|
| EC-34 | Semicolons in literals/comments; trailing semicolon | Dialect-aware single-statement parse, not split(';'). Accept one terminated statement. | H | T05 |
| EC-35 | WITH-write, commented leading keywords, scripting, dynamic SQL | Parse full AST and allow-list; unknown or mutating constructs refused. | H | T05 |
| EC-36 | SELECT invokes UDF/external function | Conservative builtin function policy; unverified functions/native features hand off. Do not claim grammar alone prevents external side effects. | H | T05, T18 |
| EC-37 | Incomplete selection/multiple cursors/UTF-16 surrogate split | Snapshot range/hash validated server-side; reject invalid fragment/range; run scope visible. | H | T05 |
| EC-38 | Missing/repeated/extra marker or marker in string/comment | Parse parameter markers, dedup required names, validate exact binding set; no string replacement. | H | T05 |
| EC-39 | Decimal precision, NULL, timezone/DST, invalid date or integer | Typed string values; explicit timezone for timestamp input; reject invalid casts/ranges before dispatch when knowable. | H | T05, T11 |
| EC-40 | Identifier injection, SQL metacharacters in values | Values bound by API; dynamic identifiers unsupported until separately validated. Metadata IDs/paths are never concatenated into SQL. | H | T05, T10 |
| EC-41 | Legacy `{{}}`, positional `?`, complex or dynamic widget | Preserve source; do not silently convert; supported copy conversion reviewed or native handoff; no metadata round-trip claim. | H | T05, T18 |
| EC-42 | Native PATCH affects schedules/alerts/shared draft unexpectedly | In-place update and publish gate closed; require SP-2 evidence plus explicit impact review. Save copy available. | H | T04, T18 |
| EC-43 | Unknown native metadata/version fields | Mask only verified supported fields; preserve unknowns; no whole-object rewrite. | H | T04, T18 |
| EC-44 | Local native-update pre-read races external editor | Do not call pre-read/PATCH CAS; without verified guard, no in-place update. | H | T15, T18 |
| EC-45 | Save while user keeps editing or permission changes | Save exact captured revision; later edits remain dirty; reauthorize target at action time. | H | T04, T10 |
| EC-46 | Save copy destination unavailable, duplicate resolved title, inherited ACL | Show actual native name/ref and destination; disclose new asset permissions; retain draft on failure. | H | T04, T10 |

## Results, AI, resource bounds and UI

| ID | Case | Mitigation and expected observation | Severity | Test |
|---|---|---|---|---|
| EC-47 | Successful empty SELECT or command without rows | Distinct no-rows success; do not infer failure or table cardinality. | M | T11 |
| EC-48 | NULL, empty, literal null, duplicate labels, large numbers | Ordinal column arrays; raw string-or-null values; precision preserved. | H | T11 |
| EC-49 | Partial chunk, bad width, missing schema, truncated data | Validate manifest/rows; expose truncation and protocol errors; no silent missing tail. | H | T11, T12 |
| EC-50 | Huge/wide/binary/complex values or malformed Unicode | Decode/display caps, column paging, escaped text, full-value dialog only within byte limit; native handoff. | M | T11, T12, T17 |
| EC-51 | Result expires/CLOSED or chunk fetch fails | Execution remains succeeded; availability separately expired/error; rerun requires new action/key. | H | T11, T12 |
| EC-52 | Query/warehouse/parameters changed after prior run | Compare immutable input hashes/context; show stale result and snapshot; never silently reuse output. | H | T06, T11 |
| EC-53 | Sort/filter only loaded rows | Label loaded-preview scope; do not imply whole-result transformations or silently rerun SQL. | M | T11 |
| EC-54 | Query/comment/metadata/result prompt injection | Fence as data, server-authorized reference resolution, instruction hierarchy; adversarial AI transcript fixtures. | H | T13 |
| EC-55 | AI applies to stale or different document | Bind patch to document/ref/hash; preview, explicit apply and conflict on changed base; no remote save/run. | H | T13, T15 |
| EC-56 | Result/parameter secrets accidentally sent to model/logs | Explicit row selection, redaction/context caps, no default sensitive bindings, content-free telemetry. | H | T10, T13 |
| EC-57 | Replayed/truncated tool summary or missing query artifact ID | Typed verified artifact event; do not infer ID/path from prose; report created-elsewhere without replacing dirty work. | H | T13 |
| EC-58 | Multiple viewers poll same run; rapid tab churn | Coalesce by run/principal; cancel stale reads; enforce poll/global active budgets. | M | T09, T15, T17 |
| EC-59 | 10k assets or expensive nested SQL freezes UI | Demand paging, bounded scan/cache, parser timeout/depth budget; no all-text/ACL fanout. | M | T17 |
| EC-60 | Small screen, zoom, forced colors or reduced motion | Existing shell resolver; own scrolling region; semantic state labels and measured contrast. | M | T16 |
| EC-61 | Focus lost after dialog/tab/result completion | Restore initiating focus/stable toolbar; no result-driven focus steal; keyboard grid/page access. | M | T03, T16 |
| EC-62 | Clipboard denied, spreadsheet formula text or download disabled | Copy errors surfaced; no execution of values; export deferred until authorization/escaping policy. Loaded-row copy is explicit. | M | T11, T16, T18 |
| EC-63 | Feature disabled or rollback while runs active | Stop new dispatch, retain history/reconcile/cancel; no dropping tables or deleting native Queries. | H | T18 |
| EC-64 | Tool writes disabled / UI tool-policy disagreement | One query service gate plus MCP write flag; known refusal surfaced once; no alternate path retries. | H | T10, T13, T18 |

The highest-risk cross-cutting invariants are [P3–P6](00-five-whys-first-principles.md): permissions are conjunctive, actions remain separate, unknown outcomes stay unknown, and coverage/bounds remain visible. Release gates cover every H row; performance/visual targets remain measurable rather than assumed.
