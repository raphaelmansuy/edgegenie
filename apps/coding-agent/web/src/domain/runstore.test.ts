import { beforeEach, describe, expect, it } from "vitest";
import type { CellRun } from "./cellrun";
import {
  INTERRUPTED, KEPT_ROWS, KEY, MAX_NOTEBOOKS, MAX_NOTEBOOK_CHARS, TTL_MS, completeRun, fit, forgetRuns, hashSource,
  recallRuns, rememberRuns, resetMemory, restore, snapshot,
} from "./runstore";

const ok = (extra: Partial<CellRun> = {}): CellRun => ({ state: "succeeded", seconds: 1, ...extra });
const cells = (...sources: string[]) => sources.map((source, i) => ({ id: `c${i}`, source }));

beforeEach(() => {
  localStorage.clear();
  resetMemory();
});

describe("a result belongs to the code that produced it", () => {
  it("hashes the source the same way every time, and differently for different code", () => {
    expect(hashSource("select 1")).toBe(hashSource("select 1"));
    expect(hashSource("select 1")).not.toBe(hashSource("select 2"));
  });
  it("hands a result back to the cell with the same code, wherever that cell is now", () => {
    const before = cells("select 1", "select 2");
    const stored = snapshot(before, { c0: ok({ rows: [["1"]] }), c1: ok({ rows: [["2"]] }) });
    // A cell was inserted above: the cells moved and got other ids.
    const after = [{ id: "new", source: "select 0" }, { id: "x1", source: "select 1" }, { id: "x2", source: "select 2" }];
    const back = restore(after, stored);
    expect(back.new).toBeUndefined();
    expect(back.x1.rows).toEqual([["1"]]);
    expect(back.x2.rows).toEqual([["2"]]);
  });
  it("drops the result of a cell whose code changed", () => {
    const stored = snapshot(cells("select 1"), { c0: ok() });
    expect(restore(cells("select 1 + 1"), stored)).toEqual({});
  });
  it("gives two identical cells their own results, in order", () => {
    const stored = snapshot(cells("x", "x"), { c0: ok({ seconds: 1 }), c1: ok({ seconds: 2 }) });
    const back = restore(cells("x", "x"), stored);
    expect([back.c0.seconds, back.c1.seconds]).toEqual([1, 2]);
  });
  it("keeps only cells that have a result", () => {
    expect(snapshot(cells("a", "b", "c"), { c1: ok() })).toHaveLength(1);
  });
});

describe("a run that was in flight is not a spinner after a reload", () => {
  it("comes back as interrupted, with the words to say so", () => {
    const stored = snapshot(cells("print(1)"), { c0: { state: "running", seconds: 12, error: "waiting 12s", warehouse: "Serverless · as the app" } });
    const back = restore(cells("print(1)"), stored).c0;
    expect(back.state).toBe("cancelled");
    expect(back.error).toBe(INTERRUPTED);
    expect(back.warehouse).toBe("Serverless · as the app");
  });
});

describe("the store", () => {
  it("survives a tab switch (memory) and a reload (storage)", () => {
    rememberRuns("/a", snapshot(cells("select 1"), { c0: ok({ rows: [["1"]] }) }));
    expect(recallRuns("/a")).toHaveLength(1);
    resetMemory();                                   // a reload: memory is gone, storage is not
    expect(recallRuns("/a")?.[0].run.rows).toEqual([["1"]]);
  });
  it("keeps notebooks apart", () => {
    rememberRuns("/a", snapshot(cells("a"), { c0: ok() }));
    expect(recallRuns("/b")).toBeNull();
  });
  it("forgets a notebook whose results are all cleared", () => {
    rememberRuns("/a", snapshot(cells("a"), { c0: ok() }));
    rememberRuns("/a", []);
    expect(recallRuns("/a")).toBeNull();
    expect(localStorage.getItem(KEY + "/a")).toBeNull();
  });
  it("does not crash on a corrupt entry", () => {
    localStorage.setItem(KEY + "/bad", "{not json");
    expect(recallRuns("/bad")).toBeNull();
    localStorage.setItem(KEY + "/shape", JSON.stringify({ at: 1, runs: [{ nope: true }] }));
    expect(recallRuns("/shape")).toBeNull();
  });
  it("does not return results older than the time limit", () => {
    const now = Date.now();
    rememberRuns("/old", snapshot(cells("a"), { c0: ok() }), now - TTL_MS - 1000);
    resetMemory();
    expect(recallRuns("/old", now)).toBeNull();
  });
  it("keeps at most a set number of notebooks, dropping the oldest", () => {
    const now = Date.now();
    for (let i = 0; i < MAX_NOTEBOOKS + 3; i += 1) {
      rememberRuns(`/n${i}`, snapshot(cells("a"), { c0: ok() }), now + i);
    }
    resetMemory();
    expect(recallRuns("/n0", now + 100)).toBeNull();
    expect(recallRuns(`/n${MAX_NOTEBOOKS + 2}`, now + 100)).not.toBeNull();
  });
  it("still works when storage throws", () => {
    const real = Storage.prototype.setItem;
    Storage.prototype.setItem = () => { throw new Error("quota"); };
    try {
      expect(() => rememberRuns("/a", snapshot(cells("a"), { c0: ok() }))).not.toThrow();
      expect(recallRuns("/a")).toHaveLength(1);       // memory still carries a tab switch
    } finally {
      Storage.prototype.setItem = real;
    }
  });
  it("adds a result that arrived after the notebook was left, replacing the run that was in flight", () => {
    rememberRuns("/a", snapshot(cells("print(1)"), { c0: { state: "running", seconds: 3 } }));
    completeRun("/a", "print(1)", ok({ output: "1\n" }));
    const back = restore(cells("print(1)"), recallRuns("/a")!);
    expect(back.c0.state).toBe("succeeded");
    expect(back.c0.output).toBe("1\n");
    completeRun("/a", "other", ok());
    expect(recallRuns("/a")).toHaveLength(2);
  });
  it("forgets", () => {
    rememberRuns("/a", snapshot(cells("a"), { c0: ok() }));
    forgetRuns("/a");
    expect(recallRuns("/a")).toBeNull();
  });
});

