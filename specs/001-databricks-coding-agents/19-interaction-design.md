# 19 · Interaction design: layout, keyboard, navigation

What this document is: the assessment behind the shell's interaction design, what was built, and how
each claim is tested. It answers one question — *is this as fast to use as the best web app of
November 2026?* — with the evidence, not an opinion.

The reference points are the apps that define the current bar: **Raycast** and **Linear** (palette,
shortcut discipline), **Cursor** (an agent inside an editor), **Genie Code** (the same job inside
Databricks), and **Superhuman** (keyboard-first density). None of them is the target individually;
what they share is.

## What the best apps share

| Property | Why it matters | Where this app stands |
|---|---|---|
| **One palette that finds everything** | The mouse is the slow path. Users stop learning the UI once ⌘K works | `⌘K`: sessions, open documents, workspace files, tables, and every action — ranked by fuzzy match |
| **Complete, discoverable shortcuts** | A shortcut nobody can find is a private feature | 16 shortcuts in one registry, a sheet at `⌘/`, every key printed where it is used |
| **Nothing is a dead end** | Every state offers the way out | Empty state, blocked turn, error strip, permission refusal all name the next action |
| **The same key means the same thing** | ⌘W closes, ⌘1/2/3 switch panes, ⌘B toggles, Esc cancels | Enforced by one registry, and by a test that no two shortcuts collide |
| **Panels yield to content** | A three-pane layout on a laptop leaves no room for the work | Both side panels hide (`⌘B`, `⌘I`) and come back from a visible handle |
| **Conventions over cleverness** | Enter sends; Shift+Enter is a newline | Exactly that, with ⌘⏎ still accepted |
| **Fast feedback under load** | A streaming answer must not freeze the tab | Batched events, memoised render, plain text past 4k characters |
| **Accessible by construction** | Keyboard, screen reader, contrast, motion | WAI-ARIA trees and tabs, focus visible, AA contrast, `prefers-reduced-motion`, dark mode |

## What was built in this pass

**The palette (`⌘K`).** One query field over four kinds of thing: actions (new session, panels, quick
actions on the open document), open documents, sessions, and — from the server — workspace files and
Unity Catalog tables. Fuzzy ranking with the rules people feel: exact substring beats scatter, word
boundaries beat mid-word, earlier beats later. Matched characters are highlighted, so the reason for
each result is visible. Arrows move, Enter opens, Escape leaves. Results from the catalog and the
workspace arrive independently, so a fast source is never held back by a slow one.

**The shortcut sheet (`⌘/`).** Every shortcut, grouped, printed as keycaps in this platform's
notation. Reachable from the palette too, so it is findable without knowing it exists.

**Panels that yield.** `⌘B` and `⌘I` hide the side panels; `⌘1/2/3` switch the left panel; both have a
visible control, so the mouse path exists as well. With both hidden the transcript takes the full
width — the layout a laptop actually needs.

**Tabs that behave.** `Ctrl+Tab` / `Ctrl+Shift+Tab` cycle documents, `⌘W` closes the current one (and
never the chat), Arrow/Home/End move within the strip following WAI-ARIA's tab pattern with roving
focus.

**The composer.** Enter sends, Shift+Enter breaks the line — the convention every chat box has
followed for years — with ⌘⏎ still accepted. The primary action sits on the right where people look
for it; tools sit on the left. `/` opens commands, `@` opens context, `↑` recalls history.

**Table search that is instant.** Unity Catalog has no name-search endpoint, so the walk
(catalogs → schemas → tables) runs once per credential, incrementally and eight requests at a time,
started by the first `/api/me` rather than at boot. Names land in the cache as each schema answers,
so a search during the walk finds what has arrived. Measured on the deployed app: 0.9 s for the first
search after page load, 0 ms after that.

**Dark mode.** Full token set behind `prefers-color-scheme: dark`, not an inverted hack: borders,
badges, code, palette and shadow all have dark values.

## Defects this pass found

Each was found by a test or by looking at the app, not by reading the code.

| Defect | How it surfaced | Fix |
|---|---|---|
| `⌘/` did nothing | The e2e asserted the sheet opens; it never did | The registry wrote `mod+slash`, the key press produces `mod+/`. One alias table now maps punctuation, and a test pins it |
| Shortcuts typed into text fields | — | One `isTyping` rule: bare keys are text, modified keys are commands |
| Palette ranked a hash above a verb | e2e: best match for "nb" was a session id | A keyword-only match could beat a real title match. Fixed, and the behaviour is now a unit test |
| Palette showed nothing for a table that existed | e2e against the deployed app | The cold cache was shared and anonymous. Now per credential, and warmed by the user's own first request |
| Palette waited for the slower of two sources | Looking at the screenshot: "Nothing matches" while the request was in flight | Each source fills in as it answers |
| First table search was always empty | Reproduced directly against the adapter | A 6 s budget abandoned the walk; now incremental with polling, so partial results are shown |
| Send sat on the left | Screenshot review | Moved right; tools left |
| Panel collapse existed only as a key | Screenshot review | Visible control on the rail and a handle to bring it back |

## How each claim is verified

Contrast, target size, names, ARIA and OS preferences are covered by the accessibility audit; see
[20 Accessibility](20-accessibility.md) for the standard and its results.

- **Unit** (`web/src/domain/keys.test.ts`): combo parsing per platform, punctuation aliases, display
  formatting, no duplicate shortcuts, typing-vs-command rule, fuzzy ranking and highlighting.
- **Unit** (`web/src/components/Composer.test.tsx`): Enter sends, Shift+Enter does not.
- **End to end** (`web/scripts/ux-e2e.mjs`, passes against the deployed app): palette opens and
  ranks, live table results, shortcut sheet opens from the keyboard, `⌘1/2/3`, `⌘B`, `⌘I`, `⌘L`,
  `⌘W`, arrow keys in the tab strip, Shift+Enter does not send. Screenshots at each state.
- **End to end** (`web/scripts/genie-e2e.mjs`, 19 steps, real agent): the product workflow the keys
  drive.

Run them:

```bash
cd apps/coding-agent/web
npx vitest run                                     # unit
node scripts/ux-e2e.mjs                            # shell and keyboard, local server
APP_URL=<url> BEARER_FILE=<token> node scripts/ux-e2e.mjs   # same, against the deployment
```

## Still below the best

Honest list, in the order a demanding user would notice:

- **No drag-and-drop.** Files cannot be dropped onto the transcript to attach, and tree items cannot
  be dragged into the composer.
- **No multi-select in the tree.** Attaching six notebooks means six `@` picks.
- **No recent-objects section** in the palette beyond sessions: "the table I looked at yesterday"
  is not one keystroke.
- **No `?` overlay on the canvas** listing shortcuts in place (the sheet is a dialog, not contextual).
- **No vim motions** in the composer, and no configurable keymap.
- **Screen-reader testing is manual.** ARIA roles and roving focus are correct by inspection and by
  role-based tests, but no assistive technology was run against the app.
