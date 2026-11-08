# 04 · Wireframes (ASCII)

[Index](README.md) · prev: [03 Requirements](03-requirements.md) · next: [05 Diagrams](05-diagrams.md)

Every drawing below is **generated** on an exact character grid by
[`tools/draw_wireframes.py`](tools/draw_wireframes.py): one primitive composes each interior row to an
exact width, so a box cannot drift a character out in an edit. Then the drawings are verified
independently by the repository's own checker, which parses each box rather than comparing line lengths:

```bash
python3 specs/008-github-page/tools/draw_wireframes.py --check
cd apps/coding-agent/web && node scripts/verify-spec-ascii.mjs ../../../specs/008-github-page
```

The design widths behind the drawings are content `1100` px, the navigation breakpoint `860` px, and the
narrowest supported viewport `320` px. On the desktop drawings one character is about 11 px of the real
page.

---

## Route order

The reading order. It drives the header, the footer, and the previous/next links (`[NAV-7]`).

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────┐
│  1  /           Home       what it is, why it exists, the three claims, the first look         │
│  2  /tour/      Tour       17 screenshots of the running app, captioned by width               │
│  3  /tutorial/  Tutorial   the 30-minute setup, rendered from docs/tutorial.md                 │
│  4  /evidence/  Evidence   the exam results, with denominator and caveat                       │
│  5  /install/   Install    the three ways to run it, and what each needs                       │
│  6  /reference/ Reference  the docs and the five specifications, verbatim                      │
│  7  /about/     About      who built it, why, and what else he builds                          │
│  -  /404.html   404        the seven routes, in the site's own design                          │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Screen 1. Home, desktop 1100 to 1600 px

The first two viewports are the whole argument: identity, the problem, two actions, and one real screenshot of the product (`[PG-1]`, `[PG-3]`).

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────┐
│  ◕ OpenGenie     Tour   Tutorial   Evidence   Install   Reference            [◐][◑][●]   GitHub│
├────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                │
│   Apache-2.0   ·   Databricks App   ·   any model you can reach                                │
│                                                                                                │
│   Genie Code gives you one model.                                                              │
│   You cannot choose it, and you cannot see the bill coming.                                    │
│                                                                                                │
│   OpenGenie is a Databricks App that does the same work with the model                         │
│   you pick, writes only inside the folder you name, and proves what it                         │
│   did before it says done.                                                                     │
│                                                                                                │
│   ┌────────────────────────┬──────────────────────────┐                                        │
│   │     Read the tour      │       Install it         │                                        │
│   └────────────────────────┴──────────────────────────┘                                        │
│      filled primary                outline                                                     │
│                                                                                                │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐ │
│   │       the app at 1440 px: sessions and files · notebook · assistant dock                 │ │
│   │       a real screenshot, not an illustration of one                                      │ │
│   │                                                                                          │ │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘ │
│   caption: "The three-pane shell at 1440 px. The dock is bound to the notebook."               │
│                                                                                                │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Screen 2. Home, continued: the three claims

Each cell is a claim, a one-line reason, and a path to the file that implements it (`[PG-2]`), followed by the one measurement that motivates the page — with its caveat attached (`[CPT-2]`).

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ┌──────────────────────────────┬──────────────────────────────┬──────────────────────────────┐ │
│ │                              │                              │                              │ │
│ │ 1 · The model is yours       │ 2 · The fence is real        │ 3 · Proof, not promises      │ │
│ │                              │                              │                              │ │
│ │ 16 models from 4 providers,  │ A write is allowed only in   │ A requirement counts as done │ │
│ │ plus whatever the gateway    │ the folder and the schema    │ only when a tool call proves │ │
│ │ serves, discovered live.     │ you named. Anything else     │ it. A citation to a call that│ │
│ │                              │ is ask, or deny.             │ never happened is a verdict. │ │
│ │ seed/llm_models.yaml  →      │                              │                              │ │
│ │                              │ api/domain/scope.py  →       │ api/domain/evidence.py  →    │ │
│ └──────────────────────────────┴──────────────────────────────┴──────────────────────────────┘ │
│                                                                                                │
│ Same tools, same rules, two models. 8 development tasks (M1-M8), one run each:                 │
│                                                                                                │
│ gpt-oss-120b       █████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░   39%                          │
│ Gemini 3.8 Flash   ██████████████████████████████████████░░░░░░   86%                          │
│                                                                                                │
│ The caveat is on the card, not in a footnote: one run per model, and M2 has the                │
│ widest natural spread of the eight. Source, and the command that regenerates this,             │
│ are one link away on /evidence/.                                                               │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Screen 3. Home, continued: what it is not, and the footer

