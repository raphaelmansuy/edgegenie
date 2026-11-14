/** Where the math is in a markdown string. Pure: no DOM, no KaTeX, no React.
 *
 * Splitting math out of markdown is a *scanning* problem, and it is the part that goes wrong: a `$` in
 * a price, an escaped `\$`, a fence containing `$` that must not be read as math, `$$` inline on one
 * line vs. a display block across three lines. Getting this right in a regex produces something that
 * works for the example and fails on the next answer, so the rules are spelled out here and tested
 * directly.
 *
 * The syntax is the one every LLM is trained on, and the one Databricks, GitHub and Jupyter all render:
 *
 *   $x$  or  \(x\)           inline
 *   $$ x $$  or  \[ x \]     display
 *
 * Rules, in the order a scan applies them:
 *  1. **Code is never math.** Inside a fenced block or an inline code span, `$` is a dollar sign. A
 *     scan that ignores this turns `SELECT * FROM t WHERE p > $5` into an opening delimiter and eats
 *     the rest of the answer.
 *  2. **`\$` is a literal dollar**, and the backslash is consumed.
 *  3. **`$$` opens display math**, which closes at the next `$$` (or `\]` for the LaTeX form). It may
 *     span lines, and it is trimmed: LLMs write `$$\n x \n$$`.
 *  4. **`$` opens inline math only when it cannot be money**: there is no whitespace after it and a
 *     closing `$` on the *same* line. `$5 and $10` is prose (no second `$`); `$x$` is math; and `$4$`
 *     is math too — a digit alone is not the signal, a missing close is.
 *  5. **An unmatched opener is literal text**, not a swallowed tail: a streamed answer must never lose
 *     everything after a stray `$`.
 */

export interface MathSpan {
  /** Offset of the first character of the whole span (delimiters included). */
  start: number;
  /** Offset one past the last character. */
  end: number;
  /** The TeX source, without delimiters, trimmed. */
  tex: string;
  /** `display` is a block (centred, own line); `inline` flows with the text. */
  mode: "inline" | "display";
  /** The raw text that was scanned, delimiters included. */
  raw: string;
}

/** Characters that may not follow an opening `$`.
 *
 * A digit WAS in this class, and it was wrong: `$4$` and `$1$` are perfectly ordinary math ("multiply
 * both sides by $4$"), and rejecting them left raw dollars in a document that was otherwise typeset.
 * Space still disqualifies, because no LaTeX is written `$ x $`, and `$5 and $10` is caught by the
 * closing-delimiter rule instead: there is no second `$` on the line, so the opener is literal. */
const NOT_AFTER_OPEN = /\s/;

/**
 * Find every math span in `text`, in order, skipping code.
 *
 * Returns spans only; rendering them is the caller's job, so this can be tested as data and the
 * markdown renderer can keep streaming (an unterminated span is simply not reported yet — the text is
 * shown as-is until its closing delimiter arrives, which is what a streamed `$$` should look like).
 */
