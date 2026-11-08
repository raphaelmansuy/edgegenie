# 14 · Genie Code against our coding agent: gap analysis and what closed it

[Index](README.md) · prev: [13 UX assessment](13-ux-assessment.md)

The request: *assess Genie Code against Databricks, find what is missing that would bring great value
to our coding agent, write a detailed gap analysis, implement it with the best UX, and prove it with
screenshots that were each looked at, iterating until it is right.*

Screenshots: [`e2e/improve-parity-databricks/`](e2e/improve-parity-databricks/). Scenes:
`web/scripts/parity-e2e.mjs` (notebook, live workspace), `parity-dock-e2e.mjs` (assistant dock),
`parity-widths-e2e.mjs` (1440 dark, 1024, 760).

---

## 0 · Where the evidence comes from

Stated first because a gap analysis is only as good as its sources.

| Tag | Meaning |
|---|---|
| **[observed]** | visible in the two screenshots of the user's own workspace on 8 Nov 2026 (the workspace browser and a new notebook with the Genie Code panel open) |
| **[known]** | what I know of Databricks' Genie Code from its documentation and product; **not re-verified in this session**, and the product changes quickly. Treat each as "believed", and correct me where it is stale |

Nothing below claims to have driven Genie Code itself. The comparison is made from what the screenshots
show and from what is documented, against our app, which I did drive.

---

## 1 · What Genie Code shows [observed]

From the notebook screenshot (a new notebook, Genie Code panel open on the right):

| # | Where | What is on screen |
|---|---|---|
| O1 | cell | placeholder **"Start typing or generate with AI (⌘ + I)"**: the AI is reachable *from the cell*, by keyboard |
| O2 | cell toolbar | run (split button), language tag, delete, **a Genie sparkle**, full-screen, overflow menu |
| O3 | between cells | **`+ Code   + Text   ✦ Genie Code`**: add a cell, or have the agent write one, in the gap |
| O4 | notebook bar | **Run all**, a compute selector (*Serverless*), Schedule, Comments, Share, "Last edit was now", language and view toggles |
| O5 | panel header | title ("New chat"), **new chat / open in tab, history, overflow menu, close** |
| O6 | panel, empty | brand mark, one-line promise ("Run multi-step data and AI tasks"), **three starter chips** (one with a menu), a dismissible **"Connect your tools"** card (connectors) |
| O7 | composer | hint **"@ for objects, / for commands, ↑↓ for history"**, and the trust line "Only use the agent with code and data you trust" |
| O8 | workspace tree | a **`.assistant`** folder in the user's home: where instructions and skills live [known] |

And from the workspace screenshot: Genie Code is reached from the left rail and from every object; there
is a **Genie agent** object type next to folders and notebooks.

---

## 2 · The gap analysis

Scored on **value to a person using the agent** (H/M/L) and **cost** (S/M/L). *Before* is our app at the
start of this round, measured on the live workspace (see
[`00-baseline-run.png`](e2e/improve-parity-databricks/00-baseline-run.png)).

### 2.1 In the notebook

| ID | Genie Code | Ours before | Value | Cost | Status |
|---|---|---|---|---|---|
| G1 | **Ask AI from the cell, by keyboard** (O1, O2) | an `ask` word that *moved focus to the dock*; no keyboard path; no place to type on the cell | **H** | M | **done**: `⌘I` (or **Ask**) opens a prompt on the cell with four one-click actions |
| G2 | **Generate a cell in the gap** (O3) | one `+` per cell, code only; a "code / markdown" pair at the very end | **H** | M | **done**: a seam between every pair of cells (`+ Code`, `+ Text`, `✦ Generate`) |
| G3 | **Run all** + compute indicator (O4) | none: nine clicks to run nine cells | **H** | M | **done**: runs SQL cells in order, stops at the first failure, says what it will skip and why, names the warehouse |
| G4 | **Fix an error in one click** [known] | a red box; the user retyped the error into the chat | **H** | S | **done**: **Fix with agent** on a failed cell sends the engine's own words bound to that cell |
| G5 | Run Python on a cluster / pick compute (O4) | refused with a reason | H | **L** | **not done**, see §4 |
| G6 | Schedule, Comments, Share (O4) | none | M | L | not done: workspace features, see §4 |
| G7 | Inline completion (ghost text) [known] | none | M | L | not done: needs a low-latency completion path the agent protocol does not have |

### 2.2 In the panel

