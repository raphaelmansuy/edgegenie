# 03 — Product requirements and acceptance

[Index](README.md) · Evidence: [02](02-code-grounding.md) · Design: [04](04-ux-wireframes.md)
· Delivery: [10](10-implementation-plan.md) · Verification: [11](11-tests-traceability.md)

## Scope and priority

**P0 release:** interpreted/styled resting cells, notebook-specific typography, explicit Edit and
Show preview, a bounded CommonMark/GFM dialect, safe links and image placeholders, formatting
transactions, trustworthy math, source-integrity guards, keyboard/focus and performance gates.

**P1 follow-up:** authenticated workspace/volume images and opt-in external images, a derived
heading outline with in-document anchors. P1 still requires the same source, permission and test
contracts. An image remains a labeled placeholder until its resolver is available; no broken icon
or invisible dropped content. Rendering a placeholder interprets image syntax without fetching it.

Outside scope: WYSIWYG/HTML-to-Markdown conversion, arbitrary HTML/iframes, `%md-sandbox`, executable
Mermaid in notebook cells, SQL execution from preview, collaborative CRDT editing, persistent cell
titles not representable in SOURCE, automatic image uploads, and a new database schema.
Section-folding across later code cells is deferred: it changes execution visibility and requires
separate product decisions. Ordinary per-cell collapse is retained.

## Requirements

| ID | Priority | Normative contract | Verification |
|---|---|---|---|
| MD-01 | P0 | Every Markdown cell outside explicit Edit mode displays interpreted, styled content. Empty cells display an Empty Markdown cell state with Edit when writable. A new + Text cell may start in Edit. Collapse hides content, not a source view. | T01, T02, T03 |
| MD-02 | P0 | Render, preview, focus, collapse, links, media and theme changes never mutate source, dirty state, cell kind/language/order, or trigger a save. Preserve semantic cell-source round-trip; do not promise arbitrary SOURCE byte identity. | T01, T10, T14 |
| MD-03 | P0 | Explicit Edit/Show preview actions are reachable by pointer, keyboard and touch. Enter on a command-focused writable cell enters Edit; Esc exits after editor overlays/IME resolve. Selection, links and copy controls never enter Edit. | T01, T02, T09 |
| MD-04 | P0/P1 | Preserve source heading depths 1–6 in AST and visual scale. Map semantic levels using explicit surface context; do not collapse h1/h2 to one level. P1 outline derives from the same AST. | T03, T16 |
| MD-05 | P0 | Define and test paragraphs, emphasis/strong, strike, inline code, ordered/unordered/nested lists, static task lists, blockquotes, hard breaks and thematic rules. Unknown/malformed syntax has a readable fallback and cannot loop. | T04, T19 |
| MD-06 | P0 | Fences preserve code bytes, fence length/type, language and Copy. Math preserves existing accepted delimiters and money/code exclusions, fails locally, and exposes accessible output. Fences never execute code. | T05, T08, T15 |
| MD-07 | P0 | Tables preserve alignment and escaped pipes; long content uses a local horizontal scroller with real table semantics and keyboard access. No page-level horizontal overflow. | T04, T08, T09 |
| MD-08 | P0 | URL handling has a central allow/deny policy for external, workspace, relative and fragment links. Deny active schemes and malformed/obfuscated variants. Link activation never edits a cell or silently performs workspace writes. | T06, T15 |
| MD-09 | P0/P1 | Parse image syntax and show alt text/placeholder in P0. P1 resolves authenticated images as the signed-in user; external requests require explicit Load image. Broken, denied, offline and oversized media retain source and meaningful alternatives. | T07, T15 |
| MD-10 | P0 | HTML/JS/SVG/event-handler content is inert text or a bounded unsupported block. Renderer errors cannot blank the notebook. No arbitrary AST properties become DOM attributes. | T05, T06, T19 |
| MD-11 | P0 | Formatting modifies source through one editor transaction with undo, selection restoration and UTF-16 offsets. Bold, italic, inline code, link, image reference, headings 1–3, list and quote controls have specified behavior. | T02, T09 |
| MD-12 | P0 | Existing document save/version/fence/conflict/draft recovery is the only persistence path. Previewing is not saving. Display dirty/saving/conflict distinctly; unsaved edits survive an external agent update. | T10, T11, T14 |
| MD-13 | P0 | Editable cells and read-only cells use one parser and rendering component with surface options; chat/file adapters remain explicit. No notebook-only CSS changes leak into `.answer` consumers. | T01, T03, T13 |
| MD-14 | P0 | Mode, permission, dirty/save state, render revision, async media and focus are independent state dimensions. Ignore obsolete results after edit, delete, conversion, reorder or navigation. Read-only forbids source mutations, not reading/copying. | T01, T11, T12 |
| MD-15 | P0 | Meet the bounded-cost and latency gates in [08](08-lenses-performance.md#budgets). Avoid repeated notebook-wide parsing, repeated run-plan scans and persistent AST/content caches. | T12, T17, T19 |
| MD-16 | P0 | Agent-written Markdown remains untrusted data. Showing a preview cannot execute tools or elevate privileges. Agent edits use existing reconciliation/conflict UI; do not steal focus/scroll on adoption. | T11, T15 |
| MD-17 | P0 | Partial/truncated/over-limit source is explicitly identified and cannot be destructively saved. Count/character/byte limits are propagated to the document before serialization can discard metadata. | T14, T19 |
| MD-18 | P0 | Heading semantics, control names, toolbar navigation, MathML/alternatives, image alt text, focus visibility, zoom, reduced motion and both themes pass the accessibility contract in [04](04-ux-wireframes.md#accessibility-contract). | T03, T07, T09, T18, T20 |

The authoritative requirement-to-test table is above; test details and phase mapping are in
[11](11-tests-traceability.md#test-groups). Risk-level coverage is [09](09-edge-cases.md#register).

## Acceptance gates

1. Open the Bakehouse fixture with source `# Bakehouse Business Performance & KPI Dashboard`.
   Without editing, its heading and paragraph are interpreted and styled. Syntax delimiters are
   absent from prose; intentional fenced code stays code. This holds in editable and read-only views.
2. Enter Edit, type a final character, immediately select Show preview or Esc. The final character
   is in the preview; source and draft agree. Toggle back: source is unchanged by previewing.
3. Enter a Markdown cell while a code cell is running: no run/cancel request occurs. Source formatting
   is one undoable transaction; a read-only permission change prevents it synchronously.
4. Render the entire [risk corpus](09-edge-cases.md#register): no uncaught page errors, active scripts,
   unexpected network requests, unbounded parsing, silently lost source, or hidden permission denial.
5. Run the [performance and accessibility matrix](11-tests-traceability.md#matrix-and-evidence).
   Feature acceptance requires recorded results; specification validation is not an implementation pass.

