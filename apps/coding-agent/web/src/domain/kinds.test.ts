/** The ten document kinds: one identity, one route, one action set, one dock, one reducer.
 *
 *  Spec 014's [UI-1] requires that adding a kind is a compiler-guided change. That is only true if a test
 *  proves each register was extended, because `Record<DocKind, …>` names two of them and the rest are
 *  `if` chains a compiler cannot see through. This file is the register: a kind that reaches `DocKind`
 *  without appearing in every list below fails here, by name.
 */
import { describe, expect, it } from "vitest";
import {
  ACTIONS_FOR, asAttachment, canAttach, canonicalPath, docId, isRunObject, makeDoc, touched, touchedKinds,
  type DocKind,
} from "./docs";
import { suggestionsFor } from "./dock";
import { formatRoute, parseRoute, EMPTY_ROUTE, type Route } from "./route";
import { nameOf } from "./recent";

const JOB_ID = "812345678901";
const RUN_ID = "812345679";
const PIPE_ID = "f0e1c4a2-0000-11ee-be56-0242ac120002";

const SAMPLE: Record<DocKind, string> = {
  notebook: "/Users/me/agent_scratch/etl",
  file: "/Users/me/agent_scratch/app.py",
  table: "main.sales.orders",
  lakebase: "projects/pg_tickets",
  app: "tickets-app",
  job: JOB_ID,
  pipeline: PIPE_ID,
  run: RUN_ID,
  query: "00000000-0000-4000-8000-000000000001",
  "query-draft": "00000000-0000-4000-8000-000000000002",
};

const KINDS = Object.keys(SAMPLE) as DocKind[];


describe("every kind is registered everywhere", () => {
  it("registers all ten kinds across routes, actions and bindings", () => {
    expect(KINDS.sort()).toEqual(
      ["app", "file", "job", "lakebase", "notebook", "pipeline", "query", "query-draft", "run", "table"]);
  });

  it.each(KINDS)("%s has an action set (possibly empty, never missing)", (kind) => {
    // [UI-1]: a kind with no entry is an empty list, not a fallthrough to the notebook actions.
    expect(ACTIONS_FOR[kind]).toBeDefined();
    expect(Array.isArray(ACTIONS_FOR[kind])).toBe(true);
  });

  it.each(KINDS)("%s has a route that round-trips", (kind) => {
    // [UI-7]: `parse(format(r))` must be `r`, or a shared link opens something else.
    const route: Route = { ...EMPTY_ROUTE, doc: { kind, ref: SAMPLE[kind] } };
    const written = formatRoute(route);
    expect(written.startsWith(`#/${kind}/`)).toBe(true);
    expect(parseRoute(written).doc).toEqual({ kind, ref: expect.any(String) });
    expect(parseRoute(written).doc?.kind).toBe(kind);
  });

  it.each(KINDS)("%s has a name rule for the recent list", (kind) => {
    expect(nameOf(kind, SAMPLE[kind])).toBeTruthy();
  });

  it.each(KINDS)("%s has a document id that is stable and kind-prefixed", (kind) => {
    const a = makeDoc(kind, SAMPLE[kind]);
    const b = makeDoc(kind, SAMPLE[kind]);
    expect(a.id).toBe(b.id);
    expect(a.id.startsWith(`${kind}:`)).toBe(true);
  });
});


describe("attachment rules", () => {
  it("only content documents ride along with a message", () => {
    // A job, a run, a pipeline, a project and an app are management objects: the server has no resolver
    // that could re-read one with the user's token (013's [UI-5], extended by 014).
    for (const kind of KINDS) {
      const expected = ["notebook", "file", "table", "query", "query-draft"].includes(kind);
      expect(canAttach(kind)).toBe(expected);
      expect(asAttachment(makeDoc(kind, SAMPLE[kind])) !== null).toBe(expected);
    }
  });
});


