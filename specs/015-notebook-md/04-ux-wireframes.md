# 04 — UX, UI and ASCII wireframes

[Index](README.md) · Requirements: [03](03-requirements.md) · Transitions: [06](06-statecharts.md)
· Accessibility tests: [11](11-tests-traceability.md)

These are proposed interaction wireframes, not screenshots of implemented OpenGenie behavior.
The supplied images motivate separate author/reader surfaces. Read mode interprets and styles Markdown.

## Reading mode

```ascii
+----------------------------------------------------------------------------+
| Notebook: Bakehouse analysis                [Save] [Outline] [Open in DBX] |
| Cell 1  Markdown                                      [Edit] [Ask] [More]  |
|                                                                            |
| BAKEHOUSE BUSINESS PERFORMANCE & KPI DASHBOARD                             |
| Comprehensive analysis across transactions, franchises and customers.      |
|                                                                            |
| Executive summary                                                          |
| 1. Revenue and transaction context                                         |
| 2. Read assumptions before running code below.                             |
|                                                                            |
| [Copy link]    Select text and follow links without entering Edit.         |
|                                                                            |
| -------------------- + Code   + Text   + Agent --------------------        |
| Cell 2  Python                                            [Run] [More]     |
| kpi_df = spark.sql(...)                                                    |
+----------------------------------------------------------------------------+
```

The title is proportional, prominent and wraps naturally. Prose uses a readable measure inside
the cell; the cell frame and tables may be wider. Edit remains discoverable without hover. The
cell index, Ask, copy link and command selection remain available. Code-cell execution is unchanged.
The mock SQL is a placeholder, not an executable test fixture.

## Editing mode

```ascii
+----------------------------------------------------------------------------+
| Cell 1  Markdown                          [Show preview] [Ask] [More]      |
| [B] [I] [Code] [Link] [Image] [H1] [H2] [H3] [List] [Quote]                |
|                                                                            |
| # Bakehouse Business Performance & KPI Dashboard                           |
| Comprehensive analysis of **key performance indicators**.                  |
|                                                                            |
| Selection stays in the editor while a formatting tool is activated.        |
| Formatting is one undoable source transaction.                             |
|                                                                            |
| Unsaved changes                  Preview does not save this notebook.      |
+----------------------------------------------------------------------------+
```

The Markdown label avoids injecting a synthetic `%md` line into the editor buffer. SOURCE magic
belongs to serialization. If a literal `%md` already exists inside the source, preserve it rather
than silently stripping it. Show preview reads the latest editor text; it does not save.

Controls: Bold, Italic, Inline code, Link, Image reference, H1/H2/H3, List, Quote. Clicking a tool
preserves editor selection. Empty selection inserts a placeholder and selects the editable part.
Headings/lists/quotes operate on complete selected lines; inline wrappers use one contiguous selection.
Multiple selections disable formatting with an explanation. Link/image dialogs have label/alt and
destination fields, validation and Cancel. Inserting a reference does not load media. One Undo reverses
one operation. Toggle only a matching syntax wrapper; never remove arbitrary content to “clean up.”

## Narrow layout

```ascii
+----------------------------------------+
| Cell 1  Markdown                       |
| [Show preview] [More]                  |
| [B] [I] [Code] [Format v]              |
|                                        |
| # Bakehouse Business                   |
|   Performance & KPI Dashboard          |
|                                        |
| Essential actions stay visible.        |
| Extra tools move into Format.          |
| No page-wide horizontal scroll.        |
+----------------------------------------+
```

Use cell-container width: open rails and the assistant can narrow a large desktop. Below a proposed
600px content width, keep Edit/Show preview visible and move extra tools into Format. Verify the
breakpoint against actual controls. At 320px and 200% zoom, controls remain reachable; wide content
scrolls locally. Touch controls target 44 CSS px; desktop controls meet 24px targets with spacing.
44px is a product touch target, not a claim about the WCAG AA minimum.

## Navigation

```ascii
+----------------------------------------------------------------------------+
| NOTEBOOK NAVIGATION                                                        |
|                                                                            |
| [Read] --Edit/Enter--> [Source] --Show preview/Esc--> [Read]               |
|    |                                                  |                    |
|    +----------- Select / Link / Copy -----------------+                    |
|                                                                            |
| [Outline] -> [Heading entry] -> [Scroll to current heading]                |
| [Cell menu] -> [Copy link | Convert | Collapse | Delete]                   |
| [Agent Ask] -> [Conversation] -> [Review incoming changes]                 |
|                                                                            |
| Tab enters current cell/group. Arrows move within the toolbar.             |
| Command mode retains cell navigation and run chords.                       |
+----------------------------------------------------------------------------+
```

