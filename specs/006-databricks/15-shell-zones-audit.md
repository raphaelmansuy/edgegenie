# 15 · Shell and zones audit — the coding-session journey

Trigger: a user opened a notebook, typed "Update this notebook…" in the notebook's own composer, and
saw nothing: no thread, no progress, no sign a session existed. Then, on the deployed app, the agent
said it had added a cell and the open notebook still showed the old cells.

Method: drive the journey the way a person does (deep link → ask from the document → watch → read the
result), at 800, 1100 and 1440 px, on the deployed app with Gemini 3.8 flash, and look at each frame.

## The zones, and what each is for

| Zone | Job in a coding session | Databricks | Here, before | Here, now |
|---|---|---|---|---|
| Top bar | Where am I, is anything running, what do I need to do next | Static toolbar; Assistant button | Status pill with a word ("ready") and no action | **Session chip**: working / needs you / stopped / ready; one click shows the conversation (or focuses the composer) |
| Navigator (rail) | Find things; find past sessions | Workspace tree | Sessions / Files / Catalog | unchanged (the current session is highlighted in Sessions) |
| Centre: document | The work | Notebook | Notebook, stale after an agent write | Adopts outside changes, marks changed cells, **Undo** |
| Centre: nothing open | Say where the work is | Empty workspace | "What should we build today?" even while a session ran | **Session home**: title, what was written / read, Open buttons |
| Centre composer | Ask about this document | Cell-level Ask | Cleared on send; conversation invisible below 1136 px | **Opens the conversation** on send; a **status strip** stays above the composer when it is closed |
| Assistant dock | The conversation, approvals, Stop | Right panel | Column ≥ 1136 px, hidden drawer below | unchanged, but now revealed by every path that sends |
| Inspector | Facts (tools, model, tokens) | none | Facts on demand | unchanged |

## Findings fixed

1. **Conversation invisible** below 1136 px (and whenever the dock was hidden): `message()` and the
   "Ask" menu never revealed the drawer (only the per-cell prompt did). → `reveal()`, called by every
   send from a document; `SessionPeek` strip + top-bar chip for when it is closed.
2. **Open notebook never reflected an agent write** (and the Reload button did nothing visible). The
   editor seeded its cells once; a later load only changed a prop it ignored. A latent clear-on-mount
   had been hidden by a stale first `source`. → the editor adopts a changed server version, says which
   cells changed (`diffCells`), marks them, and offers Undo. With unsaved edits it asks instead.
3. **Save race**: marking the buffer clean when a slow save returned, over newer keystrokes. → only
   clean if the text is still what was saved.
4. **Draft banner contradicted the conflict banner** while the user was mid-edit. → suppressed.
5. **First-run screen while a session ran** → Session home.

## Round 2 — grey conversation, live files

6. **Grey when the conversation opens.** A drawer scrim dimmed the notebook the user was asking
   about. → No dimming for the assistant. Between 860 and 1136 px the opened assistant now takes a
   **column** (focus layout, `DOCK_FOCUS_MIN`) and the navigator yields to a drawer on demand, so the
   notebook is beside the conversation, never under it. Below 860 px it stays an overlay.
7. **Open files follow the workspace, three layers** (no single signal is trusted):
   instant (a completed write tool names the path; a SQL write refreshes an open table) →
   `useFresh` version check (`GET /api/workspace/version`, one `get-status`) every 2.5 s while the
   agent works, 0.7 s after a turn ends, and on window focus → the editor adopts the change, marks
   cells, offers Undo, and asks instead of overwriting unsaved edits.
   Verified live: the new cell appears while the chip still says "working".

## Still open (ranked)

- LaTeX in markdown cells renders raw (`$\pi$`); Databricks renders it.
- Per-cell Python timing shows the job time on every cell.
- "Review changes" as a real per-hunk diff (Genie Code shows one before applying); today it is
  mark + Undo after the fact.
- Sessions tab does not badge a running session when another tab is selected (the top-bar chip does).

## Evidence

`web/scripts/session-journey-e2e.mjs` (800, 1100), `external-update-e2e.mjs`,
`deployed-update-e2e.mjs`; screenshots in `e2e/session-journey` and `e2e/update-open-notebook`.