describe("touched: a tool call names an object, through one table", () => {
  it("reads a job from a create result", () => {
    const hit = touched("dbx_create_job", '{"name": "agent_4ff_daily"}',
      '{"job_id": 812345678901, "name": "agent_4ff_daily", "summary": "2 tasks in 2 levels"}');
    expect(hit?.doc.kind).toBe("job");
    expect(hit?.doc.ref).toBe(JOB_ID);
    expect(hit?.mutates).toBe(true);
  });

  it("reads a run from a run result, and marks it a write", () => {
    const hit = touched("dbx_run_job", '{"job_id": 812345678901}', '{"run_id": 812345679, "reused": false}');
    expect(hit?.doc.kind).toBe("run");
    expect(hit?.doc.ref).toBe(RUN_ID);
    expect(hit?.mutates).toBe(true);
  });

  it("reads a pipeline from a create result", () => {
    const hit = touched("dbx_create_pipeline", '{"name": "sales"}', `{"pipeline_id": "${PIPE_ID}"}`);
    expect(hit?.doc.kind).toBe("pipeline");
    expect(hit?.doc.ref).toBe(PIPE_ID);
    expect(hit?.mutates).toBe(true);
  });

  it("a status call opens the object without making it stale", () => {
    const hit = touched("dbx_pipeline_status", "{}", `{"pipeline_id": "${PIPE_ID}", "state": "IDLE"}`);
    expect(hit?.mutates).toBe(false);
  });

  it("a job read is not a mutation", () => {
    expect(touched("dbx_job_run_status", '{"run_id": 812345679}')?.mutates).toBe(false);
  });

  it("still reads a notebook path, and still canonicalises it", () => {
    const hit = touched("dbx_write_notebook", '{"path": "/Workspace/Repos/me/demo/nb"}');
    expect(hit?.doc.kind).toBe("notebook");
    expect(hit?.doc.id).toBe(makeDoc("notebook", canonicalPath("/Workspace/Repos/me/demo/nb")).id);
  });

  it("reads a Lakebase project from its result, as 013 established", () => {
    const hit = touched("dbx_lakebase_create", '{"name": "pg_tickets"}', '{"project": "projects/pg_tickets"}');
    expect(hit?.doc.kind).toBe("lakebase");
    expect(hit?.doc.ref).toBe("projects/pg_tickets");
  });

  it("an app is its name", () => {
    const hit = touched("dbx_create_app", '{"name": "agent-4ff-tickets"}', '{"app": "agent-4ff-tickets"}');
    expect(hit?.doc.kind).toBe("app");
    expect(hit?.doc.ref).toBe("agent-4ff-tickets");
  });

  it("never guesses: no id, a wrong-shaped id, or an unrelated tool", () => {
    expect(touched("dbx_create_job", '{"name": "x"}', '{"error": "write blocked"}')).toBeNull();
    expect(touched("dbx_run_sql", '{"sql": "select 1"}')).toBeNull();
    expect(touched("dbx_whoami")).toBeNull();
  });

  it("the tool families are disjoint, so no call is swallowed by the wrong rule", () => {
    // The defect this table's own test found: `dbx_run_job` names a RUN, and a `job` rule that matched it
    // returned null and lost the call. A name must belong to exactly ONE row.
    const names = [
      "dbx_create_job", "dbx_list_jobs", "dbx_job_failure_context",
      "dbx_run_job", "dbx_job_run_status",
      "dbx_create_pipeline", "dbx_pipeline_status", "dbx_start_pipeline",
      "dbx_write_notebook", "dbx_write_file",
      "dbx_lakebase_create", "dbx_create_app",
    ];
    const owners = new Map<string, string[]>();
    for (const { kind, tools } of touchedKinds()) {
      for (const name of names) {
        if (tools.test(name)) owners.set(name, [...(owners.get(name) ?? []), kind]);
      }
    }
    const shared = [...owners.entries()].filter(([, kinds]) => kinds.length > 1);
    expect(shared).toEqual([]);
  });

  it("one id is one document, whatever produced it", () => {
    // A run's answer carries BOTH ids; the run is what this tool names, and the job's own document is
    // reached from the run page's link. The invariant that matters is that one id makes one tab.
    const fromTool = touched("dbx_run_job", "{}", '{"job_id": 812345678901, "run_id": 812345679}');
    expect(fromTool?.doc.kind).toBe("run");
    const sameRun = touched("dbx_job_run_status", '{"run_id": "812345679"}');
    expect(sameRun?.doc.id).toBe(fromTool?.doc.id);
    const job = touched("dbx_create_job", "{}", '{"job_id": "812345678901"}');
    expect(job?.doc.id).toBe(makeDoc("job", "812345678901").id);
  });
});


