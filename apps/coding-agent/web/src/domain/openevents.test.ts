/** The cross-page controls, and the mapping that makes them not-dead.
 *
 *  A read-only page cannot navigate the shell by itself, so it dispatches a window event and the shell
 *  opens the document. Two such events existed with NO listener at all — `opengenie:open-lakebase` (spec
 *  013's app page) and `opengenie:open-job` (spec 014's run page) — which is an inert control, the defect
 *  spec 011 [N5] removed. A screenshot shows a button either way, so the guard has to be this test, and it
 *  calls `docFromOpenEvent`, which is the function `App.tsx`'s listener calls too.
 */
import { describe, expect, it } from "vitest";
import { docFromOpenEvent, OPEN_EVENTS } from "./docs";

describe("cross-page controls", () => {
  it("has a mapping for every event a page dispatches", () => {
    // The two `dispatchEvent` call sites in the app. If a third is added without a row here, it is dead.
    expect(Object.keys(OPEN_EVENTS).sort())
      .toEqual(["opengenie:open-job", "opengenie:open-lakebase"]);
  });

  it("an open-lakebase event names the project", () => {
    const doc = docFromOpenEvent("opengenie:open-lakebase", "projects/pg_tickets");
    expect(doc?.kind).toBe("lakebase");
    expect(doc?.ref).toBe("projects/pg_tickets");
  });

  it("an open-job event names the job", () => {
    const doc = docFromOpenEvent("opengenie:open-job", "812345678901");
    expect(doc?.kind).toBe("job");
    expect(doc?.id).toBe("job:812345678901");
  });

  it("an event with no ref opens nothing, rather than a document named 'undefined'", () => {
    expect(docFromOpenEvent("opengenie:open-job", "")).toBeNull();
    expect(docFromOpenEvent("opengenie:open-job", "   ")).toBeNull();
    expect(docFromOpenEvent("opengenie:open-job", undefined)).toBeNull();
  });

  it("an event nobody mapped opens nothing", () => {
    expect(docFromOpenEvent("opengenie:open-typo", "1")).toBeNull();
  });
});