| ID | Genie Code | Ours before | Value | Cost | Status |
|---|---|---|---|---|---|
| G8 | **History** from the panel header (O5) | history existed only in the left rail, which is hidden at 760 px and when you work in the panel | **H** | S | **done**: a clock opens the same list (search, day groups, delete) in a popover |
| G9 | **Panel menu** (O5) | `+` and hide only | M | S | **done**: copy conversation, download as Markdown, new conversation |
| G10 | Take the conversation with you [known] | none | M | S | **done** (G9), tested for what it keeps and what it drops |
| G11 | **Next-step suggestions** after an answer [known] | the answer ended; the user stared at a cursor | **H** | S | **done**: up to three chips, derived from what the turn did |
| G12 | **`/` commands**, discoverable (O7) | the menu opened only after a letter was typed, and only the first match could be chosen | M | S | **done**: bare `/` lists all 12, arrows select; added `/optimize /prettify /rename /findtables /test` |
| G13 | Connectors ("Connect your tools", O6) | none | **H** | **L** | **not done**, see §4 |
| G14 | **Instructions and skills** (`.assistant`, O8) | none: every conversation starts from nothing | **H** | M | **not done**, designed in §4 |
| G15 | Rename a conversation, open it in a tab | titles come from the first prompt | L | S | not done |
| G16 | Thumbs up / down | none | L | S | not done: nowhere to send it |

### 2.3 Bugs the work exposed (not on anyone's list)

Every one was found by looking at a screenshot or by writing the test for the feature, not by the
audit that already existed.

| ID | Defect | Found by | Fixed |
|---|---|---|---|
| B1 | A cell never knew it was focused: `onFocus` was passed to every cell and **attached to nothing**, so the `is-focused` style (and anything keyed off "the current cell") was dead code | `⌘I` did nothing in the first run | wired on the cell section; the focus ring now actually shows |
| B2 | **The dock did not follow a long answer.** "Stay at the bottom if you are near it" was measured *after* the content had grown, so any update larger than the threshold read as "scrolled away" and a long turn was never followed; the answer and the new chips were below the fold | the follow-ups screenshot showed the top of the turn | pinned state is remembered from the last scroll event; programmatic scrolls are instant |
| B3 | At 760 px, choosing a notebook in the navigator drawer **left the drawer open, covering the notebook** | the 760 scene could not click a cell | the drawer is a chooser: choosing closes it |
| B4 | Quick-action buttons carried `role="listitem"`, which removes their button semantics for assistive technology | the component test | plain buttons in a labelled group |
| B5 | The message sent from a cell showed my scaffolding as the user's own words ("About cell 3 of the attached notebook … Leave every other cell exactly as it is") | the sent-message screenshot | prompts shortened to what the user said plus one constraint |
| B6 | The `/` button inserted `/` and nothing appeared | the slash scene | see G12 |
| B7 | On a long notebook the document bar and **Run all** scrolled away with the first cell (the whole editor surface scrolled, not the cells) | screenshots 03/05 | `.viewer-body.is-editing` is now a non-scrolling flex column; only `.cells` scrolls. The e2e asserts Run all and the bar stay in view |

---

## 3 · How it was built

Pure decisions in `domain/`, rendering in components, every rule with a test.

| Piece | File | Tests |
|---|---|---|
| What a cell-level request says (edit, insert, fix; clip long errors; always say what must not change) | `domain/cellprompt.ts` | `cellprompt.test.ts` |
| What to offer after an answer (true of this turn, nothing after a blocked turn) | `domain/followups.ts` | `followups.test.ts` |
| A conversation as Markdown, and a safe file name | `domain/transcript.ts` | `transcript.test.ts` |
| What Run all will do, and the sentence that says so | `domain/cellrun.ts` (`runPlan`, `runAllLabel`) | `cellrun.test.ts` |
| Inline prompt, seam, notebook bar, dock tools | `CellPrompt`, `CellInsert`, `NotebookBar`, `DockTools` | `CellPrompt.test.tsx` |

Design decisions worth keeping:

- **One conversation, one transcript.** The inline prompt is a faster way *in*, not a second chat: it
  binds the message to the cell and opens the dock, so Stop, approvals and the audit trail live in one
  place. A cell binding supersedes its notebook (`attachmentsFor`), so the context is sent once.
- **Every cell prompt says what must stay unchanged.** An instruction scoped to one cell that does not
  say so invites a rewrite of the notebook.
- **A failed cell quotes the engine.** The agent starts from the cause, not from "it didn't work".
- **Run all stops at the first failure.** Later cells often read what earlier ones made; a second error
  is noise. It says which cells it will skip *before* it starts.
- **Follow-ups are derived, not canned.** "Run it" is offered only if a notebook was written and not
  run. A fixed menu is marketing; a derived one is help.
- **Nothing is offered that cannot act.** No cluster picker (SQL runs on a serverless warehouse and the
  bar names it); Run all is disabled with a reason when no cell can run.

---

## 4 · What is still behind, and why