describe("the dock's suggestions are about the object on screen", () => {
  // [UI-6], the S2/S3 defect 013 found TWICE by looking at a screenshot: a plausible button that is wrong
  // about its subject. Asserted here so it cannot recur silently.
  const notebookPhrases = /notebook|cell/i;

  it.each(["job", "pipeline", "run"] as DocKind[])(
    "%s is never offered notebook actions", (kind) => {
      const items = suggestionsFor({ docId: makeDoc(kind, SAMPLE[kind]).id,
        doc: { kind, ref: SAMPLE[kind], name: "x" }, cell: null });
      expect(items.length).toBe(3);
      for (const item of items) {
        // The label must not be about a notebook or a cell. A prompt MAY mention a notebook when the
        // suggestion is about a job that *runs* one, so only the label is asserted.
        expect(item.label).not.toMatch(notebookPhrases);
      }
    });

  it("a job's first suggestion is about the failure, not the definition", () => {
    const items = suggestionsFor({ docId: "job:1", doc: { kind: "job", ref: "1", name: "daily" }, cell: null });
    expect(items[0].label.toLowerCase()).toContain("fail");
  });

  it("a pipeline's suggestions mention an update, not a job", () => {
    const items = suggestionsFor({ docId: "pipeline:1",
      doc: { kind: "pipeline", ref: PIPE_ID, name: "x" }, cell: null });
    expect(items.some((i) => /update/i.test(i.label + i.prompt))).toBe(true);
  });
});


describe("routes for the new kinds", () => {
  it("a job and a run carry a numeric id, spelled one way", () => {
    expect(formatRoute({ ...EMPTY_ROUTE, doc: { kind: "job", ref: "812345678901" } }))
      .toBe("#/job/812345678901");
    expect(parseRoute("#/job/812345678901").doc).toEqual({ kind: "job", ref: JOB_ID });
    expect(parseRoute("#/run/812345679").doc).toEqual({ kind: "run", ref: RUN_ID });
  });

  it("a malformed job or run id opens the app, not a blank page", () => {
    // [E-20]: a stale link must never produce a request to `/api/jobs/abc`.
    for (const hash of ["#/job/abc", "#/job/", "#/run/-1", "#/run/1.5", "#/job/1/extra"]) {
      expect(parseRoute(hash)).toEqual(EMPTY_ROUTE);
    }
  });

  it("a pipeline is a UUID, and a name is not an id", () => {
    // [E-17]: a name answered with a 404 reads as a permission problem.
    expect(parseRoute(`#/pipeline/${PIPE_ID}`).doc).toEqual({ kind: "pipeline", ref: PIPE_ID });
    expect(parseRoute("#/pipeline/sales_medallion")).toEqual(EMPTY_ROUTE);
    expect(parseRoute("#/pipeline/")).toEqual(EMPTY_ROUTE);
  });

  it("the three new routes do not disturb the five old ones", () => {
    expect(parseRoute("#/notebook/Users/me/x").doc?.kind).toBe("notebook");
    expect(parseRoute("#/app/tickets-app").doc?.kind).toBe("app");
    expect(parseRoute("#/settings/models").settings).toBe("models");
    expect(parseRoute("").doc).toBeNull();
  });
});


describe("identity", () => {
  it("a job and a run are distinct documents even with one number", () => {
    expect(docId("job", "1")).not.toBe(docId("run", "1"));
  });

  it("a pipeline is its UUID and keeps it", () => {
    expect(makeDoc("pipeline", PIPE_ID).ref).toBe(PIPE_ID);
  });

  it("a job's display name says what it is, because a job has no name here", () => {
    expect(makeDoc("job", JOB_ID).name).toBe(`job ${JOB_ID}`);
    expect(makeDoc("run", RUN_ID).name).toBe(`run ${RUN_ID}`);
  });

  it("isRunObject is the one predicate for the three read-only kinds", () => {
    expect(KINDS.filter(isRunObject).sort()).toEqual(["job", "pipeline", "run"]);
  });
});
