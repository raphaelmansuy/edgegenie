# Decisions, compatibility spikes and residual risks

[Index](README.md) · [Official evidence](01-databricks-assessment.md) · [Requirements](03-requirements.md) · [Architecture](05-architecture-api.md) · [Plan](10-implementation-plan.md) · [Tests](11-test-e2e-plan.md)

## Decision record

| ID | Decision | Reason and consequence |
|---|---|---|
| D1 | Separate native Query, app draft, SQL file, execution and result | Different identities, grains and permissions; typed refs/DTOs rather than filename heuristics. |
| D2 | Reuse the existing shell, tabs, editor host and assistant dock | One interaction vocabulary and fewer regression surfaces; no second SQL application shell. |
| D3 | Baseline creates/saves copies, with local recovery; no implicit native update | Native Save/draft/dependency semantics are not established by Query PATCH. Useful author/run/reopen remains possible without risking dependent assets. |
| D4 | In-place update requires verified conflict protection and explicit propagation semantics | Pre-read/PATCH races with native editors. App locks cannot lock the Databricks UI; without an authoritative guard keep update disabled. |
| D5 | Baseline one parsed read-only statement, selected range or whole buffer | Avoid hidden batch order, session/temp-object dependencies, partial commits and mutation authorization. Multistatement authoring is allowed but execution is gated. |
| D6 | Explicit viewer warehouse/context and conjunctive permissions | Never silently run as app/owner or another warehouse. Query ACL, warehouse and UC serve different boundaries. |
| D7 | Capability-gated native widget/tree/ID compatibility | Public APIs and native UI do not expose identical concepts. Preserve metadata, no numeric/UUID guessing or plain-text `.dbquery.ipynb` overwrite. |
| D8 | Own favorites/history first, labeled separately from native surfaces | No invented native favorites API; run history independent from saved Queries and chat sessions. |
| D9 | Durable operations with unknown outcome; no automatic POST replay | Exactly-once cannot span an external POST and local commit without provider support. Keep uncertainty visible and idempotency scoped. |
| D10 | Bounded INLINE results with lossless values, no large export initially | Lower operational/privacy footprint; avoids presigned-link handling and unverified download-policy parity. |
| D11 | Own private run results; no implicit native shared-result publication | Sending SQL to Statement API does not establish native editor result synchronization. Shared-result behavior is a separate feature. |
| D12 | Assistant proposals apply locally and require explicit run/save actions | Data context is untrusted; AI suggestions do not expand authorization or overwrite a newer buffer. |
| D13 | Single-active-server baseline with additive durable schema | Matches inspected store patterns; multiworker failover needs leased ownership and additional tests. Known-handle recovery does not require replay. |

## Compatibility spikes

No live compatibility spike ran. SP-6 has a pinned dialect-aware parser and local refusal corpus; other spikes retain their live evidence gates. [14](14-implementation-outcome.md) records the implementation checkpoint. Owners are implementation roles, not assignments to named people. Store sanitized evidence beside future test artifacts; never credentials or user data.

