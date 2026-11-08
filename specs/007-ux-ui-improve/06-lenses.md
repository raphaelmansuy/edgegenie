# 06 — Six lenses

Part of [007](README.md). One system, six owners, six sets of questions. Requirements:
[03](03-requirements.md). Plan: [08](08-implementation-plan.md).

---

## 1. Product Owner

**Question:** what does the user get, and what does it cost them to get it?

*Today:* the app can do everything Genie Code does, and a person cannot find half of it. Measured:
40 Tab presses to the code, `⌘I` doing something the sheet does not say, Escape dropping focus onto
`<body>`. None of those is a missing capability — they are all the same missing *contract*.

**What shipping this buys:**

| Outcome | Measure before → after |
|---|---|
| A keyboard user can work without the mouse | Tab-to-code 40 → ≤ 12; every dialog returns focus (`KB-1`) |
| The documented shortcuts are true | 19 registered, 1 unlisted, 1 double-bound → 21 registered, 0 unlisted, 0 double-bound (`KB-5`) |
| Nobody is navigated away by accident | `overscroll-behavior: auto` → `contain` on 3 regions (`SC-3`) |
| The app stops moving on its own | 2 `smooth` data paths → 0 (`SC-1`) |

**What it costs:** four small phases, no new dependency, no new bundle chunk, one pure module
(`domain/keys.ts` gains 3 fields), one hook (`useHotkeys` gains arbitration), one component
(`SkipLinks`). The riskiest change is `⌘I`, and it is riskiest because it is *visible*: see `[D3]`.

**What I am deliberately not doing:** a full command-mode for the shell (vim-style `g i`), a
customisable keymap, a "focus mode" that hides all chrome. All three are real Genie-Code-adjacent
ideas and all three would double this scope without fixing a measured defect.

## 2. Full-stack developer

**Question:** where does each rule live so it cannot drift?

| Rule | Home | Why there |
|---|---|---|
| Which chord means what | `domain/keys.ts` (`SHORTCUTS`) | data, so a test can walk it both ways |
| Who wins when two could answer | `domain/keys.ts` (`resolve`) — pure | the arbitration is a function, not a listener order |
| How a dialog returns focus | `hooks/useReturnFocus.ts` (new) | one effect, five call sites; a second copy is how the bug returns |
| Whether a zone is a column | `domain/layout.ts` (exists) | already the only producer of the grid string |
| Which region scrolls | CSS, asserted by test | a scroller is a layout fact, not JavaScript state |

**The seam I am most careful about:** `NotebookEditor` currently binds `⌘I` in its own
`onKeyDown`. `KB-2` says that binding moves to `⌘⇧I`. If I change only the editor and not the
registry, the sheet still lies; if I change only the registry, two owners remain. So the change is
atomic: registry + editor + sheet + test, one commit.

**SOLID, concretely:**

- *Single responsibility*: `useReturnFocus` knows focus; `resolve` knows chords; `layout` knows widths.
  Today `App.tsx` knows all three (940 lines).
- *Open/closed*: adding a chord is adding a row to `SHORTCUTS` — no `App.tsx` edit for a *simple*
  binding (a binding that needs app state still registers a handler, which is correct: the app owns
  state, the registry owns meaning).
- *Dependency inversion*: the hook depends on `resolve()` and `focusStore`, not on React state.

## 3. Database expert

**Question:** what is persisted, where, and can it be wrong?

Nothing in this spec adds a server table. The persistence that matters is local:

| Store | Key | Shape | Failure mode | Mitigation |
|---|---|---|---|---|
| `localStorage` | `coding-agent:layout:v1` | `Layout` (v2 with `STORAGE_VERSION`) | a v1 blob read by v2 | `parseLayout` upgrades, tested |
| `sessionStorage` | `coding-agent:view:v1` | `{[path]: ViewState}` | a path that no longer exists; a notebook that shrank | `clampTo` pulls it inside (`viewstate.ts`) |
| `localStorage` | `coding-agent:recent-docs:v1` | `RecentDoc[6]` | malformed JSON, a `kind` that is not a `DocKind` | `valid()` filters; tested |
| `localStorage` | `coding-agent:workspace-favorites` | `Favorite[]` | same | `readFavorites` tolerates |

