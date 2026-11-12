/** The scaffold's step table, mirrored from the same JSON the server reads.
 *
 * These are the TypeScript half of `tests/test_scaffold.py`: the same cases, so the two runtimes
 * cannot disagree about what a proof is (spec 013 [07 §2.1]).
 */
import { compute, progress, focusStep, proved, STEPS, type Call } from "./scaffold";

const done = (name: string, fields: Record<string, unknown>): Call =>
  ({ name, status: "completed", result: JSON.stringify(fields) });

const byKey = (rows: ReturnType<typeof compute>) =>
  Object.fromEntries(rows.map((r) => [r.key, r]));

test("there are seven steps, in the order the card implies", () => {
  expect(STEPS.map((s) => s.key)).toEqual(
    ["project", "branch", "table", "resource", "files", "deploy", "verify"]);
});

test("every step names a proof field", () => {
  for (const s of STEPS) expect(s.proof).toBeTruthy();
});

test("a full chain proves every step", () => {
  const calls = [
    done("dbx_lakebase_create", { project: "projects/pg" }),
    done("dbx_lakebase_branch", { branch: "projects/pg/branches/a" }),
    done("dbx_lakebase_sql", { ok: true, row_count: 12 }),
    done("dbx_create_app", { resources: ["postgres"], deploy_http_status: 200 }),
    done("dbx_write_file", { bytes: 1200 }),
    done("dbx_app_health", { status: 200 }),
  ];
  expect(compute(calls).every((o) => o.state === "done")).toBe(true);
  expect(byKey(compute(calls)).table.proof).toBe("12");
});

test("a completed call without the proof field does not prove the step", () => {
  // [E-9] `{"ok": true}` is the DDL's status, not the table's existence.
  expect(byKey(compute([done("dbx_lakebase_sql", { ok: true })])).table.state).toBe("pending");
});

test("a SELECT's rows are a proof", () => {
  const calls = [{ name: "dbx_lakebase_sql", status: "completed",
    result: JSON.stringify({ columns: ["count"], rows: [["12"]], row_count: 1 }) }];
  expect(byKey(compute(calls)).table.proof).toBe("12");
});

test("an error is never a proof, even with the field present", () => {
  const calls = [{ name: "dbx_lakebase_create", status: "error",
    result: JSON.stringify({ project: "projects/x", error: "denied" }) }];
  expect(byKey(compute(calls)).project.state).toBe("blocked");
});

test("an app without the postgres resource does not tick the resource step", () => {
  // [F6] this is the defect itself
  expect(byKey(compute([done("dbx_create_app", { resources: [] })])).resource.state)
    .not.toBe("done");
});

test("a 5xx deployment is not a proof", () => {
  const calls = [done("dbx_create_app", { resources: ["postgres"], deploy_http_status: 500 })];
  expect(byKey(compute(calls)).deploy.state).not.toBe("done");
});

test("a blocked step stops every later step that has no proof", () => {
  // [SCF-2], [E-8]
  const calls = [
    done("dbx_lakebase_create", { project: "projects/pg" }),
    done("dbx_lakebase_branch", { branch: "projects/pg/branches/a" }),
    { name: "dbx_lakebase_sql", status: "error", result: JSON.stringify({ error: "denied" }) } as Call,
  ];
  const rows = byKey(compute(calls));
  expect(rows.table.state).toBe("blocked");
  expect(rows.table.reason).toContain("denied");
  expect(rows.resource.state).toBe("pending");
  expect(rows.resource.reason).toContain("table");
});

test("a step proved after a block is done, and says so", () => {
  const calls = [
    { name: "dbx_lakebase_sql", status: "error", result: JSON.stringify({ error: "denied" }) } as Call,
    done("dbx_create_app", { resources: ["postgres"], deploy_http_status: 200 }),
  ];
  const rows = byKey(compute(calls));
  expect(rows.resource.state).toBe("done");
  expect(rows.resource.reason).toContain("blocked");
});

test("a running step is running, not blocked", () => {
  expect(byKey(compute([{ name: "dbx_lakebase_create", status: "running" }])).project.state)
    .toBe("running");
});

test("a repeated proof keeps one row and the latest value", () => {
  // [E-10]
  const calls = [done("dbx_lakebase_create", { project: "projects/first" }),
                 done("dbx_lakebase_create", { project: "projects/second" })];
  const rows = compute(calls);
  expect(rows.filter((o) => o.key === "project")).toHaveLength(1);
  expect(byKey(rows).project.proof).toBe("projects/second");
});

test("matching is linear in calls plus steps", () => {
  // [06 §6.4] this runs on every streamed token
  const filler = done("dbx_run_sql", { rows: [["1"]], row_count: 1 });
  const calls = Array.from({ length: 2000 }, () => filler);
  const started = performance.now();
  compute(calls);
  expect(performance.now() - started).toBeLessThan(50);
});

test("progress counts proven steps", () => {
  const calls = [done("dbx_lakebase_create", { project: "projects/p" })];
  expect(progress(compute(calls))).toEqual({ done: 1, total: 7 });
});

test("the step needing attention is a blocked one first", () => {
  const calls = [
    { name: "dbx_lakebase_create", status: "running" } as Call,
    { name: "dbx_lakebase_branch", status: "error", result: "{}" } as Call,
  ];
  expect(focusStep(compute(calls))?.key).toBe("branch");
});

test("proved() ignores a call to a tool the step does not accept", () => {
  expect(proved(STEPS[0], done("dbx_run_sql", { project: "x" }))).toBe("");
});
