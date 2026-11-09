# Implementation plan

Status: local implementation and verification complete, subject to the explicitly recorded browser/workspace limits in [06](06-validation.md).

Inputs: [5 WHY](README.md), [requirements](01-requirements.md), [architecture](03-architecture.md). Completion evidence belongs in [06 Validation](06-validation.md).

1. **Pure operations (TM-04/07/08):** add `domain/tabs.ts`; test permutations, invalid IDs/indexes, adjacent close behavior and DOM-ID collisions. Preserve object references and revisions.
2. **Wire App (TM-04/07/09):** pass move and bulk-close callbacks; update selected view and assistant binding together; record up to 20 closed metadata records; reopen through existing open path at prior index; focus successor or document panel. Never place side effects in React state updaters.
3. **Overflow (TM-01/02/03/10):** reserve fixed controls, remove shrink-to-fit and floating badge, bound labels, measure on scroll/list/resize, reveal active using strip-only deltas, translate wheel without stealing zoom.
4. **Reorder (TM-04/05):** pointer capture, mouse threshold/touch hold, marker, bounded time-based edge scroll, commit only on valid release, cancel and cleanup. Keyboard/menu invoke the same move command.
5. **Discovery (TM-05/06/08):** searchable anchored picker, context actions, full-path disambiguation, menu key model, Escape/outside dismissal and focus restoration. Register global reopen in existing shortcut registry.
6. **Draft safety (TM-09):** expose dirty status through existing viewer seam; flush latest unsaved file buffer when leaving before debounce; keep existing explicit recovery flow and save fence.
7. **Verification:** meaningful unit/component tests plus real browser tests through App and mocked read-only HTTP fixtures. Test no mutation request during reorder, same editor node/buffer, focus/binding after close, overflow geometry and drag cancellation. Save every evidence screenshot under [screenshots](e2e/screenshots); inspect each; fix observed defects and rerun affected scenarios.
8. **Release review:** run full frontend tests/build and spec-link/diagram parsers; report exact results and limitations in [06](06-validation.md). No production deployment is part of this request.

## Application refinement follow-through

The implemented follow-up in [07](07-ux-refinement.md) reuses one ActionMenu across four surfaces, isolates scoped working-set serialization from App orchestration, preserves editor instances during theme updates, and uses shared browser fixtures. [08](08-ux-refinement-evidence.md) records two inspection-driven iterations and final checks. The original tab operations above remain the single paths for moving, closing and reopening.

## DRY and SOLID checks

Single responsibility: domain order rules, UI geometry, App context, and editor persistence have distinct owners. Open/closed: the strip issues ID-based callbacks for all document kinds. Liskov: notebook/file/table obey the same tab contract. Interface segregation: tab metadata contains no editor or API implementation. Dependency inversion: callbacks connect UI to App; no workspace write is introduced for ordering. One move function serves drag, keyboard and menu; one close path serves cross, middle click, shortcut and bulk actions; one DOM-ID function labels tab and panel. Existing tokens, icons, drafts, route and shortcut registry are reused.

## Failure mitigation

Invalid/stale move is a no-op; removing the source cancels its gesture; external additions cannot erase existing objects. Unmount releases timers/listeners/frames. Storage unavailable does not crash tabs; existing draft recovery limits apply (50 drafts, 30-day TTL). Permission errors remain visible in the viewer and never trigger alternate data access. Manual scrolling is never reset by a hidden-count render. Cancellation preserves order and selection; document keys never include index.
