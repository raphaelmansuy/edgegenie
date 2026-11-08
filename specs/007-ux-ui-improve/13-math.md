# 13 — Math in markdown (`MD-1`…`MD-6`)

Part of [007](README.md). Requirements: [03](03-requirements.md). Panels: [12](12-hidden-panels.md).

---

## The report

> "Make sure LaTeX/KaTeX display is taken into account in markdown; assess the display, make sure to
> have the best UX/UI, not clunky, at the level of the best SaaS or coding agent on the market."

The screenshot showed an agent answer with `$$\frac{\pi}{4} = …$$` and `$\pi$` **as raw text**. The
renderer was a hand-rolled subset — headings, lists, tables, code, bold — with no math at all, so
every formula an LLM writes arrived as source.

## Assessment — what "clunky" actually means here

Four distinct failure modes, in order of how badly they damage an answer:

| # | Failure | Why it matters | Rule |
|---|---|---|---|
| **1** | **Swallowed text.** A naive `$…$` scan treats `WHERE p > $5` as an opening delimiter and eats the rest of the answer. | Losing text is worse than showing source. | `MD-1` |
| **2** | **Unstyled glyphs.** KaTeX with its default black ink on a warm surface, in either theme, reads as pasted-in. | The formula must be part of the sentence. | `MD-2` |
| **3** | **Torn lines.** An inline `\frac{a+b}{c-d}` that pushes a paragraph's leading apart. Measured before: a two-line paragraph at 56 px against 38 px for plain text. | The eye reads it as a rendering bug. | `MD-3` |
| **4** | **Wide formulas that widen the panel.** A display derivation in a 380 px dock. | The dock must not gain a horizontal scrollbar. | `MD-4` |

Two more, which are edge cases that decide whether this is trustworthy:

| # | Case | Rule |
|---|---|---|
| **5** | A **half-streamed** formula (`$x^`) must look like progress, not an error. | `MD-5` |
| **6** | A formula that is genuinely invalid must be **readable**, never throw into the transcript. | `MD-6` |

## What was built

### `domain/math.ts` — finding the math, as data (19 tests)

Pure. No DOM, no KaTeX, no React. The scanner implements the syntax LLMs actually emit (`$x$`,
`$$x$$`, `\(x\)`, `\[x\]`) with the rules that stop it eating an answer:

```
1  fenced code is never math      ```sql … $5 … ``` keeps its dollars
2  inline code is never math      `echo $HOME` keeps both
3  \$ is a literal dollar         "costs \$5"
4  $ opens inline only when it    next char is not a space or a digit,
   cannot be money                and the close is on the SAME line
5  an unmatched opener is text    a stray $ never swallows the tail
6  display may span lines         $$\n … \n$$  (trimmed)
```

