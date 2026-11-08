# 02 — Measured assessment

Part of [007](README.md). Method and raw output: `web/scripts/shell-audit.mjs`,
`shell-audit2.mjs`, `shell-audit3.mjs`, and the probes quoted below. Everything here was observed on
`scripts/dev-token.sh 8062` at 1440×900 unless stated; nothing is inferred from reading code alone.

---

## A. Zones — the geometry is right, the *reachability* is not

Measured on the home screen at 1440 px (`.pane`, bounding boxes):

```
topbar    1440 × 52     y 0
rail       276 × 848    x 0
centre     782 × 848    x 277
dock       380 × 848    x 1060
inspector  (hidden: no room for four columns at 1440 with the dock open)
body scroll 1440 × 900  — the page itself never scrolls (overflow: clip)   ✔
```

That matches `layout.ts` exactly (`ASSISTANT_COLUMN_MIN = 1136`, `ALL_FOUR_MIN = 1476`), and the
prior audit's round 2. **No geometry defect.** What is wrong is what a keyboard user can reach:

| Finding | Evidence |
|---|---|
| **No skip link** | The first Tab lands on `button.chip` (the model). Reaching the code editor takes **40** Tabs. Reaching the composer takes more. |
| **The dock is not a landmark in the Tab order that helps** | `<aside aria-label="Assistant">` is present (good), but there is no Landmark shortcut support by design — a skip link is how a browser exposes that. |
| **`⌘I` does not open the inspector** | With a cell focused, `⌘I` opens the *cell prompt* (`NotebookEditor` binds it). The shortcut sheet says "Show or hide the inspector". Measured: inspector `false` before, `false` after; `.cell-prompt` `true`. |
| **`⌘J` is unlisted** | Works (toggles the dock), absent from `SHORTCUTS` and from the sheet — so it is undiscoverable and untested. |

## B. Keyboard — three real defects, one of them a lost place

| id | Finding | Evidence |
|---|---|---|
| `KB-1` | **Escape from the palette or the sheet returns focus to `<body>`.** | probe: `palette open: focus INPUT` → `after Esc focus: BODY`. |
| `KB-2` | **`⌘I` is double-bound** (inspector vs cell prompt) and the sheet lies. | see A. |
| `KB-3` | **The composer textarea has no focus style of its own** — it inherits the ring from `.composer-box:focus-within`, so it *looks* focused, but `getComputedStyle(textarea).outline` is `none` and a keyboard user who tabs into it gets no direct affordance. Audit item `noFocusStyle: ["textarea. \"Message the agent\""]`. | `shell-audit.mjs` |
| — | **The code editor is reachable but shows no focus ring of its own** (`outline: none`, caret is 2px accent when focused — acceptable, and deliberate: a ring around a 40-line cell is noise). Not a defect; recorded so nobody "fixes" it. | `shell-audit3.mjs` |
| `KB-4` | **Tab order inside a cell is 6 stops before the text**: collapse, →code, Ask, link, Run, + | measured order: `section.cell-block`, `button.cell-collapse`, `button.cell-act` ×5 … then `.cm-content` at #40. |

## C. Scrolling — correct, and worth locking down

| id | Finding | Evidence |
|---|---|---|
| — | **One scroller for the notebook.** `.cells` is `overflow: auto` (4048/714); no editor inside it scrolls; no nested scroller anywhere. | `shell-audit2.mjs`: `nested-in=[]`, `nestedScrollers: 0` |
| — | A long cell (40 added lines) grows the cell; the *notebook* scrolls, not the cell. | probe: 40 `.cm-scroller` at 49px, none scrolling |
| `SC-1` | **`scroll-behavior: smooth` on `.transcript` and `.dock-body`** makes a streamed turn animate while it streams, and turns a wheel "flick" into an eased scroll — against P3 ([01](01-five-whys.md)). Reduced motion already disables it, so the cost is only for users without that preference. | `styles.css:313`, `styles.css:1913` |
| `SC-2` | **The wheel at the end of the notebook does nothing** (does not chain to an ancestor). Verified: `cells` at `scrollHeight`, wheel, `doc.scrollTop` unchanged — correct, because there is no ancestor scroller. Recorded so a future change does not introduce one. | probe |
| `SC-3` | **`overscroll-behavior` is `auto` on `.cells`** — on a trackpad, scrolling past the last cell can trigger browser back/forward navigation on some platforms. | `shell-audit2.mjs`: `overscroll=auto` |

## D. Controls — one lie, one missing name

| Finding | Evidence |
|---|---|
| The sheet says `⌘I` is the inspector (it is not, with a cell focused) | §A |
| `⌘J` absent from the sheet | §A |
| `⌘⇧M` (change model) works from the top bar but is not in `SHORTCUTS`… | `App.tsx:495` binds `mod+shift+m`; `keys.ts` lists `changeModel` as `mod+shift+m` ✔ (no defect — verified) |
| The separator is keyboard-operable and announces its value ✔ | `role=separator`, `tabIndex=0`, `aria-valuenow`, Arrow/Home handled (`Separator.tsx`) |

## E. What is already right (do not regress)

1. **The page never scrolls** (`html, body { overflow: clip }`) — the 100 px slide of round 3 stays fixed.
2. **Every zone width is a pure function** of viewport and intent, with `CENTRE_MIN = 480` winning.
3. **The separator is a real separator** — focusable, valued, arrow keys, double-click reset.
4. **The cells' own keyboard model** (edit/command modes, `d d`, `z`, `Alt+↑↓`) — from round 3.
5. **No nested scrollers** anywhere in the notebook view.

## Summary — four things to fix, three to harden

| id | Fix | Effort |
|---|---|---|
| `KB-1` | Focus returns to the opener when a dialog closes | small |
| `KB-2` | `⌘I` = inspector; the cell prompt gets `⌘⇧I`; the registry states ownership | small |
| `KB-3` | A visible focus style on the composer field | tiny |
| `KB-4` / `KB-7` | Skip links + a measured Tab budget; cell actions behind one Tab stop | medium |
| `SC-1` | Remove programmatic `smooth`; keep it only for explicit "Show" jumps | tiny |
| `SC-3` | `overscroll-behavior: contain` on the scrolling regions | tiny |
| `ZN-5` | Landmarks and names asserted by test | small |
