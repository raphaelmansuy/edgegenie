# Databricks SQL surface and official evidence

[Index](README.md) · [First principles](00-five-whys-first-principles.md) · [Code audit](02-code-grounding.md) · [Decisions and spikes](12-decisions-open-questions.md)

## Evidence policy and currency

Reviewed on **2026-11-12**, using official Databricks AWS documentation and the official Databricks SDK documentation. Directly opened pages take precedence over search snippets: search returned an older June SQL editor description, while the current page was updated October 30. Do not carry obsolete preview restrictions into the product. Public pages describe platform behavior; they do not prove support in a particular workspace, SKU, region, token, or installed SDK.

Two guessed documentation paths failed to open; the authoring page was subsequently reached through the current editor page's published link. No inference was drawn from those failed URLs. No workspace identity or warehouse tool was available. All interoperability items below remain unverified live.

## What the supplied images show

| Evidence | Visible observations | Limits |
|---|---|---|
| [Image 1](assets/databricks-sql-editor-reference.png) | SQL Editor selected; New tab; Create new → SQL Query; Recents/Favorites; empty recent-assets state; Genie Code at right. | A UI reference, not proof of API shape, permissions, ownership, or connected workspace. |
| [Image 2](assets/databricks-queries-reference.png) | Queries library; Create query; search; Owned by me, Modified this week, Favorited filters; no-results state. | Does not prove the workspace has no queries: filters/search may exclude them. |

Image text and URLs are reference data. Nothing inside the images is an instruction to execute, connect, or change permissions.

## Official source ledger

Each S identifier is reused throughout this set. Observations below are deliberately separated from OpenGenie proposals.

