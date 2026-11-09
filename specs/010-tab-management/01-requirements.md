# Requirements and lenses

Application follow-up: [UX acceptance](07-ux-refinement.md) and [visual evidence](08-ux-refinement-evidence.md).

Start with [5 WHY and principles](README.md); see [interaction contract](02-interaction-design.md), [architecture](03-architecture.md) and [test matrix](05-test-matrix.md).

| ID | Contract | Acceptance |
|---|---|---|
| TM-01 | Readable, stable-width single-row tabs; bounded long names; full path tooltip; distinguish duplicate names | Overflow never squeezes all tabs into unreadable slivers; selected and focused states differ |
| TM-02 | Horizontal wheel/trackpad and vertical-wheel translation over the strip, previous/next controls and a scrollbar | No page scroll, honest disabled edges, live hidden count, ctrl-wheel remains browser zoom |
| TM-03 | Reveal selected tab on activation and container resize | Selection fits available viewport; oversized tab uses nearest edge; manual scrolling is not fought |
| TM-04 | Drag reorder with threshold, insertion marker, cancel and edge autoscroll | Commit on valid release only; preserve active ID, editor mount and buffer; cancel outside or on Escape |
| TM-05 | Keyboard and single-pointer reorder alternatives | Alt+Shift+Left/Right and tab menu Move left/right share one pure move function |
| TM-06 | Search all open documents by name and full reference | Open documents button always reachable; selected row marked; empty query/result states; Escape and focus return |
| TM-07 | Predictable closing and recovery | Close active selects right neighbor then left then Home; close inactive preserves selection; middle-click closes; reopen at prior position |
| TM-08 | Accessible identity and focus | Collision-free IDs; one selected document; roving tab stop; Arrow keys/Home/End; Delete; correctly labelled panel; live reorder feedback |
| TM-09 | Preserve drafts and show unsaved state | Reorder never remounts editor; immediate close flushes latest draft; reopen offers existing recovery flow; no implicit workspace save |
| TM-10 | Robust lifecycle and visual consistency | ResizeObserver, event/rAF/timer cleanup, light/dark, reduced motion, narrow viewport, no document-wide overflow |

## Professional lenses

| Lens | Decision and tradeoff | Evidence |
|---|---|---|
| Product owner | Optimize switching and confidence; all requested drag and overflow behaviors are in scope; bound recovery history to 20 | TM-02–07; [validation](06-validation.md) |
| Full stack developer | App owns documents and binding; strip requests ID-based commands; no API needed for ordering | [architecture](03-architecture.md) |
| Database expert | Tab position is transient UI metadata; existing canonical document ID is identity; drafts remain separate local records; Unity Catalog permissions unchanged | [ER model](03-architecture.md#data-model) |
| UX designer | Stable spatial order, discoverable overflow, adjacent close selection, explicit recovery | [navigation](02-interaction-design.md) |
| UI designer | Existing semantic colors and icons; quiet chrome; distinct selected underline, focus outline and drop marker | [wireframes](02-interaction-design.md#wireframes) |
| Frontend designer | Container-only geometry, ResizeObserver, bounded rAF autoscroll, no animation dependency or page scrolling | [implementation](04-implementation-plan.md) |
| Marketing and growth | Promise “Keep your work in reach”; useful feature discovery in tooltips/menu, no unsubstantiated superiority or fabricated conversion metrics | [evidence limits](06-validation.md) |

Release acceptance requires the mapped automated checks and visual review; [06](06-validation.md) records what actually ran. Live Databricks authentication and workspace integration cannot be inferred from local UI tests.
