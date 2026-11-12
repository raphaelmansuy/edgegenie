import { describe, expect, it } from "vitest";
import { drawn, outputsOf, runAffordance, runPlan, type CellRun } from "./cellrun";
import { NO_SESSION, chipFor, fallbackNotice, replacedNotice, withNotice } from "./session";

const on = { enabled: true, reason: "", session: true };
const off = { enabled: true, reason: "" };
const py = (id: string, source = "x = 1") => ({ id, kind: "code", language: "python", source });
const sql = (id: string, source = "select 1") => ({ id, kind: "code", language: "sql", source });

describe("the session chip says what is true and what can be done", () => {
  it("has nothing to restart or stop before the first run", () => {
    const c = chipFor(NO_SESSION, null);
    expect(c.label).toBe("No session yet");
    expect(c.canRestart || c.canStop).toBe(false);
  });
  it("offers Stop while starting but not Restart", () => {
    const c = chipFor({ state: "starting" }, null);
    expect(c).toMatchObject({ tone: "busy", canStop: true, canRestart: false });
  });
  it("is ready, busy, and stopping in words", () => {
    expect(chipFor({ state: "idle", idleSeconds: 1200 }, null).title).toMatch(/Variables stay between cells.*20 minutes/);
    expect(chipFor({ state: "busy" }, null).label).toBe("Session running");
    expect(chipFor({ state: "stopping" }, null)).toMatchObject({ canRestart: false, canStop: false });
  });
  it("says why a session ended and that variables are gone", () => {
    const c = chipFor({ state: "ended", reason: "the session ended after being idle" }, null);
    expect(c.tone).toBe("warn");
    expect(c.title).toMatch(/^The session ended after being idle\. Variables from earlier cells are gone/);
    expect(c.canRestart).toBe(true);
  });
  it("shows the fallback, whatever the session says, because that mode forgets variables", () => {
    const c = chipFor({ state: "idle" }, "the session store could not be written");
    expect(c.label).toBe("One-shot runs");
    expect(c.title).toMatch(/do not stay between runs: the session store could not be written/);
    expect(c.canRestart).toBe(true);
  });
});

describe("what the run controls promise", () => {
  it("says variables stay between cells when there is a session, and does not when there is not", () => {
    expect(runAffordance("python", "x = 1", on).title).toMatch(/Python session.*Variables stay between cells/);
    expect(runAffordance("python", "x = 1", off).title).toMatch(/The Python cells above it run first/);
  });
  it("counts no separate Python jobs in a session, and counts them without one", () => {
    const cells = [py("a"), sql("b"), py("c")];
    expect(runPlan(cells, on).blocks).toBe(0);
    expect(runPlan(cells, off).blocks).toBe(2);
  });
});

describe("the magics that need a session", () => {
  const MAGICS = [["%sh ls", "python"], ["%pip install x", "python"], ["%run ./lib", "python"]] as const;
  it.each(MAGICS)("%s runs in a session, and says what it does", (source) => {
    const a = runAffordance("python", source, on);
    expect(a).toMatchObject({ enabled: true, engine: "python" });
    expect(a.title.length).toBeGreaterThan(20);
  });
  it.each([["shell", "ls"], ["pip", "install x"], ["run", "./lib"]])("a cell read from a file as %s runs too", (language, source) => {
    expect(runAffordance(language, source, on)).toMatchObject({ enabled: true, engine: "python" });
  });
  it("cannot run without a session, and says why", () => {
    const a = runAffordance("shell", "ls", off);
    expect(a.enabled).toBe(false);
    expect(a.title).toMatch(/%shell needs the notebook's Python session/);
    expect(runAffordance("python", "%pip install x", { enabled: false, reason: "admins only", session: false }).title)
      .toMatch(/admins only/);
  });
  it("still refuses a magic nothing can run, naming what works", () => {
    expect(runAffordance("python", "%fs ls /", on).title).toBe("%fs cells cannot run here; only SQL, Python, %sh, %pip and %run do");
  });
  it("runs a mix in Run all: shell, install and Python go to the session, SQL to the warehouse", () => {
    const cells = [
      { id: "a", kind: "code", language: "pip", source: "install x" }, { id: "b", kind: "code", language: "python", source: "x=1" },
      { id: "c", kind: "code", language: "sql", source: "select 1" }, { id: "d", kind: "code", language: "shell", source: "ls" },
    ];
    const plan = runPlan(cells, on);
    expect(plan.runnable).toEqual(["a", "b", "c", "d"]);
    expect(plan.python).toEqual(["a", "b", "d"]);
  });
});

describe("a running cell shows what it has printed so far", () => {
  const live: CellRun = {
    state: "running", seconds: 3, error: "running your cell… 3s",
    outputs: [{ type: "text", stream: "stdout", text: "50% done\n" }],
  };
  it("draws those outputs while running", () => {
    expect(drawn(live)).toEqual(live.outputs);
  });
  it("draws nothing for a run that has printed nothing yet", () => {
    expect(drawn({ state: "running", seconds: 0 })).toEqual([]);
  });
});

describe("notices go before the output", () => {
  const run: CellRun = { state: "succeeded", seconds: 1, outputs: [{ type: "text", stream: "stdout", text: "hi\n" }] };
  it("puts one sentence first, as a notice, and keeps the rest in order", () => {
    const out = outputsOf(withNotice(run, "something to know"));
    expect(out).toHaveLength(2);
    expect(out[0]).toEqual({ type: "text", stream: "notice", text: "something to know\n" });
    expect(out[1]).toMatchObject({ text: "hi\n" });
  });
  it("works on a flat result too (an older shape with only `output`)", () => {
    const out = outputsOf(withNotice({ state: "succeeded", seconds: 1, output: "old\n" }, "note"));
    expect(out.map((o) => o.type === "text" && o.stream)).toEqual(["notice", "stdout"]);
  });
  it("words the two situations", () => {
    expect(replacedNotice("the session ended after being idle")).toMatch(/new session.*idle.*gone/);
    expect(fallbackNotice("no volume")).toMatch(/one-shot.*not kept: no volume/);
  });
});
