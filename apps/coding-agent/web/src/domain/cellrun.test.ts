import { describe, expect, it } from "vitest";
import {
  badge, clearAll, presentRows, runAffordance, runKey, showsImages, showsMessage, showsOutput, showsTable, spanIds, summary, toTsv, type CellRun,
} from "./cellrun";

const ok = (extra: Partial<CellRun> = {}): CellRun => ({
  state: "succeeded", seconds: 0.42, columns: ["a"], rows: [["1"]], totalRows: 1, ...extra,
});

describe("badge — one word per state, and a tone that is not colour-only", () => {
  it("names every state", () => {
    expect(badge(ok()).word).toBe("done");
    expect(badge({ state: "failed", seconds: 1 }).word).toBe("failed");
    expect(badge({ state: "running", seconds: 1 }).word).toBe("running");
    expect(badge({ state: "cancelled", seconds: 1 }).word).toBe("cancelled");
    expect(badge({ state: "refused", seconds: 0 }).word).toBe("not run");
    expect(badge(undefined).word).toBe("");
  });
  it("gives a refusal a neutral tone, not an error: we declined, nothing broke", () => {
    expect(badge({ state: "refused", seconds: 0 }).tone).toBe("muted");
    expect(badge({ state: "failed", seconds: 0 }).tone).toBe("error");
  });
});

describe("summary", () => {
  it("says rows and time on success", () => {
    expect(summary(ok())).toBe("1 row · 420ms");
    expect(summary(ok({ rows: [["1"], ["2"]], totalRows: 2 }))).toBe("2 rows · 420ms");
    expect(summary(ok({ seconds: 2.34, rows: [["1"], ["2"]], totalRows: 2 }))).toBe("2 rows · 2.3s");
  });
  it("says how much of a large result is shown", () => {
    expect(summary(ok({ rows: [["1"]], totalRows: 900, truncated: true }))).toBe("900 rows (first 1 shown) · 420ms");
  });
  it("says only the time when there is no table", () => {
    expect(summary({ state: "failed", seconds: 0.5 })).toBe("500ms");
    expect(summary(undefined)).toBe("");
  });
});

describe("what to draw", () => {
  it("draws a table only for a success with columns", () => {
    expect(showsTable(ok())).toBe(true);
    expect(showsTable({ state: "failed", seconds: 1, columns: ["a"], rows: [] })).toBe(false);
    expect(showsTable({ state: "succeeded", seconds: 1 })).toBe(false);
  });
  it("draws a message for every failure that has words", () => {
    expect(showsMessage({ state: "failed", seconds: 1, error: "[TABLE_OR_VIEW_NOT_FOUND] nope" })).toBe(true);
    expect(showsMessage({ state: "refused", seconds: 0, error: "python needs a cluster" })).toBe(true);
    expect(showsMessage(ok())).toBe(false);
  });
});

describe("runAffordance — a control that cannot act is not offered", () => {
  it("offers no run for a Python or Scala cell, and says what would work", () => {
    const py = runAffordance("python", "print(1)");
    expect(py.enabled).toBe(false);
    expect(py.title).toMatch(/SQL/);
    expect(runAffordance("python", "%scala x").enabled).toBe(false);
  });
  it("offers a run for SQL, and for %sql inside a Python notebook", () => {
    expect(runAffordance("sql", "select 1").enabled).toBe(true);
    expect(runAffordance("python", "%sql select 1").enabled).toBe(true);
  });
  it("refuses an empty cell with a reason rather than failing later", () => {
    expect(runAffordance("sql", "   ")).toEqual({ enabled: false, title: "This cell is empty" });
  });
});

describe("keys and clearing", () => {
  it("keeps an output with its cell across a reorder", () => {
    expect(runKey("/a/nb", "s1")).toBe("/a/nb::s1");
    expect(runKey("/a/nb", "s1")).not.toBe(runKey("/a/nb", "s2"));
  });
  it("clears every output in one action", () => {
    expect(clearAll({ a: ok(), b: ok() })).toEqual({});
  });
});

import { runAllLabel, runPlan } from "./cellrun";

describe("run all", () => {
  const cells = [
    { id: "a", kind: "markdown", language: "sql", source: "# title" },
    { id: "b", kind: "code", language: "sql", source: "select 1" },
    { id: "c", kind: "code", language: "python", source: "print(1)" },
    { id: "d", kind: "code", language: "sql", source: "  " },
    { id: "e", kind: "code", language: "sql", source: "select 2" },
  ];

  it("runs SQL in order, skips what cannot run and says why, and ignores prose", () => {
    const plan = runPlan(cells);
    expect(plan.runnable).toEqual(["b", "e"]);
    expect(plan.skipped.map((s) => s.id)).toEqual(["c", "d"]);
    expect(plan.skipped[0].index).toBe(2);
    expect(plan.skipped[0].reason).toMatch(/python/i);
  });

  it("the label reflects the plan before, during and after", () => {
    const plan = runPlan(cells);
    expect(runAllLabel(plan, {}, false)).toBe("2 cells can run · 2 skipped");
    expect(runAllLabel(plan, { b: { state: "running", seconds: 0 } }, true)).toBe("running 1 of 2");
    const ok = { state: "succeeded", seconds: 1 } as const;
    expect(runAllLabel(plan, { b: ok, e: ok }, false)).toBe("2 ran · 2 skipped");
    expect(runAllLabel(plan, { b: ok, e: { state: "failed", seconds: 1 } }, false)).toBe("1 ran · 1 failed · 2 skipped");
  });

  it("a notebook with nothing runnable says so instead of offering a dead button", () => {
    expect(runAllLabel(runPlan([{ id: "c", kind: "code", language: "python", source: "x" }]), {}, false))
      .toBe("no cell here can run in the app");
    expect(runAllLabel(runPlan([]), {}, false)).toBe("nothing to run");
  });
});

