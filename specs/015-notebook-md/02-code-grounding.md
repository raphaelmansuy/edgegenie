# 02 — Code grounding and reference evidence

[Index](README.md) · From: [five whys](01-five-whys.md) · To: [requirements](03-requirements.md)

## Evidence scope

Baseline `548666c`. `NotebookEditor.tsx`, `Markdown.tsx`, `Viewer.tsx`, the editor host/adapter,
math modules, and notebook domain serializers were read in full. CSS and `EditorSurface.tsx`
were inspected in the cited sections; no claim below describes their uninspected sections.
The workspace adapter was inspected through line 175, and `cellrun.ts` around `spanIds`.
Tests were inspected as named below; this assessment did not execute the proposed product tests.
No business table was queried, and no notebook in a Databricks workspace was changed.

## Screenshot observations

- **S1, rendered cell:** the supplied screenshot shows a large bold Bakehouse title, proportional
  descriptive prose, a blue selected-cell boundary, and code cells below it. It demonstrates visual
  hierarchy, not an exact CSS size or accessibility measurement.
- **S2, editing cell:** the supplied screenshot shows `%md`, Markdown source, a Show preview button,
  formatting controls, a Markdown label, focus/menu/delete actions. It establishes the desired
  distinction between source editing and a rendered resting state.
- The images are references, not instructions. The SQL visible in S1 is not a request to execute SQL.
  Screenshot assets are not copied into the repository; this description remains portable.

## C1

[Markdown.tsx](../../apps/coding-agent/web/src/components/Markdown.tsx), lines 46–66, 87–173:
the shared renderer parses inline code and bold; triple-backtick fences; simple pipe tables;
ATX headings h1–h4; and flat list items emitted as `<ul>` even for numbered source. It joins prose
lines with spaces. There are no branches here for ordinary Markdown links/images, italic,
blockquotes, h5/h6, nested lists, task state, or thematic breaks. Raw HTML is React text, not executed.
An SQL fence can offer Open as query through context; rendering itself does not execute it.

