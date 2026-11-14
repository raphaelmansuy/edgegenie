# 12 — Decisions, open implementation evidence and rollout

[Index](README.md) · Grounding: [02](02-code-grounding.md) · Scope: [03](03-requirements.md)
· Implementation: [10](10-implementation-plan.md) · Tests: [11](11-tests-traceability.md)

## D1

**One source grammar/model, surface-specific rendering policy.** Adopt an AST-based adapter rather
than extending the regex renderer indefinitely or adding a separate WYSIWYG store. The candidate
is `remark-parse` with selected GFM/math integration; phase P0 must prove browser compatibility,
bounded behavior and bundle cost before locking dependencies. Reject a candidate that needs raw
HTML execution, discards source positions or cannot meet the [budgets](08-lenses-performance.md#budgets).
Keep existing `Markdown` callers behind one compatibility adapter; no permanent dual parser.

## D2

**Notebook is a document, chat is a conversation.** Shared grammar/components do not require identical
typography. Notebook headings follow source visual depth; notebook semantic heading context is
explicit. Chat/file profiles are migrated only with their own tests. Do not treat the existing
flattened `.answer` heading style or “only one h1” comment as a universal accessibility rule.

## D3

**Reading is the resting mode.** The user's explicit instruction controls [MD-01](03-requirements.md#requirements).
Edit is entered intentionally; preview interprets source without writing it. Empty cells render a
styled placeholder; newly inserted writable text cells may intentionally begin in Edit. A render
failure has a labeled source fallback, not an invisible loss or a blanket source-only mode.

## D4

**SOURCE and existing write fences remain authoritative.** No new database schema, browser HTML
serializer or auto-save-on-preview. Partial source is unsafe to save, including per-cell/count
truncation below the document byte cap. Resolve the integrity gaps before releasing rendering changes.
Round-trip semantics are the guarantee; arbitrary hand-written SOURCE byte equality is not.

## D5

**Images are capabilities, not incidental parser behavior.** P0 renders image placeholders and
reference syntax. P1 authenticated loading and external opt-in have independent privacy/permission
gates. No arbitrary URL proxy, SVG execution, automatic upload, credential forwarding or alternate
principal on denial. A platform limitation keeps the placeholder; it does not weaken the trust model.

## D6

**Reuse editor state, not hidden editor fleets.** Formatting is one source transaction. Preview
preserves history/selection via a bounded editor-state capability. The phase P3 spike chooses whether
to retain the active host temporarily or remount with its state snapshot; acceptance is identical.
No allocation of a live CodeMirror instance for every rendered Markdown cell merely to retain Undo.

## Implementation evidence still required

| Question | Owner lens | Required evidence and default |
|---|---|---|
| Which AST adapter meets costs and extension behavior? | Full stack / O(n) | P0 corpus, bundle and scaling report; no dependency version guessed in this spec |
| How is editor history retained across preview? | Full stack / UX | P3 real editor transaction/Undo tests; source cannot be reset to emulate history |
| Can volume/workspace media enforce byte/pixel limits under caller identity? | System / database | P5 endpoint/CSP review and denied-read tests; placeholder until proven |
| How do deep semantic headings work with target screen readers? | UX/UI | P6 manual heading navigation; adjust semantics without flattening visual hierarchy |
| Does the current draft identity scope need migration? | Database / system | P1 scope audit; never automatically recover path-only content across identities |
| Which rendering stage exceeds latency/memory budgets? | O(n) | P4 measured samples; constrain or isolate work rather than assert unproven O(n) |

These are implementation validation tasks, not missing user choices blocking specification delivery.

## Release and rollback

1. Merge source-integrity guards and regression tests first. Review affected APIs for additive
   compatibility. No new migrations, privileges or business-data reads are part of this UI feature.
2. Introduce a scoped notebook-rendering capability using existing configuration conventions after
   inspecting them. Do not invent a second settings store. Keep P1 media/outline separately gated.
3. Validate local production build against [T01–T20](11-tests-traceability.md#test-groups), including
   the user rule in both editable and read-only notebook surfaces. Stage enabled capabilities only.
4. Deploy through the established repository workflow when implementation deployment is authorized.
   Confirm deployment success **and** app-running state, then inspect the served bundle/version and
   styled-reading interaction. Build success alone is insufficient. Permission/config changes require
   their own authorization; the design works with placeholders under existing permissions.
5. Observe redacted renderer-fallback counts, mode latency, blocked unsafe URLs and cache/task counts.
   Do not log notebook source, formulas, asset URLs with secrets or personal data for telemetry.
6. Roll back the notebook renderer/profile capability if page errors, unsafe navigation, lost source,
   focus theft or cost regressions appear. Keep source-integrity fixes and existing save fences.
   Rollback does not write notebook documents or migrate HTML back into Markdown.

P0 release is complete only when styled reading is default and its safety/interaction gates pass.
P1 completion is separate and requires its own enabled-feature evidence. The artifacts in this
directory specify the work; they do not authorize a new runtime deployment by themselves.

