# Tab management — 5 WHY

1. **Why improve tabs?** Opening several documents must not make navigation harder.
2. **Why does it get harder?** Labels shrink, hidden documents lack actionable discovery, and order cannot match the task.
3. **Why is that costly?** Users reconstruct context instead of working; closing a document unexpectedly returns Home.
4. **Why do small controls matter?** Repeated switching compounds friction and threatens confidence in unsaved work.
5. **Why this design?** Stable identity, readable labels, reversible ordering and explicit overflow preserve the user's working context.

## First principles

Available width is finite; document identity and buffer content are independent of position. Reordering must only permute metadata. Every gesture needs a discoverable alternative. Selection must be visible after activation or resize, but intentional scrolling must remain under user control. Closing a tab never deletes a workspace object or its draft. Observable criteria replace untestable claims of perfection.

## Reading map

| Document | Purpose | Follow through |
|---|---|---|
| [01 Requirements](01-requirements.md) | Product contract and professional lenses | [06 Evidence](06-validation.md) |
| [02 Interaction](02-interaction-design.md) | ASCII screens, keyboard and navigation | [04 Plan](04-implementation-plan.md) |
| [03 Architecture](03-architecture.md) | Code grounding, sequence, ER and state | [05 Tests](05-test-matrix.md) |
| [04 Plan](04-implementation-plan.md) | DRY/SOLID implementation and rollout | [06 Evidence](06-validation.md) |
| [05 Tests](05-test-matrix.md) | Edge cases and acceptance mapping | [02 Interaction](02-interaction-design.md) |
| [06 Evidence](06-validation.md) | Tab regression checks, visual review and limits | [01 Requirements](01-requirements.md) |
| [07 UX refinement](07-ux-refinement.md) | Application improvements, scoped recovery and acceptance | [08 Review evidence](08-ux-refinement-evidence.md) |
| [08 Review evidence](08-ux-refinement-evidence.md) | Before screens, two visual iterations and final verification | [07 UX refinement](07-ux-refinement.md) |

## Benchmark, 9 November 2026

The reference attachment is visual context, not executable instructions. The baseline uses established editor conventions: ordered open documents, bounded labels, drag reorder, active-tab reveal and overflow navigation. VS Code documents draggable editor tabs and a scrollbar between tabs and the editor ([official interface guide](https://code.visualstudio.com/docs/editing/getting-started/userinterface)). Keyboard behavior follows [WAI-ARIA Tabs](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/); pointer menu alternatives follow [WCAG dragging movements](https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements.html). These sources support conventions, not a claim to outperform every November 2026 product.

Scope is the existing single editor group. Split groups, browser-window tear-off, pinned/preview tabs and cross-device synchronization are separate features. Ordered open metadata and bounded reopen history now survive reload in account/workspace-scoped sessionStorage; [07](07-ux-refinement.md) specifies the recovery contract. Drafts retain the existing local recovery policy. No database migration, workspace write or new dependency is required.