| Gap | Why it is open | The next step |
|---|---|---|
| **G14 instructions and skills** | The highest-value remaining item. It needs the server to read `<home>/.assistant/instructions.md` as the signed-in user and inject it as *user-authored* context, and a decision about the fence (the file is outside the working folder, so editing it from the app is a write that must ask). I would rather specify that properly than ship a browser-local substitute that looks the same and is not shared | spec the read path, the edit path and the injection label; then build |
| **G13 connectors** | Needs an MCP client in the app server and a credential model for each connector. Security design first | separate spec |
| **G5 Python cells, compute picker, G6 schedule/comments/share** | They are the workspace's features. Running arbitrary code on the app's own compute would be a hole, and a picker for a choice the app does not offer would be a lie. See [13](13-ux-assessment.md) | none planned |
| **Agent edits as an inline accept / reject diff** | `domain/diff.ts` exists but the notebook does not draw a proposal over a cell. This is the largest remaining notebook gap | next after G14 |
| **G7 inline completion** | No low-latency completion path in the agent protocol | needs a model route, not UI |
| **G15, G16** | Small, but each needs a server field | batch with the next server change |

---

## 5 · Evidence

Every picture below was opened and looked at; the assertion that goes with it ran before it was taken.

| Screenshot | What it shows | Asserted before the picture |
|---|---|---|
| [`00-baseline-run.png`](e2e/improve-parity-databricks/00-baseline-run.png) | the starting point: no Run all, `ask` / `run` as small words, a red error with no action | n/a (baseline) |
| [`01-notebook-toolbar.png`](e2e/improve-parity-databricks/01-notebook-toolbar.png) | Run all, "3 cells can run", compute chip, **Ask** and **Run** with icons on every cell | Run all visible; every cell has Ask and Run |
| [`02-insert-seam.png`](e2e/improve-parity-databricks/02-insert-seam.png) | the pill floating in the gap: `+ Code  + Text  ✦ Generate` | all three buttons visible on hover |
| [`03-run-all-failed.png`](e2e/improve-parity-databricks/03-run-all-failed.png) | three cells ran in order, the third failed, the bar says "2 ran · 1 failed", **Fix with agent** | states are `succeeded,succeeded,failed`; label; warehouse named |
| [`04-cell-prompt.png`](e2e/improve-parity-databricks/04-cell-prompt.png) | `⌘I` on cell 3: the prompt, focused, with Explain / Fix / Optimise / Comment | prompt focused; placeholder names cell 3; five chips |
| [`05-prompt-sent.png`](e2e/improve-parity-databricks/05-prompt-sent.png) | the message that was sent, bound to **parity_demo · cell 3** | dock chip says cell 3; message carries "Change only cell 3" |
| [`06-follow-ups.png`](e2e/improve-parity-databricks/06-follow-ups.png) | the dock followed the stream to the answer; three derived next steps | 1–3 chips; visible after the turn |
| [`07-fix-with-agent.png`](e2e/improve-parity-databricks/07-fix-with-agent.png) | the engine's error sent with cell 4 | message contains the error code; dock bound to cell 4 |
| [`08-generate-cell.png`](e2e/improve-parity-databricks/08-generate-cell.png) | a generate prompt in the gap after cell 1 | placeholder says "after cell 1"; Escape closes it unsent |
| [`09-dock-history.png`](e2e/improve-parity-databricks/09-dock-history.png) | history popover: search, day group, active row | rows and headings; popover inside the window |
| [`10-conversation-menu.png`](e2e/improve-parity-databricks/10-conversation-menu.png) | copy / download / new | items enabled; the downloaded file is `.md`, has question and answer, no plumbing |
| [`11-slash-commands.png`](e2e/improve-parity-databricks/11-slash-commands.png) | a bare `/` lists the commands, arrows move | ≥10 commands; selection moved |
| [`12-dark-cell-prompt.png`](e2e/improve-parity-databricks/12-dark-cell-prompt.png), [`13-w1024-…`](e2e/improve-parity-databricks/13-w1024-cell-prompt.png), [`14-w760-…`](e2e/improve-parity-databricks/14-w760-cell-prompt.png) | the same controls dark, at 1024 and at 760 | no horizontal overflow; toolbar fits its row; prompt inside the window |

### Two things the pictures cannot tell you

- **The turn in 05 / 07 / 08 ends `blocked`.** That is correct, not a defect: with a real workspace token
  the audit checks the fake agent's hard-coded paths against the real workspace and refuses what it
  cannot verify. The follow-up scene therefore runs against the fake agent *without* a token, where the
  turn completes. The cell scenes run on the live workspace so that cells really execute.
- **I changed your workspace once:** the scenes need a notebook with a failing cell, so I created
  `agent_scratch/parity_demo` (SQL) in the app's own scratch folder. Delete it when you are done.

---

## 6 · Re-running

```bash
cd apps/coding-agent
scripts/dev-token.sh 8062 &                       # real workspace token, fake agent
APP_AGENT_MODE=fake python -m uvicorn api.main:app --port 8071 &   # no token: turns complete
cd web
APP_URL=http://127.0.0.1:8062 node scripts/parity-e2e.mjs
APP_URL=http://127.0.0.1:8062 node scripts/parity-widths-e2e.mjs
APP_URL=http://127.0.0.1:8071 node scripts/parity-dock-e2e.mjs
```
