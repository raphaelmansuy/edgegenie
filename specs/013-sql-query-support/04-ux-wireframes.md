# Navigation, screens and interactions

[Index](README.md) · [Requirements](03-requirements.md) · [Lifecycle charts](07-sequences-statecharts.md) · [E2E](11-test-e2e-plan.md)

## Information architecture

Queries is a permanent navigator destination in the existing shell. Its central area is a library. SQL Editor is a command/landing destination that restores the last query document; it does not create a second application shell. Query tabs coexist with notebooks/files/tables. Own SQL run history is a library subview and a per-query panel; native workspace-wide Query History remains an external handoff. The assistant stays in the current dock.

```ascii
+--------------------------------------------------------------------------------------+
| OpenGenie - existing shell                                                           |
+--------------------------------------------------------------------------------------+
| Home             --> New SQL query --> Local draft --> Create Query / Save copy      |
| Navigator                                                                            |
| |-- Workspace    --> notebooks / files (SQL source files keep file identity)         |
| |-- Catalog      --> table --> Open as query (schema-backed proposal)                |
| |-- Queries      --> Library --> Open saved Query --> Query document tab             |
| |   |-- Recent   --> recently opened permitted assets                                |
| |   |-- Favorites (OpenGenie)                                                        |
| |   +-- My runs  --> immutable snapshot / status / bounded result                    |
| +-- SQL Editor   --> last query document, or New / Open landing                      |
+--------------------------------------------------------------------------------------+
| Assistant dock  <--> attached query / selection / explicit result context            |
| Native handoff   --> sharing, global history, schedules and advanced features        |
+--------------------------------------------------------------------------------------+
```

Navigation retains browser Back/Forward and the current hash router. Proposed routes: `#/queries`, `#/queries/history`, `#/query/<native-uuid>`, `#/query-draft/<draft-uuid>`. Workspace identity is selected by the app deployment and validated on references; copied links use that deployment's origin. Cross-workspace asset payloads display a mismatch with a deliberate external link instead of switching credentials. Do not put SQL, parameter values, or result data into URLs.

## W1 Queries library

```ascii
+------------------------------------------------------------------------------------------------+
| OpenGenie / Queries                                                    [New SQL query]         |
+------------------------------------------------------------------------------------------------+
| [Search scanned queries.........................................................] [Clear]      |
| [Owned by me v] [Modified this week v] [Favorites: OpenGenie]                       [Filters]  |
+------------------------------------------------------------------------------------------------+
| Title                         Owner          Modified          Warehouse          Actions      |
| revenue by day                analyst@...    12 Nov 10:32      Analytics          [Open] [...] |
| quality checks                engineer@..   11 Nov 16:04      SQL warehouse      [Open] [...]  |
+------------------------------------------------------------------------------------------------+
| 2 matches in 50 scanned queries. More queries may match.                         [Load more]   |
| Upstream creation order. Search and filters apply to scanned pages.                            |
+------------------------------------------------------------------------------------------------+
| Empty: No saved Queries found in scanned pages. [New SQL query] [Load more]                    |
| Filtered empty: No matches in scanned pages. [Clear filters] [Load more]                       |
| Denied: Query access unavailable. [Details] [Open Databricks]                                  |
+------------------------------------------------------------------------------------------------+
```

Default upstream order is retained. Owner/date/favorite filters and text search apply to currently cached scanned pages; the coverage line remains visible even when zero matching rows appear. Load more adds one native page and deduplicates by canonical ID. A bounded Scan more action can fetch up to five sequential pages with progress/cancel. When the 1,000-item session cache bound is reached, older pages can be evicted and reread. Display the retained page window as the search scope and total scanned count separately. After eviction, reaching the last upstream page does not make local filtering globally complete. Offer Previous pages/restart scan or native search rather than hiding that limitation.

States: skeleton → ready; ready/partial → fetching more; no assets → create call to action; no matches → Clear filters/Load more; denied → permission-specific recovery; rate-limited → retry countdown. Preserve filters and focus after each page. Missing metadata is “Unknown,” never a fabricated owner/zero timestamp.

## W2 Query editor

```ascii
+---------------+------------------------------------------------------------+--------------------------+
| Navigator     | Tabs: [Notebook] [revenue by day *] [+]                    | Assistant                |
+---------------+------------------------------------------------------------+--------------------------+
| Workspace     | revenue by day  [Query] [Local changes]                    | Query attached           |
| Catalog       | [Save copy] [Copy link] [Open in Databricks] [...]         | [Explain] [Optimize]     |
| Queries *     | Warehouse: Analytics v | Catalog/schema: main/sales        | Suggestions only         |
| My runs       | Run as: signed-in viewer | Preview: 1,000 rows             | [Preview diff]           |
+---------------+------------------------------------------------------------+--------------------------+
|               | [Run selection] [Cancel: disabled]                         | Apply changes locally    |
|               | Parameters: cutoff [2026-11-01] DATE   [NULL: off]         | Then choose Run          |
|               | 1 -- query source in existing CodeMirror editor            |                          |
|               | 2 -- real schema checked before AI authors SQL             |                          |
|               | 3 -- selection scope is visibly highlighted                |                          |
+---------------+------------------------------------------------------------+--------------------------+
|               | [Results] [Run details] [History]                          |                          |
|               | Succeeded | 0.8s | 100 rows returned | Preview capped      |                          |
|               | Source changed since this run. [View run snapshot]         |                          |
|               | column #1       column #2       column #3                  |                          |
|               | exact text      NULL            empty string               |                          |
|               | [Previous rows] [Next rows] [Copy selected rows]           |                          |
+---------------+------------------------------------------------------------+--------------------------+
```

