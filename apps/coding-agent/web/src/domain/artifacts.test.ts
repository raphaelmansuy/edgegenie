import { describe, expect, it } from "vitest";
import { artifactsOf, wroteElsewhere } from "./artifacts";
import { makeDoc } from "./docs";

const call = (name: string, args: string, status = "completed", summary = "") => ({ name, args, status, summary });

describe("artifactsOf", () => {
  it("lists what was written before what was only read, each once", () => {
    const out = artifactsOf([{ tools: [
      call("db_dbx_read_notebook", '{"path": "/Users/a/in"}'),
      call("db_dbx_write_notebook", '{"cells": [{"source": "x', "completed", '{ "path": "/Users/a/out" }'),
      call("db_dbx_read_notebook", '{"path": "/Users/a/out"}'),
    ] }]);
    expect(out.map((a) => [a.doc.ref, a.wrote])).toEqual([["/Users/a/out", true], ["/Users/a/in", false]]);
  });
  it("ignores a call that did not finish or that names nothing openable", () => {
    expect(artifactsOf([{ tools: [call("db_dbx_write_notebook", '{"path": "/Users/a/x"}', "failed"),
      call("todowrite", "{}")] }])).toEqual([]);
  });
});

const hit = (n: string, path: string) => call(n, `{"path": "${path}"}`);
const turn = (...tools: ReturnType<typeof hit>[]) => ({ tools });

describe("wroteElsewhere", () => {
  const open = makeDoc("notebook", "/Repos/me/demo/x");
  it("reports a write to a different file when the open one was not written", () => {
    const out = wroteElsewhere([turn(hit("db_dbx_write_notebook", "/Users/me/scratch/x_with_kpi"))], open.id);
    expect(out?.docs.map((d) => d.ref)).toEqual(["/Users/me/scratch/x_with_kpi"]);
  });
  it("says nothing when the open document itself was written", () => {
    expect(wroteElsewhere([turn(hit("db_dbx_write_notebook", "/Workspace/Repos/me/demo/x"))], open.id)).toBeNull();
  });
  it("says nothing when nothing was written", () => {
    expect(wroteElsewhere([turn(hit("db_dbx_read_notebook", "/Users/me/a"))], open.id)).toBeNull();
    expect(wroteElsewhere([], open.id)).toBeNull();
  });
  it("only reports the most recent writing turn, and names it", () => {
    const out = wroteElsewhere([
      { id: "t1", ...turn(hit("db_dbx_write_notebook", "/Users/me/old")) },
      { id: "t2", ...turn(hit("db_dbx_write_notebook", "/Users/me/new")) },
    ], open.id);
    expect(out?.docs.map((d) => d.ref)).toEqual(["/Users/me/new"]);
    expect(out?.at).toBe("t2");
  });
});