| ID / owner | Evidence to obtain | Blocking gate and fallback |
|---|---|---|
| SP-1 / Full Stack + Database | Verify whoami and warehouse, then list/create/get current-editor Query using the supported API/SDK, open returned UUID through documented native handoff, repeat with migrated asset, inspect all relevant response pages. Capture installed SDK/version and workspace behavior. | Blocks native create/support-complete claim. If unresolved, local author/run pilot with explicit limitation; no full native-support release. |
| SP-2 / Database + System Design | Determine Query API GET/PATCH relationship to native shared draft, saved definition and dependent workflows/alerts; find/test authoritative conditional revision mechanism; test competing native editor. Check what fields PATCH changes and whether its `update_mask` preserves unknowns. | Blocks existing asset update/publish. If no atomic guard or propagation contract exists, retain Save copy indefinitely. Do not demand user approval to compensate for a technically unguarded write. |
| SP-3 / Security-oriented Full Stack | Verify effective Query CAN RUN/CAN EDIT/CAN MANAGE and destination permissions lookup under user authorization; warehouse CAN USE; required OAuth scopes, including permissions APIs. Cross-check CAN VIEW-only behavior and native UUID permission resource. | Blocks executing a saved Query when effective ability cannot be established; hand off to native. Never fetch text then bypass missing asset-run permission. |
| SP-4 / UX + Full Stack | Current named widgets/defaults versus Query API parameter metadata, legacy syntax, dynamic dropdown dependency IDs and preservation of unsupported fields. | Blocks native widget round-trip edits. Baseline execution bindings are app run overrides; do not claim defaults synchronize into native widgets. |
| SP-5 / Full Stack | Determine authoritative workspace tree path/resource-ID/native UUID correspondence, including Git-backed `.dbquery.ipynb` and moved/renamed queries. | Blocks native query tree integration and Git import/export; use Query library identity. No guessed SQL_QUERY enum or numeric conversion. |
| SP-6 / AI + O(n) expert | Select dialect-aware SQL parser compatible with Databricks constructs; validate nested/Unicode/selection/CTE/compound syntax and builtin/UDF policy. Measure parse limits and timeout handling. | Blocks SQL execution release until fail-closed corpus passes. Syntax highlighting is not a policy parser; unknown syntax stays unsupported. |
| SP-7 / System Design + QA | Validate status/chunk ownership/expiry/cancel contracts, user-token renewal after restart, deployment durability/encryption and active owner fencing. Confirm request/response bounds and native download policy before any export. | Blocks durable execution/recovery claims; known-handle status may require user reconnection. Export remains off. |

## Residual risks and open product questions

| Risk/question | Current handling | Trigger for revisiting |
|---|---|---|
| Saved Query discovery API may not cover every new-editor asset flavor | SP-1 plus honest coverage and unsupported-native handoff | Native fixture fails list/get/reopen |
| Native update has no documented CAS or public draft API | Save copy baseline; never claim atomic updates | Verified official API or provider protocol becomes available |
| Select statements can be expensive or invoke external/UDF behavior | Conservative grammar/builtin policy; explicit warehouse and result bounds; no promise of cost caps | Broader SQL coverage requested |
| A token can expire while a run continues remotely | Pause observation/cancel intent, reconnect as same user, native status handoff | Long-running workload adoption |
| A submit/create can be accepted without a durable handle | Unknown state and no replay; support evidence from operation correlation | Need provider idempotency or stronger reconciliation |
| Users expect native autosave/collaboration behavior | Clear Local changes/Save copy copy; no publish/share parity promise | R2 collaborative product scope approved |
| Search on scanned metadata misses remote unseen assets | Persistent coverage, Load more, bounded scan and native handoff | Usage shows workspace-scale indexing demand |
| Previously displayed bytes survive subsequent access revocation | Clear caches and deny further retrieval; document that delivered data cannot be recalled | Stricter compliance policy requires no client caching |
| Export parity and spreadsheet formula injection | No baseline export; explicit loaded-row copy only; future export requires policy/escaping contract | Large download feature requested |
| Private SQL may remain in recovery storage on shared devices | Per-principal partition, retention, sign-out clearing and opt-out | Organization storage policy differs |

Open prioritization questions do not block this specification: whether native ACL editing/scheduling or charts are next; whether local favorites should later sync; whether multistatement SQL should use a verified single-session scripting API or a separate job workflow. Do not choose a naive split-and-submit loop: independent statement requests must not be assumed to share temporary objects, variables, transaction context or cancellation semantics. Any future design needs per-statement outcomes, stop-on-error policy, partial-commit disclosure and state charts.

## Approval boundary

The original task authorized repository specification files. The subsequent user instruction explicitly authorized implementation, end-to-end tests and retained screenshots. Repository implementation and isolated synthetic SQL tests are within that scope. No live workspace qualification, permission change, native asset creation or publication was performed. Future live work must follow workspace identity and authorization rules; no approval can override UC or absent query/warehouse access. Product capability gates here are technical evidence requirements, not requests for more user confirmation in this documentation task.