The title and Query badge identify a native asset. A draft badge says “Local draft”; an edited native query says “Local changes.” Save copy is the baseline action for an existing native Query. Create Query is the first-save action for a new draft. Both open a destination/name dialog and return a native asset ID. Once a draft is promoted, alias its old draft ID to the native document in the working set so tabs, recents, history and return focus stay attached to one object.

Run selection wins over buffer only for one nonblank contiguous selection. With no selection, Run query accepts exactly one supported statement. Ctrl/Cmd+Enter invokes the labeled action. A multistatement buffer is still editable but cannot run as a batch in R1. The server revalidates the captured scope; editor key handling alone is not the enforcement boundary.

Editing during a run is allowed. The running snapshot stays pinned; its results get a “Source changed since this run” label. A second Run for that document is disabled while the current attempt is nonterminal, including uncertain submission; Cancel targets that attempt. Switching tabs does not cancel it. Own history exposes runs after a tab closes.

## W3 Narrow editor

```ascii
+--------------------------------------------+
| [Menu] OpenGenie         [SQL] [Assistant] |
| [revenue by day *]                         |
+--------------------------------------------+
| Local changes                 [Save copy]  |
| Warehouse: Analytics v  |  Run as: viewer  |
| [Run query] [Cancel] [More]                |
| [Editor *] [Results] [History]             |
+--------------------------------------------+
| cutoff [2026-11-01] DATE                   |
| 1 -- SQL source; editor owns horizontal    |
| 2 -- scrolling, page width stays fixed     |
+--------------------------------------------+
| Run: succeeded | source changed            |
| [View snapshot] [Show results]             |
| Navigator and assistant use current        |
| shell drawers; no second SQL overlay.      |
+--------------------------------------------+
```

At narrow widths, use one central content region with Editor/Results/History tabs and the existing navigator/dock drawers. Never stack a second results overlay over a modal assistant. Keep Run/Cancel visible; put lower-priority actions in a named menu. Long titles ellipsize with a full accessible name. Horizontal scrolling is confined to editor/results, never the page. Do not invent query-specific shell breakpoints; use the current panel resolver.

## W4 Ambiguous submission and save copy

```ascii
+--------------------------------------------------------------------------------------+
| Run outcome unknown                                                                  |
+--------------------------------------------------------------------------------------+
| We could not confirm whether this run started. Check before running again.           |
| Your source is retained. Closing this panel does not cancel SQL.                     |
| [Check status] [Open native history] [Acknowledge outcome unknown]                   |
+--------------------------------------------------------------------------------------+
| Create Query / Save copy                                                             |
| Name:        [revenue by day copy...........................................]        |
| Destination: [/Users/<signed-in-user>/agent_scratch.........................]        |
| This creates a new Query. It does not update the original or copy its permissions.   |
| [Cancel] [Create Query]                                                              |
+--------------------------------------------------------------------------------------+
```

Submission copy: “We could not confirm whether this run started. Do not run it again until you check its status.” Offer Check status when a handle exists; otherwise native history and an explicit Acknowledge outcome unknown action. Acknowledgement does not automatically retry. A deliberately new run requires another Run action after reviewing duplicate-execution risk.

Save failure keeps the exact local buffer and destination. An ambiguous create says “The query may have been created”; do not retry POST blindly or match by title alone. Provide operation status and an asset-list/native handoff. Query copy has its own permissions; the dialog must not imply original ACLs are copied.

## Interaction details and accessibility

| Concern | Contract | Tests |
|---|---|---|
| Search and filters | Debounce 250ms; announce updated match count once per settled search; stale responses cannot replace a newer scope. | T01, T02 |
| Keyboard | Named toolbar, roving tab/list controls, visible focus, editor Tab escape path, Ctrl/Cmd+S opens explicit create/copy action. No global key starts SQL from a text input elsewhere. | T03, T16 |
| Errors | Inline field errors retained; submit focuses an error summary linked to invalid fields. Denial is not an empty list. | T05, T10, T16 |
| Async status | Polite live region for meaningful state changes; elapsed timer excluded from repeated announcements; failure/cancel confirmation remains visible. | T06–T09, T16 |
| Results | Semantic table caption with run context; row/column paging has accessible totals and position. NULL is a labeled value distinct from empty string; never inject returned HTML. | T11, T12 |
| Focus | Dialog closes to initiating control; drawer closes to toggle; result completion does not steal editor focus. Unmounted control returns focus to stable document toolbar. | T13, T16 |
| Color | Reuse app semantic tokens. Normal text at least 4.5:1; meaningful UI boundaries 3:1. State also has icon/text; pastel diagram fills are documentation styling, not pale UI text. | T16 |
| Motion and zoom | Respect reduced motion; 320px/375px/768px/1024px/1440px and 200% zoom; light/dark/forced colors; focus cannot be obscured by sticky controls. | T16 |
| Row copy/download | Baseline Copy selection clearly names loaded/visible rows, with explicit user gesture. Large downloads and native workspace download-policy integration are deferred. No download control until policy is verified. | T11, T12 |

Baseline does not show native Share permissions, Publish, Schedule, Run all or chart controls. Put meaningful native handoffs in More with context. [SQ-24](03-requirements.md) governs future capability discovery.