## Round 3 — the user's hands (caret, scroll, keyboard, mouse)

Assessment (measured with `web/scripts/cursor-probe.mjs`): an outside write remounted every cell
(new ids), so caret, focus and scroll were lost; an adoption called `scrollIntoView(smooth)` and
fought the wheel; `setValue` replaced the whole document (caret to 0); buttons stole the caret from the
editor; only Esc/⌘S/⌘I were bound; new cells were not focused; a click on rendered markdown started
editing; the document itself scrolled ~100 px because of a stray `sr-only` node, sliding the top bar away.

Fixes: `domain/reconcile.ts` (identity-preserving reload), minimal-diff `setValue`, no programmatic scroll
on data updates (banner **Show** is the only way), `domain/viewstate.ts` (cell, caret, scroll per document,
survives tab switch and reload), `domain/cellkeys.ts` (Databricks edit/command modes: Shift/⌘/Alt+Enter,
Esc, ↑↓/j/k, a/b, d d, m/y, z, Alt+↑↓), buttons never take the caret, double-click edits markdown,
`html, body { overflow: clip }`. Verified by `keyboard-scroll-e2e.mjs` (local) and
`deployed-scroll-e2e.mjs` (deployed, real agent): screenshots in `e2e/keyboard-scroll/`.

Open: a save with no session still asks for approval (by design of the fence); the approval is not yet
remembered per path.

## Round 4 — the identity, the home screen, and the write fence as a tree

Two complaints drove this round, and the first one was not a refresh bug at all.

**"The agent updated a file but I don't see it refreshed."** Traced on the deployed app, from the
session's own event stream. The open notebook was `/Repos/.../demo/display_unity_catalog_tables`; the
agent, correctly, may not write into a repo, so it wrote `agent_scratch/display_unity_catalog_tables_with_kpi`
and said so in the dock. Nothing on the centre changed, and nothing said why — which reads exactly like a
broken refresh. Fixes:
- `domain/docs.ts` `canonicalPath`: `/Workspace/Users/…` and `/Users/…` are one object. They used to open
  **two tabs**, and a write reported under one spelling never refreshed a tab opened with the other.
- `domain/artifacts.ts` `wroteElsewhere` + `WroteElsewhere` banner: when the last writing turn wrote
  files and none is the open one, the centre names the file, says the open one is outside the fence, and
  offers **Open it**. The baseline is taken when a document is opened, so history is not replayed as news.
- Plain files now adopt outside changes too (`EditorSurface.adoptFile`), with the same rules as a
  notebook: never over unsaved edits, and our own save's echo is not an adoption.
- A restored draft no longer pins the editor through `forceValue` for the rest of its life.

**Home screen, working folder, identity.** The first screen asked for the write fence by typing an
absolute path into a text box, and showed no way in. Now:
- `components/FolderPicker.tsx`: the working folder is a **tree** in a popover — lazily loaded, the
  current folder expanded and scrolled to, search by name, "Use" on the row, and a "Type a path…"
  fallback for somewhere the tree cannot reach.
- `components/Chrome.tsx` `EmptyState`: fence first (it is the product's promise), then the model, then
  the six start cards, then a way IN (search, catalog, recent documents from `domain/recent.ts`), then
  what this workspace is. Verified at 1440/1100/800 px with no horizontal overflow.
- **OpenGenie**: `components/Logo.tsx` — an open ring with a spark in the gap (Open + Genie), as a
  stroke glyph and as a tile; wordmark "Open" in ink, "Genie" in the accent; favicon, tab title, server
  title, the agent's avatar in the transcript, the dock header and the session strip all carry it.
- A demo regression found while testing: `[[scenario:…]]` was stripped from the prompt *before* the
  reference agent saw it, so every start card played the same behaviour. It now travels in `context`
  (sent, never shown, never stored as the user's words).

Evidence: `web/scripts/home-e2e.mjs`, `refresh-e2e.mjs`, `deployed-home-e2e.mjs`;
screenshots in `e2e/home` and `e2e/refresh`.
