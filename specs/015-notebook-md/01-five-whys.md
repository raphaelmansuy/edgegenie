# 01 — Five whys and first principles

[Index](README.md) · Next: [evidence](02-code-grounding.md) · Decisions: [12](12-decisions-rollout.md)

## Five whys

These are a problem decomposition grounded in the inspected implementation, not a measured user
research study. The screenshots establish a reference interaction; they do not establish why an
OpenGenie user behaves a particular way.

1. **Why improve Markdown cells?** A notebook is read as an explanation interleaved with executable
   work. Outside editing mode, the user expects interpreted, styled content, not Markdown syntax.
   This is the explicit user rule, made testable by [MD-01](03-requirements.md#requirements).
2. **Why is the current resting presentation insufficient?** The editor renders through the shared
   `Markdown` component, whose `.answer` rules give h1/h2/h3 the same 15px size. The parser maps
   source h1 and h2 to the same HTML level and does not parse ordinary italic/link/image syntax
   ([C1](02-code-grounding.md#c1), [C3](02-code-grounding.md#c3)). Document structure loses visible meaning.
3. **Why can a user struggle to control reading versus editing?** `CellBlock` owns an implicit editing
   boolean; nonempty content renders, double-click enters source, blur can render again. The toolbar
   has no explicit Edit/Preview control or formatting tools. Empty Markdown takes the editor branch
   regardless of that boolean ([C2](02-code-grounding.md#c2)).
4. **Why would a CSS-only fix leave important failures?** A visual heading scale cannot make ordered
   lists ordered, preserve nested syntax, prevent toolbar blur races, safely resolve images, or prove
   save integrity. Those are grammar, state, policy, and persistence responsibilities
   ([architecture](05-architecture.md), [risks](09-edge-cases.md)).
5. **Why specify boundaries before adding features?** The renderer also serves chat and file previews;
   the notebook has existing save fences and SOURCE serialization. An isolated rich-text editor or
   another parser would duplicate behavior and risk data loss. A shared parser with explicit surface
   policies and a notebook-specific interaction layer is the smallest coherent extension
   ([decision D1](12-decisions-rollout.md#d1)).

## First principles

| Principle | Consequence | Contract |
|---|---|---|
| Source is the durable truth | Previewing, focusing, collapsing, or loading media never rewrites source | MD-02, MD-12 |
| Presentation is derived | Render from the latest cell source; never save an HTML preview or AST | MD-01, MD-13 |
| Mode and focus are different facts | A toolbar click, text selection, or external link must not accidentally change mode | MD-03, MD-14 |
| Structure has meaning | Preserve heading levels, ordered-list start, nested blocks, table alignment, alt text | MD-04–MD-09 |
| Untrusted text remains data | Model text cannot execute HTML, SQL, scripts, tools, or background requests | MD-08, MD-10, MD-16 |
| A preview is not a save | Show rendering state separately from dirty/saving/conflict state | MD-12, MD-14 |
| Work must scale with changed content | Parse one changed cell, reuse unchanged results, precompute notebook metadata once | MD-15 |
| Unsupported is preferable to destructive | Show a bounded, labeled fallback without dropping source | MD-10, MD-17 |

## Desired outcome

A reader sees the screenshot's hierarchy: a substantial notebook heading, clear prose, and quiet
cell chrome. An author chooses Edit, changes Markdown using source or formatting controls, then
chooses Show preview. The preview interprets that latest text without a backend call or execution.
Saving remains the document's existing explicit version-checked operation.

Success is defined by [acceptance gates](03-requirements.md#acceptance-gates),
not by pixel imitation of Databricks. The proposed [wireframes](04-ux-wireframes.md) preserve
OpenGenie's shell, code execution, and agent workflows.

