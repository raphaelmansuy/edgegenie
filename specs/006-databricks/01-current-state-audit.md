# 01 · Current-state audit and the Genie Code comparison

[Index](README.md) · prev: [00 Why](00-why-first-principles.md) · next: [02 Requirements](02-requirements.md)

Every claim here is labelled:

- **[measured]** — produced by `web/scripts/dock-audit.mjs` against the deployed app
  `coding-agent-7474654624275247.aws.databricksapps.com` on 8 November 2026. Raw output:
  [`e2e/before/audit.json`](e2e/before/audit.json); screenshots beside it.
- **[verified]** — read in this repository's code, with a line cite.
- **[observed]** — seen in the Databricks screenshots this spec was written from. Visual behaviour
  only; no claim about Databricks internals.

The comparison is deliberately narrow. It is not "Databricks is better"; it is five specific
questions where the answer is checkable.

---

## The five numbers

| # | Question | EdgeGenie today | Genie Code | Verdict |
|---|---|---|---|---|
| N1 | With a document open, is the conversation on screen? | **No, at every width** — 0 turns rendered [measured] | Yes: a docked right pane [observed] | **behind** |
| N2 | Is there somewhere to type while reading a document? | **Yes**, the composer survives (`Ask about …`) [measured] | Yes [observed] | level |
| N3 | Is the model control on screen at 1024 px? | **No** — `display: none` below 1100 px [measured] + [verified] | Not selectable at all in Genie Code [observed] | *ahead, but broken* |
| N4 | px of chrome above the first line of code | **146** [measured] | ~150 [observed] | level |
| N5 | Do the controls in a notebook all work? | **No** — a run button and an in-cell `ask` are inert [verified] | n/a (no cells in the assistant surface) | **behind** |

The two that decide this spec are **N1** and **N3**, and both are the same kind of defect: a control
or a surface that exists in the code but is not available when it is needed.

---

## N1 · The conversation is not on screen when a document is open

**[measured]** At 1600, 1180, 1024 and 760 px, with a real file opened from the Files tree:

```text
transcriptVisibleWithDocOpen   false  false  false  false
turnsRenderedWithDocOpen       0      0      0      0
```

**[verified]** The cause is one variable serving two jobs:

```39:40:apps/coding-agent/web/src/App.tsx
type Rail = "sessions" | "files" | "catalog";
const CHAT = "chat";
```

and then:

```523:530:apps/coding-agent/web/src/App.tsx
            <div id="doc-panel" role="tabpanel" aria-labelledby={`tab-${(view === CHAT ? CHAT : view.replace(/[^\w-]/g, "_"))}`}
              className="doc-panel">
            {viewDoc ? (
              viewDoc.kind === "table"
                ? <TableViewer key={viewDoc.id} doc={viewDoc} actions={viewerActions} />
                : <NotebookViewer key={viewDoc.id} doc={viewDoc} actions={viewerActions} />
            ) : !active ? (
```

`viewDoc` and the transcript are alternatives in one slot. Opening a file is not "show me this
file"; it is "replace the conversation with this file".

**The consequence that matters:** the composer stays visible (N2), so the app invites a question
about the file — and then hides the answer behind a tab. A user who asks "why is this failing?"
while reading a notebook gets an answer they cannot see without leaving the file, and leaving the
file is what loses the answer's subject.

---

## N2 · The composer survives, which sharpens the problem

**[measured]** `composerVisible` is `true` at all four widths with a document open. The placeholder
even names the file: `Ask about <name>…` ([`App.tsx:581`](../../apps/coding-agent/web/src/App.tsx)).

So the app is *already* one decision away from the target interaction. What is missing is not an
input; it is a **surface for the output**.

---

## N3 · The model control disappears below 1100 px

**[measured]**

```text
modelChipVisible   760: false   1024: false   1180: true   1600: true
modelInteractions  760: 1       1024: 1       1180: 1      1600: 1
```

**[verified]** Two separate causes. First, a CSS rule:

```210:213:apps/coding-agent/web/src/styles.css
@media (max-width: 1100px) {
  /* Below this the chip is redundant: the model is in the inspector, the topbar has work to do. */
  .topbar .meta .chip { display: none; }
}
```

The comment states the intent — *the model is in the inspector* — but the inspector only renders
above 1180 px, and below that it is a drawer that starts closed
([`layout.ts:50-52`](../../apps/coding-agent/web/src/domain/layout.ts)). Between 820 and 1100 px,
and at every width below 820 px until the drawer is opened, **the model is on no surface at all**.
`⌘⇧M` still reaches it (hence `modelInteractions: 1`), but a control reachable only by an
undocumented shortcut is not discoverable.

Second, the picker is only rendered when a session exists:

```447:449:apps/coding-agent/web/src/App.tsx
            {active && (
              <ModelPicker
                catalogue={catalogue}
```

Before the first prompt there is no `active`, so the top bar has no model control; the model is
chosen on the empty state ([`Chrome.tsx:194-207`](../../apps/coding-agent/web/src/components/Chrome.tsx)).
That is defensible for the first choice and wrong for the second: after `⌘⇧N` the user is back on
the empty state with no model in the bar.

**Against Genie Code:** Genie Code does not let the user pick a model. On this measure we are
already ahead — *if* the control is visible. The defect is that it is not.

---

## N4 · Chrome above the first line of code: 146 px

**[measured]** `chromePx = 146` at all four widths. This is the payoff from
[003 G1](../003-improve-dev-ux-ui/08-databricks-gap-assessment.md), which measured 234 px before the
document bar replaced three stacked blocks
([`DocumentBar.tsx:1-11`](../../apps/coding-agent/web/src/components/DocumentBar.tsx)).

