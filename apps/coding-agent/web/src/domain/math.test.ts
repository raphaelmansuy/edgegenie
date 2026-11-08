import { describe, expect, it } from "vitest";
import { findMath, hasMath, splitStashed, stashMath } from "./math";

const tex = (text: string) => findMath(text).map((s) => [s.mode, s.tex] as const);

describe("findMath: the delimiters people actually write", () => {
  it("finds inline $x$ and display $$x$$", () => {
    expect(tex("the value $x$ here")).toEqual([["inline", "x"]]);
    expect(tex("$$x^2$$")).toEqual([["display", "x^2"]]);
    expect(tex("a $a+b$ and $$c$$")).toEqual([["inline", "a+b"], ["display", "c"]]);
  });
  it("finds the LaTeX forms \\( \\) and \\[ \\]", () => {
    expect(tex("so \\(y\\) and \\[z\\]")).toEqual([["inline", "y"], ["display", "z"]]);
  });
  it("trims a display block written across lines", () => {
    expect(tex("$$\n\\frac{\\pi}{4} = 1\n$$")).toEqual([["display", "\\frac{\\pi}{4} = 1"]]);
  });
  it("keeps the offsets consistent with the source", () => {
    const s = "a $x$ b";
    const [m] = findMath(s);
    expect(s.slice(m.start, m.end)).toBe("$x$");
  });
});

describe("findMath: the false positives that make a naive scan eat the answer", () => {
  it("does not read money as math", () => {
    expect(hasMath("it costs $5 and $10, so $15 in total")).toBe(false);
    expect(hasMath("a $ 5 fee")).toBe(false);
  });
  it("reads a number as math when it IS math: a digit is not the money signal", () => {
    // "$4$" and "$1$" are ordinary ("multiply both sides by $4$"); rejecting them left raw dollars in
    // a document that was otherwise typeset.
    expect(tex("multiplying both sides by $4$:")).toEqual([["inline", "4"]]);
    expect(tex("to $1$ decimal place")).toEqual([["inline", "1"]]);
    expect(tex("the set $S$ has $3$ items")).toEqual([["inline", "S"], ["inline", "3"]]);
  });
  it("keeps the money cases out, including the ones a naive scan pairs", () => {
    // "$5 and $10" would otherwise match "$5 and $" — the space before the close is the signal.
    expect(tex("it costs $5 and $10, so $15 in total")).toEqual([]);
    expect(tex("cost $12.50 today")).toEqual([]);
    expect(tex("total: $1,200.50 was spent")).toEqual([]);
  });
  it("respects an escaped dollar", () => {
    expect(tex("price is \\$5 not $x$").at(-1)).toEqual(["inline", "x"]);
    expect(findMath("\\$5 and \\$6")).toEqual([]);
  });
  it("never reads math inside inline code", () => {
    expect(hasMath("`echo $HOME $PATH`")).toBe(false);
    expect(tex("`$a$` then $b$")).toEqual([["inline", "b"]]);
  });
  it("never reads math inside a fenced block", () => {
    const src = "```sql\nselect * from t where p > $5 and q < $9\n```\n\nthen $x$";
    expect(tex(src)).toEqual([["inline", "x"]]);
  });
  it("handles a fence with a language and several lines", () => {
    const src = "```python\nx = '$a$'\n# $$not math$$\n```";
    expect(hasMath(src)).toBe(false);
  });
});

describe("findMath: streaming and malformed input", () => {
  it("reports nothing for an unterminated opener, rather than swallowing the tail", () => {
    expect(findMath("cost is $5 and then $x")).toEqual([]);
    expect(findMath("$$x^2")).toEqual([]);
    expect(findMath("\\(x")).toEqual([]);
  });
  it("finds the span once the closing delimiter arrives", () => {
    expect(findMath("$$x^2")).toEqual([]);
    expect(tex("$$x^2$$")).toEqual([["display", "x^2"]]);
  });
  it("ends inline math at the line end, not later", () => {
    expect(tex("$a\nb$")).toEqual([]);
  });
  it("skips escaped characters inside inline math when finding the close", () => {
    expect(tex("$a\\$b$")).toEqual([["inline", "a\\$b"]]);
  });
  it("is not confused by an inline fence that is not a block", () => {
    // A ``` in the middle of a line is not a fence; math after it still renders.
    expect(tex("text ```x``` then $y$")).toEqual([["inline", "y"]]);
  });
  it("handles an empty document and a document that is only math", () => {
    expect(findMath("")).toEqual([]);
    expect(tex("$$\\pi$$")).toEqual([["display", "\\pi"]]);
  });
});

describe("stashMath / splitStashed: what the markdown pass sees", () => {
  it("leaves prose alone when there is no math", () => {
    const { prose, spans } = stashMath("plain **text** only");
    expect(prose).toBe("plain **text** only");
    expect(spans).toEqual([]);
  });
  it("replaces math with a marker that no markdown rule touches", () => {
    const { prose, spans } = stashMath("a $x$ b *c*");
    expect(spans).toHaveLength(1);
    expect(prose).not.toContain("$");
    expect(prose).toContain("*c*");        // the emphasis still parses
  });
  it("round-trips: the pieces reassemble the original", () => {
    const src = "one $a$ two $$b$$ three";
    const { prose, spans } = stashMath(src);
    const rebuilt = splitStashed(prose)
      .map((p) => (p.kind === "math" ? spans[p.index].raw : p.text))
      .join("");
    expect(rebuilt).toBe(src);
  });
  it("keeps the order of several spans", () => {
    const { prose, spans } = stashMath("$a$ and $b$");
    expect(splitStashed(prose).filter((p) => p.kind === "math").map((p) => spans[(p as { index: number }).index].tex))
      .toEqual(["a", "b"]);
  });
});