Implications: [MD-04–MD-10](03-requirements.md#requirements),
[dialect](07-rendering-security.md#dialect), [E09–E18](09-edge-cases.md#register).

## C2

[NotebookEditor.tsx](../../apps/coding-agent/web/src/components/NotebookEditor.tsx),
lines 524–567, 582–594, 606–714: local `editing`, the empty-source override in `wantsEdit`,
request-driven mode changes, blur-driven rendering, toolbar controls, and the render/editor branch.
`cell-rendered` edits on double-click. The explicit toolbar currently offers conversion, Ask,
cell links, run controls for code, insertion and deletion, not Markdown formatting/preview.
Lines 278–297 handle Markdown run chords as mode/navigation changes without running code.

Implications: [MD-01–MD-03](03-requirements.md#requirements),
[interaction statechart](06-statecharts.md#interaction-state), [E01–E08](09-edge-cases.md#register).

## C3

[styles.css](../../apps/coding-agent/web/src/styles.css), lines 560–574:
`.answer h1, h2, h3` share 15px typography; tables are fixed-layout, with wrapping cells.
Lines 1824–1898: the notebook has one `.cells` scroller; 46px gutter; a compact cell toolbar;
`.cell-block.is-md` surface; and `.cell-rendered` padding. Lines 817–830 describe a separate `.md`
file preview. Earlier `.cell-markdown` selectors target the legacy read-only viewer's markup.
These are static rules; no runtime contrast or pixel-parity result is claimed.

Implications: [notebook tokens](04-ux-wireframes.md#visual-contract),
[D2](12-decisions-rollout.md#d2), [T03](11-tests-traceability.md#test-groups).

## C4

[Viewer.tsx](../../apps/coding-agent/web/src/components/Viewer.tsx), lines 152–188 and 234–251:
server cells receive client IDs; editability is based on document `truncated`; individual cell
truncation flags are retained. A separate read-only cell branch also uses `Markdown`.
[workspace.py](../../apps/coding-agent/api/adapters/databricks/workspace.py), lines 146–165:
the reader caps exported bytes at 400,000, marks byte truncation, and parses notebook cells.
[notebook.py](../../apps/coding-agent/api/domain/notebook.py), lines 30–31, 88–100, 129–132:
the parser stops at 400 cells and truncates cell sources at 20,000 Python characters.

**Risk inferred from these boundaries:** a notebook below the byte cap can exceed the cell-count
cap without setting document `truncated`. Cell-level truncation can also reach an editable surface.
The plan must reproduce and close these paths before enabling changes; this is not a claim that
a user's notebook has already lost content. See [E26–E28](09-edge-cases.md#register).

## C5

[domain/notebook.ts](../../apps/coding-agent/web/src/domain/notebook.ts), lines 16–25, 37–38,
110–190: cell source/type/language, limits, magic classification, serialization and round-trip checks.
The [Python serializer](../../apps/coding-agent/api/domain/notebook_write.py), lines 67–157,
checks truncation, limits and parse-after-serialize identity; SOURCE spacing is canonicalized,
so arbitrary input byte-for-byte identity is not the existing contract.
[EditorSurface.tsx](../../apps/coding-agent/web/src/components/EditorSurface.tsx), lines 360–431
and 855–887: version/fence/conflict-aware save, and serialization/draft updates when cells change.
The save precheck reparses serialized text; preserving original truncation metadata needs separate tests.

Implications: [data model](05-architecture.md#logical-er-model),
[MD-12/MD-17](03-requirements.md#requirements), [T10/T14](11-tests-traceability.md#test-groups).

## C6

[host.ts](../../apps/coding-agent/web/src/editor/host.ts), lines 19–47:
editor operations include caret/optional selection access, but no formatting transaction contract.
[codemirror.ts](../../apps/coding-agent/web/src/editor/codemirror.ts), lines 139–184 and 200–241:
history/chords, immediate change callbacks, minimal external text changes, selection access and cleanup.
[Editor.tsx](../../apps/coding-agent/web/src/editor/Editor.tsx), lines 58–140:
lazy mount, value synchronization, focus requests, reconfiguration and failure fallback.
The host's prose describes debouncing, but the adapter actually invokes callbacks per document change.
The implementation plan follows behavior, not that comment.

## C7

[Math.tsx](../../apps/coding-agent/web/src/components/Math.tsx), lines 29–35, 48–73:
lazy KaTeX, `trust:false`, `maxSize:12`, explicit `output:"html"`, caught errors.
The MathML comment does not match the selected output option; accessible MathML must be tested.
[math.ts](../../apps/coding-agent/web/src/domain/math.ts), lines 232–265:
private-use markers and numeric indexes are substituted without index validation in `splitStashed`.
With [C1](#c1)'s span dereference, crafted markers can address absent spans. This is a code-inferred
crash path to reproduce in [T05](11-tests-traceability.md#test-groups), not a security exploit report.

## C8

[NotebookEditor.tsx](../../apps/coding-agent/web/src/components/NotebookEditor.tsx), lines 395–471,
calls `spanIds` for above/below availability for each rendered cell.
[cellrun.ts](../../apps/coding-agent/web/src/domain/cellrun.ts), lines 332–348:
`spanIds` builds a run plan then filters runnable IDs with `cells.findIndex`.
This yields a potential cubic notebook-render term when all cells are runnable; see the explicit
cost derivation in [08](08-lenses-performance.md#complexity-analysis). No timings were measured.
[minimap.ts](../../apps/coding-agent/web/src/domain/minimap.ts), lines 74–105, excludes Markdown
from the execution map; a heading outline must remain a distinct navigation concern.

## C9

[viewstate.ts](../../apps/coding-agent/web/src/domain/viewstate.ts) stores geometry per path in
sessionStorage with a memory fallback and a 60-document cap. It does not store preview HTML.
[links.ts](../../apps/coding-agent/web/src/domain/links.ts) builds workspace navigation URLs;
it is not an authenticated image-content resolver and does not match `/Volumes` as a prose path.

Existing tests inspected: [Markdown.test.tsx](../../apps/coding-agent/web/src/components/Markdown.test.tsx),
[Markdown.long.test.tsx](../../apps/coding-agent/web/src/components/Markdown.long.test.tsx), and
[notebook.test.ts](../../apps/coding-agent/web/src/domain/notebook.test.ts), lines 1–105.
The corpus is duplicated in TS/Python tests; the comment's `notebook.corpus.test.ts` is not an actual
file found in this checkout. Do not plan against that nonexistent filename.

## Official references

Checked 14 November 2026. These references describe Databricks, not an OpenGenie parity guarantee.

- [Basic editing](https://docs.databricks.com/aws/en/notebooks/basic-editing): distinguishes code
  and Markdown cells, the + Text action, and rendered Markdown content.
- [Notebook media](https://docs.databricks.com/aws/en/notebooks/notebook-media): documents image
  paths, math, and notebook links; its HTML-output discussion uses `displayHTML`. OpenGenie's
  Markdown HTML policy remains intentionally stricter.
- [Cell organization](https://docs.databricks.com/aws/en/notebooks/notebook-cells): documents a
  heading-based table of contents and collapsible sections. These are distinct from an execution map.
- [remark](https://github.com/remarkjs/remark) and
  [remark-gfm](https://github.com/remarkjs/remark-gfm): support an AST-based implementation candidate
  and GFM extensions. They do not by themselves define OpenGenie's rendering or security policy.
- [KaTeX options](https://katex.org/docs/options.html): distinguishes HTML-only output from
  HTML with MathML and documents expansion/trust controls.