The honesty block. It exists because the study's own limits are the page's credibility (`[PG-15]`, `[PG-16]`).

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                                │
│ What this is not                                                                               │
│                                                                                                │
│ · Not a replacement for Genie's business-term understanding. Our exams named the tables.       │
│ · Not a cost comparison. We measured tokens, not money, and hold no Genie usage history.       │
│ · Not a hosted demo. The app needs your workspace token, so there is nothing to click.         │
│ · Not a guarantee. One run per setup, small clean data, well-specified tasks.                  │
│                                                                                                │
│ →  Every number above, with its source and the command that regenerates it.  [Evidence]        │
│                                                                                                │
│ ┌───────────────────────────────────────────────────────────────────────────────────────┐      │
│ │ footer                                                                                │      │
│ │  ◕ OpenGenie · Apache-2.0 · built 8 Nov 2026 from commit 39eeb2f                      │      │
│ │  Pages: Tour · Tutorial · Evidence · Install · Reference · About                      │      │
│ │  Elsewhere: GitHub · LinkedIn · EdgePii · EdgeQuake · the book                        │      │
│ └───────────────────────────────────────────────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Screen 4. Any document page (`/tour/`, `/tutorial/` and so on), desktop

One frame divided into a 22-character contents rail and the content column. The rail exists only above 1100 px, and the measure never exceeds 72 characters (`[NAV-6]`).

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────┐
│  ◕ OpenGenie    Tour  Tutorial  Evidence  Install  Reference                  [◐][◑][●]  GitHub│
├──────────────────────┼─────────────────────────────────────────────────────────────────────────┤
│ On this page         │ Tour                                                                    │
│ ─────────────        │ What the app looks like, at four widths, in both themes.                │
│ The shell            │                                                                         │
│   The notebook       │ ┌───────────────────────────────────────────────────────────────────┐   │
│   The dock           │ │ 1440 px · light                                                   │   │
│   The picker         │ │                                                                   │   │
│ The widths           │ │   the screenshot, downscaled to the column                        │   │
│   1440               │ │                                                                   │   │
│   1100               │ └───────────────────────────────────────────────────────────────────┘   │
│   800                │ Sessions and files on the left, the notebook in the centre, the         │
│ Themes               │ assistant docked right and saying what it is bound to.                  │
│                      │                                                                         │
│ ─────────────        │ ┌───────────────────────────────────────────────────────────────────┐   │
│ ← Evidence           │ │ 1100 px · dark                                                    │   │
│ Tutorial →           │ │                                                                   │   │
│                      │ │   ...                                                             │   │
│ 200 px rail          │ │                                                                   │   │
│                      │ └───────────────────────────────────────────────────────────────────┘   │
│                      │ 72 characters of measure, no rail, no advertising.                      │
├──────────────────────┴─────────────────────────────────────────────────────────────────────────┤
│ ← Evidence                                                                        Tutorial →   │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Screen 5. Tablet, 860 px, the navigation collapses

`[NAV-4]`. The contents rail is gone, the content takes the full width, and the header keeps identity and one menu button. The menu is a sheet of 44 px rows.

```text
┌──────────────────────────────────────────────────────────────────────────┐
│  ◕ OpenGenie                           [☰ Menu]   [◐][◑][●]   GitHub     │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Tour                                                                    │
│  What the app looks like, at four widths, in both themes.                │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │       the screenshot, scaled to the column                         │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  after pressing [☰ Menu]:                                                │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │   Home                                                             │  │
│  │   Tour          ← current                                          │  │
│  │   Tutorial                                                         │  │
│  │   Evidence                                                         │  │
│  │   Install                                                          │  │
│  │   Reference                                                        │  │
│  │   About                                                            │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  44 px rows, focus trapped, Escape closes. A sheet, not a squeezed row.  │
└──────────────────────────────────────────────────────────────────────────┘
```

## Screen 6. Phone, 320 to 430 px

`[AX-7]`. One column and no horizontal scroll on the page. A wide screenshot scrolls inside its own frame instead of being squashed to illegibility.

```text
┌────────────────────────────────────────────┐
│  ◕ OpenGenie               [☰] [◐][◑][●]   │
├────────────────────────────────────────────┤
│                                            │
│  Tour                                      │
│  What the app looks like.                  │
│                                            │
│  ┌──────────────────────────────────────┐  │
│  │ 1440 px · light                      │  │
│  │ ───────────────                      │  │
│  │  swipe to pan                        │  │
│  │ ───────────────                      │  │
│  └──────────────────────────────────────┘  │
│                                            │
│  The three-pane shell at 1440 px:          │
│  the notebook in the centre, the           │
│  assistant docked on the right.            │
│                                            │
├────────────────────────────────────────────┤
│  ← Evidence                  Tutorial →    │
└────────────────────────────────────────────┘
```