**The invariant worth stating:** no store may contain *content* — only geometry, paths and choices.
A draft is the one exception (`drafts.ts`, spec 003) and it is documented there.

**Why no server change:** a keymap preference is per-device (mac vs PC), and a "last focus" is
meaningless across sessions. Persisting either server-side would create a migration for no user
value.

## 4. UX designer

**Question:** does the shell teach itself?

Three affordances do that work, and all three are weakened today:

1. **The focus ring is the map.** A keyboard user learns the shell by Tab and by seeing where they
   are. `KB-3` is therefore not cosmetics; it is the map.
2. **The shortcut sheet is the manual.** It must be true (`KB-5`) and it must say what the chord does
   *here* (`KB-6`). A sheet that lies is worse than no sheet: it teaches a wrong model.
3. **The skip link is the index.** It says, in two words each, what the regions are ("the work",
   "the conversation") — which is also the product's own mental model from 006.

**Deliberate negative space:** no toast for focus changes, no animated ring, no "you pressed ⌘I"
nudge. Focus feedback is visual and instant; announcing it would be noise to a screen reader that
already gets the landmark name.

**The one visual change** (`KB-3`): the composer gets its own inner ring, so the field — not just its
container — is visibly focused. `.composer-box:focus-within` stays for the outer glow.

## 5. Front-end designer

**Question:** what could this break in the paint?

| Risk | Why it matters | Guard |
|---|---|---|
| A focus ring that shifts layout | `outline` does not, `box-shadow` does not — but `border` does. Use `outline`/`box-shadow` only. | style rule + visual diff in `[S2]` |
| Skip links appearing shift the top bar | They are `position: absolute` inside the 52px bar, `pointer-events: none` at rest | CLS check in the audit (`body.scrollH === innerH`) |
| `overscroll-behavior` on a scroll container changing scrollbar rendering | It does not change layout; it changes chaining | scrollbar-gutter already `stable` on the tree; not affected |
| Removing `smooth` making "Show" feel abrupt | It is the *data* paths that lose `smooth`; `Show` keeps it | `SC-1` explicitly allows a user-requested jump |
| A roving tabindex on a cell changing the visual selected state | Command mode already draws a left accent bar; the roving stop reuses it | screenshot `[S3]` |
| Focus ring colour on the accent in dark mode | The accent inverts; `--on-accent` exists for exactly this | both themes in `[S2]` |

**One decision:** the skip links use the accent background with `--on-accent` text — the same pairing
as the primary button — rather than an outline, because a skip link must be unmissable in the one
moment it is visible.

## 6. Marketing and growth expert

**Question:** what does a person *see* in the first ten seconds, and does it say "senior tool"?

The first ten seconds are the home screen (round 4) plus two keyboard moments:

- **`⌘K`** — the palette is the single most persuasive interaction in a developer tool. It says "this
  was built by someone who uses tools like this". It is already there; `KB-1` makes the way out
  trustworthy.
- **`⌘/`** — the shortcut sheet is the proof of depth. Nineteen true shortcuts persuade; nineteen
  shortcuts with one lie destroy the effect disproportionately, because the reader tries one at
  random.

**The narrative this work supports, in one line:** *"It does what it says, including the keys."*
That is a growth asset: every review, every demo, every onboarding video is about trust in the small
things. A tool whose documented shortcut is false reads as a prototype.

**What I would put in a screenshot, after this work:**

| Shot | Message |
|---|---|
| `⌘K` open over a notebook, palette ranked, caret visible behind it | "one query away" |
| the skip link visible at the top | "built for the keyboard, not decorated with it" |
| the cell in command mode with the left accent bar | "the shell has modes, like Vim" |

**What not to claim:** "faster than Databricks". The defensible claim is *narrower and stronger*:
"every control reachable without a mouse, and your place is never lost."
