import { describe, expect, it } from "vitest";
import { makeDoc } from "./docs";
import { focusFor, NO_FOCUS, withCell } from "./focus";
import { searchRoot } from "./searchroot";

const home = "/Users/a@b.com";
const session = "/Users/a@b.com/agent_scratch";

describe("searchRoot", () => {
  it("starts from the open document's folder — that is where its neighbours are", () => {
    const f = focusFor(makeDoc("file", "/Shared/finance/q3.py"));
    expect(searchRoot(f, session, home)).toBe("/Shared/finance");
  });
  it("falls back to the session folder when nothing is open", () => {
    expect(searchRoot(NO_FOCUS, session, home)).toBe(session);
  });
  it("falls back to home when there is no session either", () => {
    expect(searchRoot(NO_FOCUS, "", home)).toBe(home);
  });
  it("a table has no folder, so the session folder is used", () => {
    const f = focusFor(makeDoc("table", "main.s.t"));
    expect(searchRoot(f, session, home)).toBe(session);
  });
  it("a selected cell does not change the root", () => {
    const f = withCell(focusFor(makeDoc("notebook", "/Repos/a/demo/nb")), 2);
    expect(searchRoot(f, session, home)).toBe("/Repos/a/demo");
  });
});