P1 Outline lists Markdown headings with indentation by source depth. Derive it from the render AST,
not regexes or a second saved model. A user selection scrolls/focuses the current target heading.
No automatic scroll on background parse, media load or agent update. Preserve a cell-relative scroll
anchor across mode/height changes. The execution minimap continues to describe code execution only.

## Empty, read-only and failure states

A resting empty cell shows **Empty Markdown cell**, not literal `*Empty markdown cell*`. It has Edit
when writable. New + Text intentionally starts in Edit. Read-only uses identical styled reading,
Copy and navigation, with no mutation controls. Collapse shows a summary and Expand, not raw source.

```ascii
+----------------------------------------------------------------------------+
| Cell 1  Markdown                     [Edit if writable] [Copy source]      |
| Preview unavailable: content exceeded the preview budget.                  |
|                                                                            |
| [Bounded source fallback; selectable and locally scrollable]               |
|                                                                            |
| Original source retained. No content was rewritten or saved.               |
|                                                                            |
| Image placeholder: [Quarterly revenue chart]                               |
| [Load image]   External image has not been requested.                      |
| On denial: Image unavailable with your permissions. [Copy reference]       |
+----------------------------------------------------------------------------+
```

Fallbacks are explicitly labeled exceptions confined to a failing block/cell. Preserve source and
Copy if a lazy editor/parser cannot load. Image denial does not reveal privileged fallback content.

## Visual contract

Use semantic app colors/fonts. Introduce a notebook surface profile; do not override all `.answer`
consumers. Proposed tokens below require visual review, not pixel matching from screenshot dimensions.

| Token | Proposed value | Rule |
|---|---|---|
| `--nb-md-body` | 16px / 1.6 | Proportional text outside Edit |
| `--nb-md-h1` | clamp(28px, 3cqi, 40px) / 1.18 | Wrap; never ellipsize the notebook heading |
| `--nb-md-h2` | 26px / 1.25 | Clear section hierarchy |
| `--nb-md-h3` | 22px / 1.3 | Subsection |
| h4 / h5 / h6 | 19px / 17px / 16px | Preserve depth using weight/spacing too |
| `--nb-md-measure` | 88ch maximum | Cap prose, not the whole cell frame |
| Content padding | 20–24px desktop; 12–16px narrow | Align source/preview starts where practical |
| Heading spacing | 1.25em before; 0.5em after | First child has no excess top gap |
| Prose/list spacing | 0.5–0.75em | Nested structure stays readable |
| Code/table/media width | At most cell content width | Local scroll; no page-level overflow |

Provide rem/px fallbacks for container units. Semantic heading level and visual size are separate.
Pastels belong to spec diagrams; product text must retain contrast in both themes. Keep existing
selected-cell/focus indicators and use semantic tokens rather than screenshot-specific colors.

## Accessibility contract

- Named document region and an intentional heading outline; retain source depth in rendered nodes.
- Named Edit/Show preview actions, accurate control state and one polite mode-change announcement.
- A formatting toolbar has one Tab entry plus arrow/Home/End movement and predictable exit. Do not
  add `role=toolbar` without that behavior. Preview links use ordinary keyboard navigation.
- Do not hijack shell shortcuts such as Cmd-I. Scope any new chord to the Markdown editor after
  auditing current bindings. Respect composition, browser keys and assistive technology.
- Normal text contrast at least 4.5:1; large text/meaningful non-text indicators at least 3:1. Focus
  stays visible and unobscured. Meaning and actions must not depend on color, hover or double-click.
- Alt text, table headers and keyboard-scroll access, Copy feedback, and MathML/source alternatives.
  Automated accessibility checks do not replace manual keyboard and screen-reader review.
- Reduced motion disables animation; test 200% zoom and 320px content width. Print uses styled
  content and expands collapsed Markdown for print only, without saving, rewriting or loading images.
  A new PDF export feature is outside scope.

See [E01–E08 and E37–E43](09-edge-cases.md#register), [T09/T18/T20](11-tests-traceability.md#test-groups).