## Screen 7. The evidence page, one claim card, annotated

The most important component on the site ([P3](01-five-whys.md#p3-two-glances-about-the-same-thing-cannot-share-a-slot)): the six facts a suspicious reader needs, and the caveat *inside* the card rather than after the table.

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  CL-3                                                            value   86%           │
│  ────────────────────────────────────────────────────────────────────────────────────  │
│  The model matters more than the tooling                                               │
│                                                                                        │
│  Same agent, same tools, same rules, two models.                                       │
│                                                                                        │
│ gpt-oss-120b       ████████████████░░░░░░░░░░░░░░░░░░░░░░░░   39%                      │
│ Gemini 3.8 Flash   ██████████████████████████████████░░░░░░   86%                      │
│                                                                                        │
│  ────────────────────────────────────────────────────────────────────────────────────  │
│  how it was measured     8 development tasks (M1-M8), one run per model,               │
│                         scored on the live workspace: 60/152 and 130/152               │
│  what it does not prove  one run each; M2 has the widest natural spread                │
│  source                  exams/results/v5_gptoss/ · v5_gemini/                         │
│  regenerate              python3 exams/make_tables.py                                  │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

## Screen 8. State: the theme, and the no-flash rule

`[NAV-3]`. One attribute on `<html>`, set before first paint by an inline script that reads the same key the control writes.

```text

   system ──press──► light ──press──► dark ──press──► system
      │                │                │                 │
      ▼                ▼                ▼                 ▼
   follows OS       data-theme=light  data-theme=dark   attribute removed,
   (no attribute)                                       follows OS again

   first paint: <html data-theme="dark">, set by a nine-line inline script in <head>
   no stylesheet-dependent flash, and no transition on the document element

```

## Screen 9. State: the navigation menu, and one escape order

`[NAV-4]`. One ordered meaning for Escape, the same discipline as [007 `KB-8`](../007-ux-ui-improve/03-requirements.md).

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│  open with Enter or Space                                                │
│         │                                                                │
│         ▼                                                                │
│  focus moves to the first item, and Tab stays inside                     │
│         │                                                                │
│         ├── Escape ──────────► close, focus returns to the button        │
│         ├── click outside ───► close, focus does not move                │
│         ├── choose an item ──► navigate, the button keeps :focus         │
│         └── resize ≥ 860px ──► close silently, no focus change           │
│                                                                          │
│  one event, one meaning.                                                 │
└──────────────────────────────────────────────────────────────────────────┘
```

## Screen 10. The 404

`[PG-18]`. A real page: identity, the seven routes, and no apology longer than one line.

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────┐
│  ◕ OpenGenie    Tour  Tutorial  Evidence  Install  Reference                  [◐][◑][●]  GitHub│
├────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                │
│  404                                                                                           │
│  That page is not here. Nothing was lost; the link was wrong.                                  │
│                                                                                                │
│  ┌─────────────────────┬─────────────────────┬─────────────────────┬────────────────────────┐  │
│  │ Home                │ Tour                │ Tutorial            │ Evidence               │  │
│  └─────────────────────┴─────────────────────┴─────────────────────┴────────────────────────┘  │
│  ┌─────────────────────────────┬─────────────────────────────┬──────────────────────────────┐  │
│  │ Install                     │ Reference                   │ About                        │  │
│  └─────────────────────────────┴─────────────────────────────┴──────────────────────────────┘  │
│                                                                                                │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
```


---

## What the drawings decided

| Drawing | The decision it fixes | Requirement |
|---|---|---|
| Screens 1–3 | The product screenshot sits above the second viewport, not after the findings | `PG-3` |
| Screen 2 | Three claims, each with a path to the code that implements it | `PG-2` |
| Screen 2 | The one measurement appears on the home page **with** its caveat | `CPT-2` |
| Screen 3 | The limits are a section of the home page, not a footnote on another one | `PG-15` |
| Screen 4 | One frame, two panes: the contents rail is a division, not a second box | `NAV-6` |
| Screen 5 | One button below 860 px, and a sheet of 44 px rows rather than a squeezed row | `NAV-4` |
| Screen 6 | A wide screenshot scrolls inside its frame; the page never scrolls sideways | `AX-7` |
| Screen 7 | Value, denominator, run count, model, caveat and command in one card | `CPT-2` |
| Screens 8–9 | Two state machines, each with one meaning per event | `NAV-3`, `NAV-4` |
| Screen 10 | A wrong link costs the reader one click, not a dead end | `PG-18` |
