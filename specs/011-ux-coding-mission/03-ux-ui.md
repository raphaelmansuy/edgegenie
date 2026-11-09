# Mission UX and visual specification

Derived from [product](01-product.md), implemented through [architecture](04-architecture.md), verified by [tests](06-edge-cases-tests.md).

## Screen hierarchy

Desktop: existing navigation at left, a calm mission workspace in the centre and the conversation at right. Mission content uses a constrained readable measure, generous heading space, thin borders, semantic status tints and existing system typography. The overview is information, not a grid of decorative metrics.

```ascii
+------------------+---------------------------------------------------+----------------------+
| Sessions         | Mission / 01                   [Copy link]        | Conversation         |
|                  |                                                   |                      |
| Current session  | [Running]  Agent mission                          | Server status        |
| Other sessions   | Build the revenue notebook                        | Stop / return link   |
|                  | model-a  /  4 tool calls  /  Progress saved       |                      |
| Files            |                                                   | Your request         |
| Catalog          | [Choose mission v]        [Last achieved]         | Agent activity       |
|                  | Overview     Activity                             |                      |
|                  | ------------------------------------------------- | Permission decision  |
|                  | Plan                              1 of 3 complete | when needed          |
|                  | [x] Inspect the source                            |                      |
|                  | [o] Build the notebook                            |                      |
|                  | [ ] Run and verify                                |                      |
|                  |                                                   |                      |
|                  | Outputs                  Evidence                 |                      |
|                  | revenue.ipynb [Open]     2 of 3 verified          |                      |
|                  | Written                  [Inspect source]         |                      |
|                  | ------------------------------------------------- |                      |
|                  | Working folder /Shared/demo                       | [Message the agent]  |
+------------------+---------------------------------------------------+----------------------+
```

Phone or narrow centre: one content column; navigation and assistant remain existing drawers. Composer stays reachable below the independently scrolling mission. Active/recovery actions are supplied by a compact shared RunStatus when no dock is visible; completed missions avoid a duplicate status card. The centre composer stays compact.

```ascii
+--------------------------------------+
| OpenGenie                [Panels]    |
| Mission / 01             [Copy link] |
|                                      |
| [Ready for review]                   |
| Build the revenue notebook           |
| model-a / 4 tool calls               |
| [Choose mission                  v]  |
| Overview     Activity                |
| ------------------------------------ |
| Plan                3 of 3 complete  |
| [x] Inspect [x] Build [x] Verify     |
|                                      |
| Outcome                              |
| The agent's reported summary         |
|                                      |
| Outputs                              |
| revenue.ipynb                 [Open] |
|                                      |
| Evidence             2 of 3 verified |
| Requirement and source disclosure    |
|                                      |
| [Message the agent                 ] |
+--------------------------------------+
```

For completed or stopped missions, the overview leads with the outcome, outputs and evidence; the reported plan follows as a review record. Running missions lead with the live plan. This state-dependent order keeps the next useful action above the fold.

## Navigation

```ascii
+-----------------------------------------------------------------+
| Session rail / return link -> Current mission overview          |
|                                                                 |
| Overview -> Activity tab -> Full selected turn                  |
| Overview -> Choose mission -> Historical mission                |
| Overview -> Last achieved -> Proven completed mission           |
| Historical mission -> Return to current mission                 |
|                                                                 |
| Overview -> Open output -> Document editor                      |
| Document -> Mission overview -> Current mission overview        |
+-----------------------------------------------------------------+
```

Mission selection is ephemeral and session-scoped. Default selection follows the foreground as queued work starts. Explicit history selection remains pinned until Return to current mission. Last achieved uses verified achievement; Last completed remains available when no mission has verified evidence. Copy return link targets the session, whose default is current mission; it does not promise a deep link to a selected historical turn.

## State copy and interactions

- Running: “In progress”; auditing: “Checking work”; completed with valid proof: “Achieved”; completed without proof: “Ready for review”.
- Ready without a mission, waiting, blocked, failed, interrupted, stopped, queued, starting and archived all have explicit text and semantic glyphs.
- Disconnect shows “Updates paused” and last-known state; recovery instructions remain in shared RunStatus. Historical state is never overwritten with the current mission's permission state.
- Overview/Activity use real ARIA tabs, roving focus, ArrowLeft/Right, Home/End. Switching tabs never sends work.
- Full request is disclosed for longer objectives; phone titles are limited to three visible lines, with the complete request available on demand. Outcomes use existing bounded Markdown; very large answers retain plain text fallback.
- Plan progress is an explicit completed/total count; it does not estimate overall mission completion. Unknown status is displayed as reported and is never coerced to completed.
- Evidence disclosure shows requirement, verdict and the exact ToolCard. Missing/mismatched sources get a textual warning. No auto-retry.
- Long paths wrap; titles have constrained measure and wrap; no request or output silently disappears. Large lists use scroll within the mission, not document/body scroll.

## Visual and accessibility contract

Use the existing `--surface`, `--surface-2`, `--ink`, `--ink-2`, `--ink-3`, `--line`, blue/green/yellow/pink semantic ramps, radius and motion tokens. Use the existing SVG icon set. Hierarchy: 26–30px title, 13px body, 11–12px metadata, 4/8px spacing rhythm. No new web fonts or external assets.

The screen is a named region; status announcements are short and atomic, not a live region around streaming Markdown. Keyboard focus has a visible ring. Desktop targets meet the 24px AA minimum; primary phone controls use 44px targets. Color always accompanies text/icon. Honor reduced motion; no animated percentage, confetti or fake elapsed clock. Reflow according to the **centre container width**, because a wide viewport may still have multiple panels open. Inspect screenshots individually using the [visual ledger](e2e/README.md).