export function findMath(text: string): MathSpan[] {
  const out: MathSpan[] = [];
  let i = 0;
  const n = text.length;
  const missingClose = new Set<string>();
  /** Set while inside a fenced code block, to the fence marker seen. */
  let fence: string | null = null;

  while (i < n) {
    const ch = text[i];

    // --- fenced code: find the opening line, then jump to its closing fence ---------------------
    if (fence === null && (ch === "`" || ch === "~")) {
      const run = runLength(text, i, ch);
      if (run >= 3) {
        const marker = ch.repeat(run);
        const lineEnd = text.indexOf("\n", i);
        const lineStart = text.lastIndexOf("\n", i) + 1;
        // Only a fence that STARTS a line opens a block, and only if there IS a body line yet. A
        // mid-line run is punctuation, and a run at the very end of a streamed answer is not a block
        // (returning here dropped every span after it — a fence with no newline yet).
        if (text.slice(lineStart, i).trim() === "" && lineEnd !== -1) {
          fence = marker;
          i = lineEnd + 1;
          continue;
        }
        i += run;
        continue;
      }
    }
    if (fence !== null) {
      /* Find the closing fence: the next line that STARTS with the same run. Searching for "\n"+fence
         and then skipping to the following newline left `i` on the newline BEFORE the close, so the
         scanner re-entered this branch, found the same close again, and looped to the end of the
         document — which silently dropped every span after a code block. */
      const lineStart = text.lastIndexOf("\n", i - 1) + 1;
      let from = lineStart;
      let close = -1;
      while (from < n) {
        if (text.startsWith(fence, from)) {
          const beforeOk = from === 0 || text[from - 1] === "\n";
          const run = runLength(text, from, fence[0]);
          if (beforeOk && run >= fence.length) { close = from; break; }
        }
        const nl = text.indexOf("\n", from);
        if (nl === -1) break;
        from = nl + 1;
      }
      if (close === -1) return out;                     // the fence has not closed yet
      const after = text.indexOf("\n", close);
      i = after === -1 ? n : after + 1;
      fence = null;
      continue;
    }

    // --- inline code: skip to the closing run of the same length --------------------------------
    if (ch === "`") {
      const run = runLength(text, i, "`");
      /* A run of three or more is a FENCE marker, not an inline span: treating it as inline code made
         "```x```" swallow the rest of the line and lose the math after it. A fence that did not open a
         block (because it is mid-line) is just punctuation, so skip the run and carry on scanning. */
      if (run >= 3) { i += run; continue; }
      const close = indexOfRun(text, i + run, "`", run);
      if (close !== -1) { i = close + run; continue; }
      i += run;
      continue;
    }

    // --- escaped dollar: literal, and the escape is part of the text ----------------------------
    if (ch === "\\" && (text[i + 1] === "$" || text[i + 1] === "\\")) { i += 2; continue; }

    // --- LaTeX delimiters ---------------------------------------------------------------------
    if (ch === "\\" && (text.startsWith("\\(", i) || text.startsWith("\\[", i))) {
      const display = text[i + 1] === "[";
      const closeTok = display ? "\\]" : "\\)";
      const close = missingClose.has(closeTok) ? -1 : text.indexOf(closeTok, i + 2);
      if (close === -1) missingClose.add(closeTok);
      if (close !== -1) {
        out.push({
          start: i, end: close + closeTok.length,
          tex: text.slice(i + 2, close).trim(), mode: display ? "display" : "inline",
          raw: text.slice(i, close + closeTok.length),
        });
        i = close + closeTok.length;
        continue;
      }
      i += 2;
      continue;
    }

    // --- $$ display, possibly across lines ----------------------------------------------------
    if (ch === "$" && text[i + 1] === "$") {
      const close = text.indexOf("$$", i + 2);
      if (close !== -1) {
        out.push({
          start: i, end: close + 2, tex: text.slice(i + 2, close).trim(), mode: "display",
          raw: text.slice(i, close + 2),
        });
        i = close + 2;
        continue;
      }
      // Unterminated: not math yet. Show the dollars as text and keep scanning (rule 5).
      i += 2;
      continue;
    }

    // --- $ inline, only when it cannot be money (rules 4 and 5) -------------------------------
    if (ch === "$") {
      const span = inlineAt(text, i);
      if (span) { out.push(span); i = span.end; continue; }
      i += 1;
      continue;
    }

    i += 1;
  }
  return out;
}

/**
 * The inline span that starts at `at`, or null if this `$` is money.
 *
 * The hard case is `$5 and $10, so $15`: a naive close search pairs the first opener with the second
 * dollar and calls "5 and" math. Two signals separate the two readings, and both are properties of how
 * people write TeX rather than of the characters:
 *
 *   · **TeX has no space before its closing `$`.** Nobody writes `$x $`; prices are written `$5 and`.
 *   · **A short, space-free, digit-only run is money**, not a formula — `$10` alone in a sentence.
 *
 * So a candidate span is rejected when the character before the close is whitespace, or when its
 * content has no space and no letter, digit or backslash-command beyond a plain number. `$4$` (a number
 * used AS math, with its closing dollar tight against it) survives, which was the bug this fixes.
 */
