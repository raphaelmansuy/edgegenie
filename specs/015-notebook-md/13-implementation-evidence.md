# 13 — Implementation and verification evidence

[Index](README.md) · [Requirements](03-requirements.md) · [Edge cases](09-edge-cases.md)
· [Test plan](11-tests-traceability.md) · [Visual review](e2e/visual-review.md)

Implemented 14 November 2026. The assessment documents retain the original baseline and proposed
budgets; this record distinguishes shipped behavior from measurements and remaining manual checks.

## Implemented seams

| Responsibility | Code | Contract |
|---|---|---|
| Shared grammar/model | `web/src/domain/markdown/parse.ts` | CommonMark/GFM AST; bounded source, nodes, depth and math; one model supplies headings and preview |
| Trust classification | `web/src/domain/markdown/policy.ts` | Central HTTPS/email/workspace/relative/fragment policy; unsafe schemes remain inert |
| Presentation | `web/src/components/Markdown.tsx`, `notebook-markdown.css` | Shared typed renderer with explicit notebook/answer profiles; six visual heading depths, tables, tasks, code and math |
| View state | `web/src/domain/markdown/viewstate.ts`, `NotebookEditor.tsx` | Explicit reading/editing; composition-aware preview; collapse and revocation return to reading |
| Source transactions | `web/src/domain/markdown/format.ts`, `MarkdownToolbar.tsx`, `editor/host.ts` | One undoable editor transaction; UTF-16 offsets; modal link/image validation and stale-selection rejection |
| Editor lifetime | `web/src/editor/Editor.tsx`, `codemirror.ts` | Dispose live view on preview, retain one history/selection snapshot per cell; wrap Markdown source on narrow screens |
| Media | `MarkdownImage.tsx`, `domain/markdown/media.ts`, `api/domain/markdown_media.py` | No fetch during render; four concurrent loads; abort/generation ownership; 5 MiB/16 MP raster limits; no animated PNG/SVG |
| Caller authorization | `api/adapters/databricks/workspace.py`, `api/routers/api.py` | User-token-only image endpoint, no redirects/principal fallback, no-store and nosniff |
| Source completeness | `api/domain/notebook.py`, workspace reader/save guard, `Viewer.tsx` | Count lookahead and cell/byte truncation promoted to read-only document; server refuses incomplete replacement |
| Existing persistence | `EditorSurface.tsx`, `domain/drafts.ts` | Existing fence/version/conflict save path; coalesced notebook serialization and explicit flush; workspace/user-scoped drafts with active-tab fallback |
| Run metadata | `domain/cellrun.ts`, `NotebookEditor.tsx` | One runnable metadata pass and prefix counts; avoids per-cell repeated run planning |

No schema migration, stored HTML, SQL execution from preview, WYSIWYG serializer, or new save endpoint
was introduced. The Python SOURCE authority and existing client parity corpus remain in use.

## Executed verification

- `make check`: **2,329 backend tests passed**, 40 skipped; **1,292 frontend tests passed** in 90 files;
  TypeScript and Python undefined-name checks passed. Existing warning counts are retained in the runner output.
- Production frontend build passed. Main bundle is approximately 257 KiB gzip, approximately 41 KiB
  above the baseline; the new grammar remains below the proposed 75 KiB dependency-increase budget.
- [Chromium report](e2e/report.json) and [WebKit report](e2e/webkit/report.json): styled default reading,
  immediate preview of the last character, retained undo, atomic formatting, safe link dialog,
  explicit SOURCE save, outline/collapse, table/task/fence/MathML, image permission denial,
  dark/narrow editor wrapping, and partial read-only viewing. API fixtures persist the submitted SOURCE.
  Tests use the built app and real browser interactions; workspace responses are controlled fixtures.
- [Screenshot review](e2e/visual-review.md): every retained PNG was opened individually. Initial
  defects and subsequent corrections are recorded; screenshots are evidence rather than a universal
  claim about all devices or future input.
- New parser tests cover incomplete prefixes, deep nesting, literal PUA markers, unsafe destinations,
  Unicode edits and adversarial delimiters. Lifecycle tests exercise 10,000 generated view events,
  media concurrency/cancellation, identity-scoped drafts and failed storage.
- Backend additions exercise 399/400/401-cell boundaries, 19,999/20,000/20,001 Unicode code points,
  document byte overflow, refusal before import, caller-only media and raster restrictions.
- Existing reconciliation, save/fence/conflict, keyboard, notebook round-trip and shared renderer tests
  ran as part of the full suite; they remain the regression gates for agent updates and saves.

## Performance observations and resource ownership

Reference: this macOS ARM64 workstation, installed Node/Vitest versions, warmed runs, seven samples
per length. Unmatched LaTeX delimiters are a regression fixture: a negative-close cache prevents
repeated searches of an absent closing delimiter.

| UTF-16 source units | Median parse ms | Maximum sample ms |
|---|---:|---:|
| 1,000 | 1.79 | 6.46 |
| 5,000 | 5.74 | 6.88 |
| 10,000 | 10.22 | 14.98 |
| 20,000 | 22.10 | 23.59 |

These are empirical parser samples, not a proof of every grammar input's complexity or end-to-end
p95 interaction latency. Cell ASTs use weak immutable-cell keys: no persistent source cache and no
per-revision snapshot collection. Each mounted cell owns at most one retained editor snapshot.
CodeMirror undo retains a minimum depth of 30 events and its normal grouping; it is not a byte cap.
The proposed 8/32 MiB cache ceiling and full 400-cell retained-heap profile have **not** been certified.
Narrow controls wrap with roving keyboard access instead of introducing a second overflow menu.

## Practical verification limits

The E2E API fixtures do not certify live Unity Catalog/image ACL combinations. Real permission errors
remain terminal; no service-principal fallback exists. Manual screen-reader reading, every 200% zoom
combination, complete print pagination and long-session heap profiling remain separate checks.
No claim of exhaustive edge-case enumeration or universal visual perfection is made. Runtime bounds,
inert rendering, local fallbacks and regression fixtures mitigate unsupported/malformed inputs.

Deployment status is recorded separately after the release command and served-version verification.

## Verified release

Implementation commit `c2606665d1b6c484dee9966b1f2d18348fc7d910` was pushed to `origin/main`
and deployed to the existing OpenGenie app. [Deployment evidence](e2e/deployment.json) records
SUCCEEDED, RUNNING and the exact resolved Git commit. This app belongs to the repository's
`opengenie-dev` workspace (`dbc-cb61f1e1-bd8e`); the distinct configured `prod` workspace was not changed.

The user explicitly approved profile discovery and use of the existing login after the repository
PAT was rejected by the separate prod workspace. No scopes, grants or database schema were changed.
The warehouse was STOPPED; no SQL or compute job was needed.

[Deployed smoke](e2e/deployed-smoke.json) verified the real API identity and served frontend,
styled Markdown, source editing and return to preview. Its notebook GET uses an intercepted fixture
and all mutation requests are blocked. [Deployed screenshot](e2e/11-deployed-reading.png) was opened
and visually inspected: heading hierarchy, list, semantic table, Edit control and white reading
surface are readable and aligned. This is not a live notebook-write or live-media-ACL test.
