/** Lakebase identity and the capacity rule, mirrored from the Python module.
 *
 * The same cases as `tests/test_lakebase_tools.py`, so the page and the tool server cannot disagree
 * about what a range is legal or what one project is called (spec 013 [07 §2.1], [LB-4], [LB-5]).
 */
import {
  branchId, branchRef, describeRange, endpointRef, isError, isReady, isSuspended,
  lakebaseUrl, orDash, projectId, projectRef, rangeProblem, rangeValid, stateWord,
} from "./lakebase";

describe("project identity", () => {
  it("gives one project one key however it is spelled", () => {
    // [LB-5], [E-24]
    expect(projectRef("pg_tickets")).toBe("projects/pg_tickets");
    expect(projectRef("projects/pg_tickets")).toBe("projects/pg_tickets");
    expect(projectRef("/projects/pg_tickets/")).toBe("projects/pg_tickets");
    expect(projectId("projects/pg_tickets")).toBe("pg_tickets");
  });

  it("refuses an empty project rather than rooting it", () => {
    expect(() => projectRef("   ")).toThrow();
  });

  it("builds and reads a branch ref", () => {
    expect(branchRef("pg_tickets", "production")).toBe("projects/pg_tickets/branches/production");
    expect(branchRef("projects/pg_tickets", "agent-9")).toBe("projects/pg_tickets/branches/agent-9");
    expect(branchId("projects/pg_tickets/branches/agent-9")).toBe("agent-9");
    expect(branchId("agent-9")).toBe("agent-9");
  });

  it("names the endpoint a credential is minted for", () => {
    expect(endpointRef("pg_tickets", "production"))
      .toBe("projects/pg_tickets/branches/production/endpoints/primary");
  });
});

describe("the autoscaling rule", () => {
  it.each([
    [0.5, 16.5, false, true],
    [0.5, 16.51, false, false],
    [48, 64, false, true],
    [8, 24, false, true],
    [8, 24.1, false, false],
    [0.4, 4, false, false],
    [2, 66, false, false],
    [8, 4, false, false],
    [0.5, 16, true, true],
    [16, 32, true, true],
    [32, 48, true, false],
  ])("%s → %s (zero=%s) is %s", (minCu, maxCu, scaleToZero, valid) => {
    // [LB-4], [E-7] max − min ≤ 16, 0.5 ≤ min, max ≤ 64, zero only when max ≤ 32
    expect(rangeValid({ minCu, maxCu, scaleToZero })).toBe(valid);
  });

  it("names the number and the fix in the problem", () => {
    const problem = rangeProblem({ minCu: 0.5, maxCu: 32, scaleToZero: false });
    expect(problem).toContain("16");
    expect(problem).toContain("31.5");
    expect(problem).toContain("at most 16.5");
  });

  it("describes itself the way the page shows it", () => {
    // the string in wireframe S2
    const text = describeRange({ minCu: 0.5, maxCu: 4, scaleToZero: false });
    expect(text).toContain("0.5 – 4 CU");
    expect(text).toContain("max − min = 3.5");
    expect(text).toContain("✓");
  });
});

describe("state words", () => {
  it.each([
    ["READY", "ready"], ["AVAILABLE", "ready"], ["PROVISIONING", "starting"],
    ["SUSPENDED", "asleep"], ["FAILED", "failed"], ["SOMETHING_NEW", "something_new"],
  ])("%s reads as %s", (raw, word) => {
    expect(stateWord(raw)).toBe(word);
    expect(isReady(raw)).toBe(word === "ready");
  });

  it("calls a suspended compute a state, not a failure", () => {
    // [RB-7] a connection resumes it
    expect(isSuspended("SUSPENDED")).toBe(true);
    expect(isReady("SUSPENDED")).toBe(false);
  });
});

describe("page helpers", () => {
  it("shows an em dash for a value that could not be read, never a zero", () => {
    // [UI-3], [E-11]
    expect(orDash(undefined)).toBe("—");
    expect(orDash(null)).toBe("—");
    expect(orDash("")).toBe("—");
    expect(orDash(0)).toBe("0");
    expect(orDash("x")).toBe("x");
  });

  it("recognises a block that failed", () => {
    expect(isError({ error: "denied" })).toBe(true);
    expect(isError([])).toBe(false);
    expect(isError(undefined)).toBe(false);
  });

  it("links to the project's page when the host is known", () => {
    expect(lakebaseUrl("https://h.cloud.databricks.com/", "projects/pg"))
      .toBe("https://h.cloud.databricks.com/database/projects/pg");
    expect(lakebaseUrl(null, "projects/pg")).toBeNull();
  });
});