function inlineAt(text: string, at: number): MathSpan | null {
  const next = text[at + 1];
  if (!next || NOT_AFTER_OPEN.test(next)) return null;

  for (let j = at + 1; j < text.length; j++) {
    const c = text[j];
    if (c === "\n") return null;                 // inline math is inline: one line
    if (c === "\\") { j += 1; continue; }        // an escaped char, including \$
    if (c !== "$") continue;
    if (text[j + 1] === "$") return null;         // `$x$$` is ambiguous: treat as text
    /* The space before the close is the whole money test, and it is a rule of the notation rather than
       a guess: TeX is written `$x$`, prices are written `$5 and $10`. Adding "a bare number is money"
       on top of it rejected `$4$`, which is how a maths document says "multiply by 4". */
    if (/\s/.test(text[j - 1])) return null;
    const tex = text.slice(at + 1, j).trim();
    if (tex === "") return null;
    return { start: at, end: j + 1, tex, mode: "inline", raw: text.slice(at, j + 1) };
  }
  return null;
}

function runLength(text: string, at: number, ch: string): number {
  let k = 0;
  while (text[at + k] === ch) k += 1;
  return k;
}

/** The next run of EXACTLY `len` of `ch` (a one-backtick span must not be closed by a fence). */
function indexOfRun(text: string, from: number, ch: string, len: number): number {
  for (let j = from; j < text.length; j++) {
    if (text[j] !== ch) continue;
    const run = runLength(text, j, ch);
    if (run === len) return j;
    j += run - 1;
  }
  return -1;
}

/** Replace each span with a placeholder and hand back the pieces, so a markdown renderer can treat
 *  prose normally and drop the rendered math in at the markers.
 *
 *  The placeholder is a private-use character plus an index. It cannot occur in real text, it survives
 *  a regex-based markdown pass unchanged (no `*`, `_`, `[`, `$`), and it is one character, so offsets in
 *  the prose stay stable in length terms where it matters. `mathAt` resolves it back.
 */
const MARK = "\uE000";
const END = "\uE001";

export interface Split { prose: string; spans: MathSpan[] }

/** Prose with each math span replaced by `\uE000<index>\uE001`, plus the spans to substitute back. */
export function stashMath(text: string): Split {
  const spans = findMath(text);
  const literal = (s: string) => s.replaceAll(MARK, MARK + MARK);
  if (spans.length === 0) return { prose: literal(text), spans };
  let prose = "";
  let at = 0;
  spans.forEach((s, idx) => {
    prose += literal(text.slice(at, s.start)) + MARK + String(idx) + END;
    at = s.end;
  });
  prose += literal(text.slice(at));
  return { prose, spans };
}

/** Split a prose string on the placeholders from `stashMath`. Returns text and math in order. */
export function splitStashed(prose: string): ({ kind: "text"; text: string } | { kind: "math"; index: number })[] {
  const out: ({ kind: "text"; text: string } | { kind: "math"; index: number })[] = [];
  let at = 0;
  for (let i = 0; i < prose.length; i++) {
    if (prose[i] !== MARK) continue;
    if (prose[i + 1] === MARK) {
      if (i > at) out.push({ kind: "text", text: prose.slice(at, i) });
      out.push({ kind: "text", text: MARK });
      i += 1; at = i + 1; continue;
    }
    const close = prose.indexOf(END, i + 1);
    if (close === -1) break;
    if (!/^\d+$/.test(prose.slice(i + 1, close))) continue;
    if (i > at) out.push({ kind: "text", text: prose.slice(at, i) });
    out.push({ kind: "math", index: Number(prose.slice(i + 1, close)) });
    i = close;
    at = close + 1;
  }
  if (at < prose.length) out.push({ kind: "text", text: prose.slice(at) });
  return out;
}

/** True when the text contains a math span: lets a caller skip the whole path for ordinary prose. */
export const hasMath = (text: string): boolean => findMath(text).length > 0;