describe("keeping within budget", () => {
  const png = "A".repeat(600_000);
  const rows = Array.from({ length: 400 }, (_, i) => ["x".repeat(200), String(i)]);

  it("leaves a small notebook exactly as it is", () => {
    const stored = snapshot(cells("a"), { c0: ok({ rows: [["1"]], columns: ["a"] }) });
    expect(fit(stored)).toBe(stored);
  });
  it("drops plots and HTML first, and says so", () => {
    const stored = snapshot(cells("a", "b"), {
      c0: ok({ outputs: [{ type: "image", png }, { type: "html", html: "<b>x</b>" }, { type: "text", stream: "stdout", text: "kept" }] }),
      c1: ok({ outputs: [{ type: "image", png }] }),
    });
    const out = fit(stored);
    expect(JSON.stringify(out).length).toBeLessThanOrEqual(MAX_NOTEBOOK_CHARS);
    const first = out[0].run.outputs!;
    expect(first.map((o) => o.type)).toEqual(["text", "text"]);
    expect(first[0]).toMatchObject({ text: "kept" });
    expect(first[1]).toMatchObject({ stream: "notice" });
  });
  it("says it in the printed text of a flat result that had a plot", () => {
    const stored = snapshot(cells("a"), { c0: ok({ output: "hi", images: [png, png] }) });
    const run = fit(stored)[0].run;
    expect(run.images).toBeUndefined();
    expect(run.output).toContain("not kept");
  });
  it("then keeps the first rows of a big table", () => {
    const ids = Array.from({ length: 12 }, (_, i) => `c${i}`);
    const stored = snapshot(cells(...ids.map((id) => `src ${id}`)), Object.fromEntries(
      ids.map((id) => [id, ok({ outputs: [{ type: "table", columns: ["a", "b"], rows }] })])));
    expect(JSON.stringify(stored).length).toBeGreaterThan(MAX_NOTEBOOK_CHARS);
    const out = fit(stored);
    expect(JSON.stringify(out).length).toBeLessThanOrEqual(MAX_NOTEBOOK_CHARS);
    const t = out[0].run.outputs![0] as { rows: unknown[]; truncated?: boolean };
    expect(t.rows).toHaveLength(KEPT_ROWS);
    expect(t.truncated).toBe(true);
  });
  it("finally drops the results furthest from the top", () => {
    const text = "y".repeat(400_000);
    const stored = snapshot(cells("a", "b", "c"), {
      c0: ok({ output: text }), c1: ok({ output: text }), c2: ok({ output: text }),
    });
    const out = fit(stored);
    expect(out.length).toBeLessThan(3);
    expect(out[0].h).toBe(hashSource("a"));
  });
});

describe("a chosen chart is kept with its result", () => {
  it("survives a snapshot and a restore", () => {
    const views = { "0": { mode: "chart" as const, spec: { kind: "line" as const, x: 0, y: 1, group: null } } };
    const run = ok({ views });
    const cells = [{ id: "c0", source: "select 1" }];
    const back = restore(cells, JSON.parse(JSON.stringify(snapshot(cells, { c0: run }))));
    expect(back.c0.views).toEqual(views);
  });
});
