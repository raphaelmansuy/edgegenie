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

import { drawn, numericColumns, outputsOf, truncationNote, typeGlyph, whenRan } from "./cellrun";

describe("ordered outputs", () => {
  const table = (rows: string[][], extra = {}) => ({ type: "table" as const, columns: ["a"], rows, ...extra });

  it("draws a Python cell's outputs in the order it produced them", () => {
    const run: CellRun = { state: "succeeded", seconds: 1, outputs: [
      { type: "text", stream: "stdout", text: "one\n" }, table([["1"]]),
      { type: "text", stream: "stderr", text: "warn\n" }, table([["2"]]),
    ] };
    expect(outputsOf(run).map((o) => o.type)).toEqual(["text", "table", "text", "table"]);
    expect(drawn(run)).toHaveLength(4);
  });
  it("draws a SQL run's flat fields as text, plots, then the table", () => {
    const run: CellRun = { state: "succeeded", seconds: 1, output: "OK", images: ["x"], columns: ["a"], rows: [["1"]] };
    expect(outputsOf(run).map((o) => o.type)).toEqual(["text", "image", "table"]);
  });
  it("draws nothing while the run is still going", () => {
    expect(drawn({ state: "running", seconds: 0, output: "partial" })).toEqual([]);
  });
  it("keeps what a failed cell produced before it failed", () => {
    const run: CellRun = { state: "failed", seconds: 1, error: "boom",
      outputs: [{ type: "text", stream: "stdout", text: "before\n" }] };
    expect(drawn(run)).toHaveLength(1);
    expect(showsOutput(run)).toBe(true);
  });
  it("counts tables and plots from the ordered outputs", () => {
    const one: CellRun = { state: "succeeded", seconds: 0.2, outputs: [table([["1"], ["2"]])] };
    expect(summary(one)).toBe("2 rows · 200ms");
    const two: CellRun = { state: "succeeded", seconds: 2, outputs: [table([["1"]]), table([["1"]]), { type: "image", png: "a" }] };
    expect(summary(two)).toBe("2 tables · 1 plot · 2.0s");
    expect(showsTable(two)).toBe(true);
    expect(showsImages(two)).toBe(true);
  });
  it("says how many rows were cut from a truncated table", () => {
    const rows = Array.from({ length: 1000 }, (_, i) => [String(i)]);
    expect(summary({ state: "succeeded", seconds: 1, outputs: [table(rows, { truncated: true })] }))
      .toBe("1,000 rows (first 1,000 shown) · 1.0s");
  });
});

describe("the sentence under a table that was cut", () => {
  it("names the cap, and the total when the engine said it", () => {
    expect(truncationNote(1000)).toBe("Showing the first 1,000 rows");
    expect(truncationNote(1000, 25_000)).toBe("Showing the first 1,000 of 25,000 rows");
    expect(truncationNote(1000, 900)).toBe("Showing the first 1,000 rows");
  });
});

describe("whenRan — who and when, as Databricks prints under a command", () => {
  const ran: CellRun = { state: "succeeded", seconds: 1, ranBy: "a@x.com", finishedAt: "2026-11-12T00:02:11+00:00" };
  const now = new Date("2026-11-12T05:00:00Z");
  it("says the time only when it was today", () => {
    expect(whenRan(ran, now, "UTC")).toBe("by a@x.com at 12:02:11 AM");
  });
  it("says the date when it was another day", () => {
    expect(whenRan(ran, new Date("2026-11-14T05:00:00Z"), "UTC")).toBe("by a@x.com on 2026-11-12 at 12:02:11 AM");
  });
  it("says what it knows and nothing more", () => {
    expect(whenRan({ state: "succeeded", seconds: 1, ranBy: "a@x.com" }, now)).toBe("by a@x.com");
    expect(whenRan({ state: "succeeded", seconds: 1, finishedAt: "not a date" }, now)).toBe("");
    expect(whenRan(undefined)).toBe("");
  });
  it("says nothing while it is running", () => {
    expect(whenRan({ ...ran, state: "running" }, now)).toBe("");
  });
});

describe("numeric columns — the engine's type decides, not the look of the text", () => {
  it("right-aligns number types and not a text column of digits", () => {
    const rows = [["1", "10001"], ["2", "94105"]];
    expect(numericColumns(["id", "zip"], rows, ["int", "string"])).toEqual([true, false]);
    expect(numericColumns(["a"], [["1.5"]], ["decimal"])).toEqual([true]);
  });
  it("falls back to the text only when no type came back, and only if every cell looks numeric", () => {
    expect(numericColumns(["a", "b"], [["1", "x"], ["2", "3"]])).toEqual([true, false]);
    expect(numericColumns(["a"], [[null], [""]])).toEqual([false]);
    expect(numericColumns(["a"], [["1"], [null], ["3"]])).toEqual([true]);
  });
  it("marks the header with a glyph for the type", () => {
    expect(typeGlyph("bigint")).toBe("123");
    expect(typeGlyph("string")).toBe("abc");
    expect(typeGlyph("timestamp_ntz")).toBe("date");
    expect(typeGlyph("struct")).toBe("");
    expect(typeGlyph(undefined)).toBe("");
  });
});

import { segments } from "./cellrun";

describe("Run all goes top to bottom, one engine at a time", () => {
  const allowed = { enabled: true, reason: "" };
  const cell = (id: string, language: string, source = "x") => ({ id, kind: "code", language, source });

  it("keeps a notebook's Python together as one job when no SQL sits between", () => {
    const cells = [cell("a", "python"), cell("b", "python"), cell("c", "sql", "select 1"), cell("d", "sql", "select 2")];
    const ids = runPlan(cells, allowed).runnable;
    expect(segments(cells, ids, allowed)).toEqual([
      { engine: "python", ids: ["a", "b"] }, { engine: "sql", ids: ["c", "d"] }]);
    expect(runPlan(cells, allowed).blocks).toBe(1);
  });
  it("splits at the SQL cell between two Python cells, so the SQL cell cannot race the Python above it", () => {
    const cells = [cell("a", "python"), cell("b", "sql", "select 1"), cell("c", "python")];
    expect(segments(cells, ["a", "b", "c"], allowed).map((s) => s.engine)).toEqual(["python", "sql", "python"]);
    const plan = runPlan(cells, allowed);
    expect(plan.blocks).toBe(2);
    expect(runAllLabel(plan, {}, false)).toBe("3 cells can run · Python runs in 2 jobs, SQL is in between");
  });
  it("puts the cells in notebook order whatever order the ids arrive in", () => {
    const cells = [cell("a", "sql", "select 1"), cell("b", "python"), cell("c", "sql", "select 2")];
    expect(segments(cells, ["c", "a", "b"], allowed).map((s) => s.ids)).toEqual([["a"], ["b"], ["c"]]);
  });
  it("leaves out cells that cannot run, markdown and cells the caller did not ask for", () => {
    const cells = [cell("a", "python"), { id: "m", kind: "markdown", language: "markdown", source: "# hi" },
      cell("s", "scala"), cell("b", "python")];
    expect(segments(cells, ["a", "m", "s", "b"], allowed)).toEqual([{ engine: "python", ids: ["a", "b"] }]);
    expect(segments(cells, ["b"], allowed)).toEqual([{ engine: "python", ids: ["b"] }]);
  });
  it("runs no Python when the server says Python is off", () => {
    const cells = [cell("a", "python"), cell("b", "sql", "select 1")];
    expect(segments(cells, ["a", "b"], { enabled: false, reason: "no" }).map((s) => s.engine)).toEqual(["sql"]);
  });
});
