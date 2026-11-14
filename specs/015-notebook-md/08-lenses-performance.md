# 08 — Seven expert lenses and complexity contracts

[Index](README.md) · Evidence: [02](02-code-grounding.md) · Requirements: [03](03-requirements.md)
· Delivery: [10](10-implementation-plan.md) · Performance tests: [11](11-tests-traceability.md)

These are review perspectives applied to one design, not claims that independent reviewers or
subagents approved it. Each lens contributes a decision and a release gate.

## Product owner

The job is to read an explanation, edit it deliberately, then return to the explanation. The user's
resting-state rule is [MD-01](03-requirements.md#requirements), not an optional visual preference.
Prioritize hierarchy, explicit preview, safe source and discoverable controls over breadth of extensions.
P0 must work without a warehouse, AI request or image backend. P1 images/outline are independently
shippable. Acceptance requires the Bakehouse story and negative cases, not a toolbar screenshot alone.

## Full stack developer

Use one parser/model boundary and explicit surface adapters. Reuse `EditorSurface`, SOURCE checks,
save/fence APIs, `CopyButton`, existing app tokens and editor abstractions. A rich-text editor or
client HTML serializer would create a second source authority. Formatting must dispatch an atomic
host transaction; full-document `setValue` as a toolbar shortcut would bypass undo intent/selection.
Gate: [T02/T10/T13](11-tests-traceability.md#test-groups) prove transaction, persistence and consumer compatibility.

## Database expert

Rendering needs **zero database queries or migrations**. The [ER diagram](05-architecture.md#logical-er-model)
is logical. Do not store preview HTML, cached ASTs or inferred titles in Lakebase. Existing notebooks
remain SOURCE documents with opaque version tokens; compare-and-write remains server-owned.
Drafts and cache keys must include an appropriate workspace/user scope; do not share document text
or media across identities. Permission denial is terminal for the caller's read, never a reason to
query via another principal. Gate: no new schema/warehouse call on preview; [T10/T14/T15](11-tests-traceability.md#test-groups).

## UX and UI designer

Separate a quiet document reading surface from source editing. Preserve semantic depth and visual
depth, readable line length, non-hover Edit, local table/code overflow, keyboard toolbar access and
predictable focus restoration. Formatting, preview and save are different actions with different
feedback. Dark mode requires measured contrast rather than a color inversion assumption.
Gate: [wireframes](04-ux-wireframes.md), [T03/T09/T18/T20](11-tests-traceability.md#test-groups).

## AI engineer

Generated Markdown may be incomplete, malformed, oversized or adversarial. Model text is data;
it cannot cause tools, SQL or network loads just by rendering. The same new parser must not regress
streaming chat. When an agent changes a notebook, preserve local editing and use the existing incoming-
change review path. Render error diagnostics never assert unverified business facts or completed work.
Gate: every-prefix/fuzz corpus, dirty-agent race and forbidden-network assertions in
[T11/T13/T15/T19](11-tests-traceability.md#test-groups).

## System design expert

View mode, focus, source version, save state and observation are independent dimensions. Version
each derived result, keep runtime work local and cancellable, and dispose all requests/listeners.
No global Markdown request cache keyed only by source hash; no external-resource service credential.
Fallback has bounded scope and always retains source. Roll out notebook adapters separately from
chat behavior; rollback never changes source storage. Gate: [statecharts](06-statecharts.md),
[T12/T20](11-tests-traceability.md#test-groups).

## O(n) expert

### Complexity analysis

Define `C` = cells, `R` = runnable cells, `S` = total source units read, `L` = changed cell units,
`A` = AST nodes, `H` = headings, `K` = changed cells in an external update, `M` = loaded media.
Offsets are UTF-16 in the editor; server character limits are Python code points. Limits must
state their unit explicitly ([E48](09-edge-cases.md#register)).

From [C8](02-code-grounding.md#c8), each above/below `spanIds` call rebuilds a run plan and
filters `R` IDs with a linear `findIndex` over `C` cells: `O(S + R*C)` conservatively including
source inspection. It is called twice per rendered cell: `O(C*S + R*C^2)`. If `R` grows with `C`,
there is a **potential O(C^3) term**, not just a quadratic one. This is a static upper-bound
analysis; it is not a measured latency result. Keep this prerequisite in scope because adding
preview updates to an already repeated notebook traversal can amplify the cost.

Current math helpers perform repeated forward delimiter searches on incomplete input; their
apparent single outer loop does not establish a worst-case linear bound. The shared renderer also
reparses changed streamed prefixes. `memo` prevents some unchanged React renders; it does not turn
a changed-text parse into an incremental algorithm. Use adversarial inputs to validate the candidate.

### Target work

| Operation | Target bound | Mechanism |
|---|---|---|
| Initial bounded document preparation | O(S + C + A) | Parse each Markdown cell once; build cell-index/runnable metadata once |
| Render one changed cell | O(L + A_changed), plus at most O(C) shallow reconciliation | Cache unchanged parse models; memoized cell view and stable handlers |
| Source typing before preview | O(L) host transaction; avoid O(S) serialization each keystroke | Dirty revisions; coalesce document draft/serialization at a bounded debounce, flush on save/navigation |
| Above/below button availability | O(1) per cell after O(S + C) metadata | Runnable prefix/suffix counts; create ID arrays only on action |
| Outline | O(H) from existing AST heading collection | No second full source parse; changed cell updates local heading entries |
| Save | O(S + C) bounded snapshot/check/serialization | Existing serializer authority, one coordinated flush; no render AST conversion |
| External K-cell update | O(S) reconciliation baseline + changed-cell parses | Retain IDs/models for unchanged cells; no hash-only equality assumption |
| Cache memory | O(open retained source + bounded A) | Document-scoped LRU with eviction; no unbounded per-revision history |

These are target contracts, not blanket claims about third-party parser internals or React layout.
If profiling disproves a bound, reduce work, constrain inputs or isolate parsing before release.
Adding a Web Worker alone cannot make a superlinear algorithm linear; it only moves its cost.

### Budgets

Proposed budgets to verify on an explicitly recorded reference machine/browser in a production build:

- Retain existing 400-cell, 20,000-code-point per-cell and 400,000-byte document read limits;
  do not increase them to hide a UI failure. Over-limit detection must be complete and read-only.
- Preview parse limit: 10,000 AST nodes, nesting depth 64 and 200 math spans per cell. Budget overflow
  produces a bounded fallback; source remains intact. These are proposed independent rendering limits.
- Active-cell Edit/Show preview response p95 at most 100ms for supported 20k-character fixtures;
  if render is async, mode feedback within one animation frame and no stale result acceptance.
- No parser/metadata task over 50ms on the fixture suite. Benchmark 1k/5k/10k/20k near-miss text;
  doubling input should not systematically exceed 2.5x median work after warm-up. Record samples;
  treat this as an empirical guard, not mathematical proof.
- With 400 small cells, toolbar availability derives from one notebook metadata pass; instrument
  parse/run-plan counters to reject per-cell re-planning. Unchanged Markdown parses remain zero
  when only a sibling cell caret or execution timer updates.
- Keep at most 8 MiB of derived AST/editor-snapshot cache per document, excluding authoritative source
  and explicitly retained undo data; retain at most 5 inactive document caches, with a 32 MiB global
  derived-cache ceiling. Evict inactive content first; no silent source/undo loss to meet this target.
  Audit and document the editor's own undo bounds; do not retain a new full undo snapshot on every
  preview revision or exclude an unbounded snapshot collection from the resource accounting.
- Parser dependency increase target at most 75 KiB gzip in the loaded feature path; avoid eager KaTeX
  and keep code highlighting optional/lazy. Record before/after build sizes and justify any exception.
- Capture layout shift and scroll anchor movement during mode/media/theme changes; no viewport jump
  without user navigation. Do not claim a universal zero CLS for deliberate source/preview height changes.

Initial optimization can keep a bounded O(C) array copy; do not build a complex global state system
solely to claim O(1). Incremental work and evidence matter more than asymptotic labels.

