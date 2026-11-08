import { describe, expect, it } from "vitest";
import { emptySession, reduce, toolState } from "./events";

describe("toolState", () => {
  it("maps the protocol's words to the card's three states", () => {
    expect(toolState("completed")).toBe("completed");
    expect(toolState("failed")).toBe("error");
    expect(toolState("error")).toBe("error");
    expect(toolState("in_progress")).toBe("running");
    expect(toolState("running")).toBe("running");
    expect(toolState(undefined)).toBe("running");
  });
  it("a failed call no longer spins under a finished turn", () => {
    let s = emptySession("s");
    s = reduce(s, { seq: 1, sessionId: "s", type: "turn.started", turnId: "t", prompt: "go" });
    s = reduce(s, { seq: 2, sessionId: "s", type: "tool_call.started", turnId: "t", callId: "c", name: "run" });
    s = reduce(s, { seq: 3, sessionId: "s", type: "tool_call.updated", turnId: "t", callId: "c", status: "failed", summary: "denied" });
    expect(s.turns[0].tools[0].status).toBe("error");
  });
});

import { touched } from "./docs";
describe("touched: the path may only be in the result", () => {
  it("finds a write's path in its answer when the arguments were cut before it", () => {
    const args = '{"cells": [{"source": "# Calculating Pi using the Leibniz Formula\\n\\nThe Leibniz formula for $\\\\pi$ is:\\n$$\\\\pi = 4 \\\\times';
    const result = '{ "path": "/Users/me@x.com/agent_scratch/calculate_pi_leibniz", "object_id": 1, "cells": 2 }';
    expect(touched("db_dbx_write_notebook", args)).toBeNull();
    const hit = touched("db_dbx_write_notebook", args, result);
    expect(hit?.doc.ref).toBe("/Users/me@x.com/agent_scratch/calculate_pi_leibniz");
    expect(hit?.mutates).toBe(true);
  });
});

import { tablesWritten } from "./docs";
describe("tablesWritten", () => {
  it("names the tables a SQL call changed, and nothing for a read", () => {
    expect(tablesWritten("dbxnb_dbx_run_sql", '{"sql": "CREATE OR REPLACE TABLE main.agent.Trips AS select 1"}')).toEqual(["main.agent.trips"]);
    expect(tablesWritten("run_sql", '{"sql": "insert into `main`.`s`.`t` values (1)"}')).toEqual(["main.s.t"]);
    expect(tablesWritten("run_sql", '{"sql": "select * from main.s.t"}')).toEqual([]);
    expect(tablesWritten("write_notebook", '{"sql": "insert into a.b.c"}')).toEqual([]);
  });
});