Two bugs in the scanner were caught by its own tests, both of the same kind — **the fence skip left the
cursor before the close**, so it re-found the same fence and ran to the end of the document, silently
dropping every formula after a code block. And a mid-line ` ``` ` was treated as an inline span, which
ate the rest of the line.

`stashMath` / `splitStashed` replace each span with a private-use marker, so the existing markdown pass
runs **unchanged** and cannot see a delimiter. One parser, one code path, for a streamed answer and a
finished one.

### `components/Math.tsx` — rendering, with the failure modes handled

- **KaTeX is a lazy chunk** (259 KB, separate from the 498 KB app bundle, with its fonts). A page with
  no math downloads none of it.
- **React never owns KaTeX's node.** KaTeX replaces a node's children; a React child in the same node
  makes the next commit throw `removeChild … is not a child of this node` — which I hit immediately:
  **seven page errors and a blank screen**. The fallback source now lives in a **sibling** node.
- **Invalid TeX renders as readable source**, marked pink once the turn is done, and **quietly** while
  streaming (`MD-5`, `MD-6`).
- `trust: false` — a model cannot restyle the app with `\color` or a size macro.
- `strict: false` — accepts the Unicode (`×`, `−`, `π`) that models emit; strict mode throws on them.
- KaTeX's **MathML** copy stays, so a screen reader can read the formula aloud.

### Styles — where "not clunky" is decided

| Rule | Why |
|---|---|
| `line-height: 0` on the inline wrapper, `line-height: normal` on the KaTeX root | stops the formula contributing its own leading to the line box |
| `:has(.math-inline)` → `line-height: 1.72` on the **paragraph** | a line with a fraction needs the air a typesetter gives it — applied to the paragraph, so plain prose keeps its tight rhythm |
| display math is its own `.math-block` | `$$…$$` *means* a block; it must not be a centred formula inside a `<p>` |
| `overflow-x: auto` on the block | a wide derivation scrolls in its own box; the dock never gains a scrollbar |
| colour inherited from `--ink` | one palette, both themes, no second KaTeX theme to keep in step |
| `border-color: currentColor` on `.frac-line`, `.sqrt-line`, `.rule` | KaTeX paints these as borders; they must follow the ink |

Measured after the fix: inline formulas are **16–17 px in an 18.75 px line**; a paragraph holding a
fraction is three lines at **21.5 px each** (not 56 px for two); the fraction has **4 px clearance**
below its bar; a display formula is **521 × 43 px** and typesets exactly as a LaTeX engine would.

## Verified

`web/scripts/math-e2e.mjs`, against a new demo scenario that contains every case at once — display,
inline, Greek, a fraction, money, inline code, a fenced block with `$$`, and prose:

```
PASS display math is typeset            (1 block, 7 KaTeX nodes)
PASS inline math is typeset             (6 spans)
PASS no formula failed to typeset
PASS no raw TeX left for a valid formula
PASS money is not math                  ("$5 and $10" stays prose)
PASS a fenced block keeps its dollars   (no KaTeX inside <pre>)
PASS no paragraph torn apart by an inline formula
PASS math inherits the theme's ink in dark mode   (katex #eceae6 == answer #eceae6)
PASS a wide formula scrolls in its own box; the panel never widens
PASS no page errors
```

Screenshots `53`–`55`: the dock, dark mode, and a narrow column. Plus `50`–`52` from the iteration.

## `MD-7` — a `.md` file opens rendered

The deployed check for this work exposed the other half: an agent wrote `leibniz_pi_explanation.md`
whosewhole point was its formulas, the user opened it, and the app showed **raw `$$…$$` in an editor**.
The renderer was correct; the *surface* was wrong. A `.md` file is prose, so it now opens in a
rendered preview — the same `.answer` typography as the transcript, at the reading measure — with a
**Preview / Source** toggle in the document bar. A file with unsaved edits says so in the preview and
offers the source in one click, so the preview can never hide work in progress.

Two more bugs found by looking at the screenshots of that path:

- **`$4$` and `$1$` were rejected.** My money rule excluded a `$` followed by a digit, which is how a
  maths document says "multiply both sides by $4$". The false positive it was guarding against —
  `$5 and $10` — is caught by a better signal: **nobody writes a space before a closing `$`**, so a
  space there means the `$` was money. 8 raw dollars became 0.
- **The inspector drawer covered the document's own toolbar** (its "Working scope" legend intercepted
  the click on Preview). It is a sibling panel, not a modal, so it is now a **grid column**: it pushes
  the work instead of floating over it, and it yields to `CENTRE_MIN` — measured, the centre had been
  squeezed to 477 px by a fixed-width drawer, and now holds 480 exactly.

## Still open

- **`\begin{matrix}`/`aligned` inside `$…$`** is not specially handled: KaTeX renders it, but a tall
  environment in an inline position will grow the line. Rare in answers; the block form is correct.
- **No copy-as-TeX** on a formula. A user who wants the source selects text and gets KaTeX's DOM.
  A hover affordance is the next increment.
- **MathML is offered to every screen reader**, which some (VoiceOver) read twice — once as MathML,
  once as the markup. The ARIA pattern needs a real device test, not a headless one.