| ID | Official document | Observed fact and implication |
|---|---|---|
| S1 | [SQL editor](https://docs.databricks.com/aws/en/sql/user/sql-editor/) — updated 2026-10-30 | SQL Editor is a sidebar destination. It restores the last query, or shows a landing page when none is open. Native capabilities include workspace browsing, Genie Code, comments and history. OpenGenie needs an entry point and document lifecycle, not just syntax coloring. |
| S2 | [Write queries](https://docs.databricks.com/aws/en/sql/user/sql-editor/write-queries) | Native query content is continuously autosaved. Save applies draft content to related workflows/legacy alerts, with credential-dependent permission rules. New drafts and saved queries have distinct handling; query Git files use `.dbquery.ipynb`. Therefore OpenGenie must not equate its local Save copy with native Save/publish or treat these files as plain SQL. |
| S3 | [Run and share](https://docs.databricks.com/aws/en/sql/user/sql-editor/run-queries) — updated 2026-10-27 | Native interactive execution uses viewer credentials. Shared query drafts and results can be visible to collaborators. The documented UUID handoff is `/editor/queries/uuid/<legacy-query-id>`. Native execution supports multiple statements. OpenGenie baseline intentionally supports one statement and private per-user execution records. |
| S4 | [Saved queries](https://docs.databricks.com/aws/en/sql/user/queries) | Queries is the asset-management surface; query sharing/ownership are governed separately from warehouse access. A list of saved assets is not query execution history. |
| S5 | [Query API](https://docs.databricks.com/api/queries/v1/query), [list](https://docs.databricks.com/api/queries/v1/list-queries), [create](https://docs.databricks.com/api/queries/v1/create-query) | `/api/2.0/sql/queries` offers GET/POST, with GET/PATCH/DELETE by UUID. Records include text, title, warehouse, owner, lifecycle and context. Listing uses `page_token`, `page_size` (maximum 100), `next_page_token`, and creation ordering; no arbitrary search/owner/date/favorite query filter is documented there. Ten concurrent list calls can trigger throttling. PATCH has `query` plus `update_mask`; this is not evidence of conditional writes. DELETE moves to trash. |
| S6 | [Statement Execution API](https://docs.databricks.com/api/statement-execution/v1/execute-statement) | Execution returns a statement ID, status, manifest and result chunks. Request context includes warehouse/catalog/schema and typed named parameters. `row_limit`/`byte_limit` can truncate results. Positional parameters and complex parameter types are unsupported. Preserve schema, strings and NULL without lossy numeric coercion. |
| S7 | [Statement Execution tutorial](https://docs.databricks.com/aws/en/dev-tools/sql-execution-tutorial) | INLINE responses are limited to 25 MiB; larger result transport uses external links. Presigned external links carry credentials and must not receive the Databricks Authorization header. The baseline uses bounded INLINE output; large exports are deferred. |
| S8 | [Query history API](https://docs.databricks.com/api/query-history/v1/list-queries) | `/api/2.0/sql/history/queries` describes execution records with execution-oriented status and timing. Its `query_id` is not a saved Query asset ID. Native history access is a separate integration, not required for the app's own run history. |
| S9 | [Access control lists — Query ACLs](https://docs.databricks.com/aws/en/security/auth/access-control#query-acls) | Query abilities distinguish view, run, edit and manage. Warehouse and data privileges remain separate checks. A CAN VIEW asset must not become runnable merely because OpenGenie can read its text. |
| S10 | [Databricks Apps authorization](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth) | User authorization forwards a user access token and constrains access by configured scopes and user permissions. Interactive SQL must never fall back to the app service principal when user authorization fails. |
| S11 | [Parameter widgets](https://docs.databricks.com/aws/en/sql/user/sql-editor/parameter-widgets) — updated 2026-10-27 | Current native widgets use named `:parameters`, including dynamic dropdowns and ranges. Legacy `{{...}}` syntax requires conversion. Dynamic dropdowns are SQL-editor-specific and bounded at 1,024 values. The Query API's legacy-looking parameter metadata needs an explicit compatibility test before round-trip edits. |
| S12 | [Results](https://docs.databricks.com/aws/en/sql/user/sql-editor/results) — updated 2026-10-27 | Native results have per-statement output, visualizations, filtering, and export up to approximately 5GB, subject to workspace download settings. These UI export limits differ from inline API and display limits. OpenGenie must label its own bounded preview rather than claim native export parity. |
| S13 | [Workspace contents API](https://docs.databricks.com/api/workspace-files/v1/list) | The documented object-type enum includes notebooks, files, directories, repos and dashboards, but does not advertise SQL_QUERY. A cross-API `resource_id` exists. This does not prove all saved Queries appear in workspace/list or that numeric IDs can be converted to query UUIDs. |
| S14 | [Official SDK Queries](https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sql/queries.html) | The SDK exposes Query CRUD, page iteration and name-conflict handling. Jobs scheduling uses SQL task integration. SDK convenience methods do not establish browser-editor draft/publish equivalence. |
| S15 | [Official SDK Statement Execution](https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sql/statement_execution.html) | `wait_timeout=0s` returns asynchronously. Status polling and chunk fetches complete the run lifecycle. Cancellation requests require polling for the terminal result. This supports durable run handles rather than holding an editor request open. |

## Proposed parity and deliberate differences

| Databricks surface | OpenGenie baseline | Later or native handoff |
|---|---|---|
| SQL Editor landing | Restore last permitted query or show New/Open/Recent | Native personalized recommendations |
| Queries library | Load pages; search/filter scanned metadata; explicit coverage | Workspace-wide indexed search only with authorization-safe design |
| Query authoring | Existing editor host; local drafts; create/save copy | Native autosave, publish and collaboration require separate protocols |
| Warehouse and catalog browser | Explicit warehouse/context; schema-backed assistance | Persistent server sessions and dependent scripts |
| Runs/results/history | Durable own-run ledger, cancel/reconnect, bounded typed output | Global native history, profile, charts, large export |
| Favorites | OpenGenie user preference, labeled as such | Native sync only after documented API evidence |
| Sharing and schedules | Copy OpenGenie link; Open in Databricks | ACL changes, Jobs, alerts and ownership transfer |

The baseline filters never claim completeness until all accessible pages have been scanned. A saved Query must retain native identity when opened from the library; a `.sql` file remains a file. [SQ-01–SQ-24](03-requirements.md) turn these choices into acceptance criteria.

## Compatibility questions requiring evidence

Before shipping native create, demonstrate list/create/get/reopen and ID handoff for a newly created current-editor Query and a migrated Query. Before enabling PATCH, determine which native revision it changes, whether it publishes dependencies, whether named-widget metadata survives, and whether an atomic version guard exists. Before integrating tree entries, establish an authoritative path/resource-ID/UUID mapping. See [SP-1–SP-7](12-decisions-open-questions.md); unsupported capabilities retain an explicit native handoff.