146 px is the tab strip plus one bar. Databricks spends about 150 px on the same bands [observed].
**This measure needs no work**, and it is recorded so a later change cannot regress it silently:
[12](12-e2e-plan.md) asserts it does not exceed 150.

---

## N5 · Two controls in a notebook do nothing

**[verified]** `NotebookEditor` renders a run button per cell and calls a handler:

```141:144:apps/coding-agent/web/src/components/NotebookEditor.tsx
          <button className="cell-run" aria-label={`Run cell ${index + 1}`} title="Run this cell (⌘↵)"
            onClick={p.onRun}>
            <Send size={12} />
          </button>
```

`EditorSurface` accepts `onAskCell` and forwards it:

```51:51:apps/coding-agent/web/src/components/EditorSurface.tsx
  onAskCell?: (cell: Cell) => void;
```

But `EditorSurface` is never given either handler: `Viewer` is never passed one to pass on, and
`App`'s `viewerActions` sets neither:

```352:359:apps/coding-agent/web/src/App.tsx
  const viewerActions = useMemo(() => ({
    onAsk: ask,
    onAttach: (d: Doc) => addContext(asAttachment(d)),
    editing: {
      folder: session.folder || folder || "",
      sessionId: active,
      theme: theme.effective,
    },
  }), [ask, addContext, session.folder, folder, active, theme.effective]);
```

So `onRun()` and `onAsk()` resolve to `undefined?.()`. Pressing either does nothing, with no message.
The audit reports `cells.run = 0` only because the file it opened was JSON rather than a notebook;
the code is the authority here.

**Why this is worse than a missing feature:** it teaches the user, in the surface where the product
promises "it reads, writes, runs and proves", that the buttons are decorative.

---

## The comparison, as a table a product owner can read

| Dimension | Genie Code [observed] | EdgeGenie [measured]/[verified] | Gap |
|---|---|---|---|
| Assistant placement | Docked right pane beside the file | A tab that replaces the file | **close** |
| Assistant context | Names the file it is about | Infers the open document; `@` searches only home | close |
| Ask from inside the code | Yes (side by side) | Composer visible, answer not | **close** |
| Model choice | Not offered | Offered, grouped, searched, pinned per turn — but hidden < 1100 px | **lead, broken** |
| New chat | Header button in the pane | `⌘⇧N`, and the Sessions rail | level |
| History | History icon in the pane | Sessions rail with relative times | level |
| Attachments | `@` for objects | `@` for objects, but home-only | **behind** |
| Code editing in place | Full notebook, cells, runs, outputs | Cells, editing, save with fence — **no outputs** | **behind** |
| Execution feedback | Cell run with output and timing | None | **behind** |
| Permissions transparency | Not shown | Fence chip + inspector scope, on screen | **lead** |
| Conflict handling | Single writer | A choice, never a verdict | **lead** |
| Keyboard model | Partial | `⌘K`, `⌘B`, `⌘I`, `⌘S`, `⌘/`, `⌘⇧M`, `⌘1..3` | **lead** |
| Survives a reload | Databricks persists notebooks | Sessions are in memory only | **behind** |
| Files browser | Tree **and** list, with owner/updated | Tree only | **behind** |

Four of the five gaps are this spec's scope. The fifth — cell execution with outputs — is named as
out of scope in [README](README.md) and remains the single largest functional gap
([11 D3](11-decisions-risks.md)).

---

## What we already do better, and must not lose

Recorded because a change that fixes the four gaps above could easily delete these:

| Ours | Why it matters |
|---|---|
| **The write fence is on screen before the first keystroke** | Genie Code does not show where the agent may write. Ours does, in the document bar and the inspector. |
| **The model is chosen, pinned per turn, and auditable** | Genie Code has no model choice. The pin is in `model-facts` and shown as "the switch was at turn N". |
| **Every turn keeps the model that answered it** | A switch never retroactively rewrites history. |
| **A conflict is a choice** | `ConflictPanel` offers keep-mine / take-theirs; it never decides. |
| **Evidence, not claims** | The supervisor audits a turn and the transcript shows the audit. |
| **Keyboard-first** | Every panel, tab and action has a key, listed in `⌘/`. |

---

## The gap, in one sentence

> EdgeGenie has the better agent and the worse stage: the parts that make an assistant feel present —
> a conversation that stays beside the work, a model that is always one click away, a file browser
> that answers "which one" as well as "where" — are the parts that are missing or hidden.

---

## How each gap is closed

| Gap | Document | Acceptance measure |
|---|---|---|
| N1 conversation leaves the screen | [04 Assistant dock](04-assistant-dock.md) | `turnsRenderedWithDocOpen ≥ 1` at every width ≥ 820 px |
| N2 answer has nowhere to appear | [04](04-assistant-dock.md) | the dock renders the turn that answers a prompt sent about the open document |
| N3 model hidden below 1100 px | [07 Model selection](07-model-selection.md) | `modelChipVisible: true` at 1600/1180/1024/900/760 |
| N5 two inert controls | [09 P5](09-implementation-plan.md) | no `.cell-run` until an executor exists; `ask` opens the dock bound to the cell |
| Files tree-only, home-only `@`, memory-only sessions | [05](05-data-model-lakebase.md), [09](09-implementation-plan.md) | list view with 4 columns; `@` searches the focused root; a reload keeps the turns |

[Back to the index](README.md)
