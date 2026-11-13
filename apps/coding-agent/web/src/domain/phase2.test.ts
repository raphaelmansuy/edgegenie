/** The two phase-2 vocabularies on the client: write mode and budget. `[R-9]` `[R-24]`.
 *
 *  Both are mirrors of a server module, and both are tested from the failure they prevent — a mode that
 *  silently widens, and a meter that claims a ceiling nobody set.
 */
import { describe, expect, it } from "vitest";
import {
  budgetFraction, budgetLine, budgetTone, hasCeiling, tokens, type BudgetState,
} from "./budget";
import {
  DEFAULT_WRITE_MODE, WRITE_MODES, asWriteMode, writeMode, writeModeChip, writeModeHint,
} from "./writemode";

const budget = (over: Partial<BudgetState> = {}): BudgetState => ({
  used: 0, limit: 0, fraction: 0, allowed: true, verdict: "unlimited", sentence: "", message: "",
  turns: 0, input: 0, output: 0, cached: 0, ...over,
});

describe("write mode: the picker cannot widen by accident", () => {
  it("offers exactly the three modes the server defines", () => {
    expect(WRITE_MODES.map((m) => m.id)).toEqual(["read-only", "fenced", "ask"]);
  });

  it("defaults to fenced, which is the narrowest mode that still lets a user work", () => {
    expect(DEFAULT_WRITE_MODE).toBe("fenced");
  });

  it("treats an unknown mode as the default, never as a wider one", () => {
    for (const junk of ["", "nonsense", "ADMIN", "true", null, undefined]) {
      expect(asWriteMode(junk as string)).toBe("fenced");
    }
  });

  it("says read-only is the only mode that cannot change anything", () => {
    expect(writeMode("read-only").mutates).toBe(false);
    expect(writeMode("fenced").mutates).toBe(true);
    expect(writeMode("ask").mutates).toBe(true);
  });

  it("warns on the chip only when nothing can change", () => {
    expect(writeModeChip("read-only").tone).toBe("warn");
    expect(writeModeChip("fenced").tone).toBe("quiet");
    expect(writeModeChip("ask").tone).toBe("quiet");
  });

  it("explains the mode in the composer before the user types", () => {
    expect(writeModeHint("read-only")).toMatch(/cannot change/);
    expect(writeModeHint("ask")).toMatch(/approval/);
    expect(writeModeHint("fenced")).toBe("");  // the default mode needs no hint
  });

  it("gives every mode a label and a sentence ending in a full stop", () => {
    for (const m of WRITE_MODES) {
      expect(m.label.length).toBeGreaterThan(0);
      expect(m.sentence.endsWith(".")).toBe(true);
    }
  });
});

describe("budget: no ceiling means no claim", () => {
  it("draws no meter when there is no limit", () => {
    expect(hasCeiling(budget())).toBe(false);
    expect(budgetLine(budget())).toBe("");
    expect(budgetFraction(budget())).toBe(0);
    expect(budgetTone(budget())).toBe("ok");
  });

  it("draws a meter and a line when there is a limit", () => {
    const b = budget({ limit: 1000, used: 250, allowed: true, verdict: "allow",
                       sentence: "250 of 1,000 tokens used (25%)" });
    expect(hasCeiling(b)).toBe(true);
    expect(budgetLine(b)).toBe("250 of 1,000 tokens used (25%)");
    expect(budgetFraction(b)).toBeCloseTo(0.25);
    expect(budgetTone(b)).toBe("ok");
  });

  it("warns from 85% but only fails when the turn is actually blocked", () => {
    expect(budgetTone(budget({ limit: 100, used: 90, allowed: true }))).toBe("warn");
    expect(budgetTone(budget({ limit: 100, used: 90, allowed: false }))).toBe("bad");
  });

  it("shows the server's blocking sentence, not one it invented", () => {
    const message = "this conversation has used 1,000 of its 1,000 token budget.";
    expect(budgetLine(budget({ limit: 1000, used: 1000, allowed: false, message }))).toBe(message);
  });

  it("clamps a fraction a server could report out of range", () => {
    expect(budgetFraction(budget({ limit: 100, used: 500 }))).toBe(1);
    expect(budgetFraction(budget({ limit: 100, used: -5 }))).toBe(0);
  });

  it("shortens token counts for a chip", () => {
    expect(tokens(0)).toBe("0");
    expect(tokens(950)).toBe("950");
    expect(tokens(1200)).toBe("1.2k");
    expect(tokens(412_000)).toBe("412k");
    expect(tokens(1_100_000)).toBe("1.1M");
    expect(tokens(Number.NaN)).toBe("0");
  });
});