describe("Python cells: offered only when the server says the user may run them", () => {
  const allowed = { enabled: true, reason: "" };
  const refused = { enabled: false, reason: "only administrators can run Python, as the app" };
  it("is disabled, with the server's reason, when the user may not", () => {
    expect(runAffordance("python", "print(1)", refused)).toEqual({ enabled: false, title: refused.reason });
    expect(runAffordance("python", "print(1)").enabled).toBe(false);
  });
  it("is enabled, and says it is not as you, when allowed", () => {
    const a = runAffordance("python", "print(1)", allowed);
    expect(a.enabled && a.engine).toBe("python");
    expect(a.title).toMatch(/not as you/);
    expect(a.title).toMatch(/above it/);
  });
  it("lets %python make a cell Python in a SQL notebook, and %sql make one SQL in a Python notebook", () => {
    expect(runAffordance("sql", "%python\nprint(1)", allowed).engine).toBe("python");
    expect(runAffordance("python", "%sql\nselect 1", allowed).engine).toBe("sql");
  });
  it("still refuses what is neither", () => {
    expect(runAffordance("python", "%pip install x", allowed).enabled).toBe(false);
    expect(runAffordance("scala", "val x = 1", allowed).enabled).toBe(false);
  });
  it("leaves a %skip cell out of a batch but still lets it run on its own", () => {
    const skip = { id: "s", kind: "code", language: "sql", source: "%skip\nselect 1" };
    const plan = runPlan([
      { id: "a", kind: "code", language: "sql", source: "select 1" },
      skip,
      { id: "b", kind: "code", language: "sql", source: "select 2" },
    ]);
    expect(plan.runnable).toEqual(["a", "b"]);
    expect(plan.skipped[0].reason).toMatch(/%skip/);
    expect(runAffordance("sql", skip.source).enabled).toBe(true);
    expect(runAffordance("sql", "%skip").enabled).toBe(false);
    expect(spanIds([
      { id: "a", kind: "code", language: "sql", source: "select 1" },
      skip,
      { id: "b", kind: "code", language: "sql", source: "select 2" },
    ], undefined, 2, "above")).toEqual(["a"]);
    expect(spanIds([
      { id: "a", kind: "code", language: "sql", source: "select 1" },
      skip,
      { id: "b", kind: "code", language: "sql", source: "select 2" },
    ], undefined, 0, "below")).toEqual(["a", "b"]);
  });
  it("filters and sorts a result, with numbers as numbers and blanks last", () => {
    const rows = [["10", "b"], ["2", "a"], ["1", null]] as (string | null)[][];
    expect(presentRows(rows, { text: "b", sortCol: null, sortDir: "asc" })).toEqual([["10", "b"]]);
    expect(presentRows(rows, { text: "", sortCol: 0, sortDir: "asc" }).map((r) => r[0])).toEqual(["1", "2", "10"]);
    expect(presentRows(rows, { text: "", sortCol: 1, sortDir: "asc" }).map((r) => r[1])).toEqual(["a", "b", null]);
    expect(toTsv(["h"], [["a\nb"]])).toBe("h\na b");
  });
  it("plans Python cells as their own group, in notebook order", () => {
    const plan = runPlan([
      { id: "a", kind: "code", language: "python", source: "x = 1" },
      { id: "b", kind: "code", language: "sql", source: "select 1" },
      { id: "c", kind: "code", language: "python", source: "x" },
    ], allowed);
    expect(plan.runnable).toEqual(["a", "b", "c"]);
    expect(plan.python).toEqual(["a", "c"]);
  });
  it("shows printed output only when there is some and the run is not in flight", () => {
    expect(showsOutput({ state: "succeeded", seconds: 1, output: "hi\n" })).toBe(true);
    expect(showsOutput({ state: "succeeded", seconds: 1, output: "  \n" })).toBe(false);
    expect(showsOutput({ state: "running", seconds: 1, output: "hi" })).toBe(false);
    expect(showsOutput({ state: "failed", seconds: 1, output: "partial\n", error: "boom" })).toBe(true);
  });
  it("shows plots when the run carries PNG images", () => {
    expect(showsImages({ state: "succeeded", seconds: 1, images: ["aaa"] })).toBe(true);
    expect(showsImages({ state: "succeeded", seconds: 1, images: [] })).toBe(false);
    expect(showsImages({ state: "running", seconds: 1, images: ["aaa"] })).toBe(false);
  });
  it("names a plot in the summary so a figure-only cell is not just a duration", () => {
    expect(summary({ state: "succeeded", seconds: 25.5, images: ["aaa"] })).toBe("1 plot · 25.5s");
    expect(summary({ state: "succeeded", seconds: 1.2, images: ["a", "b"] })).toBe("2 plots · 1.2s");
  });
});
