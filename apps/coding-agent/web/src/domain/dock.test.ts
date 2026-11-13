import { describe, expect, it } from "vitest";
import { announce, dockState, dockStateWord, dockTitle, suggestionsFor, type DockInput } from "./dock";
import { makeDoc } from "./docs";
import { focusFor, NO_FOCUS, withCell } from "./focus";

const at = (extra: Partial<DockInput> = {}): DockInput => ({
  hasSession: true, status: "ready", last: { status: "completed" }, pendingApprovals: 0, ...extra,
});

describe("dockState — four states, with a stated precedence", () => {
  it("is empty with no session", () => {
    expect(dockState({ hasSession: false, status: "", last: null, pendingApprovals: 0 })).toBe("empty");
  });
  it("is empty after a completed turn: ready for the next prompt", () => {
    expect(dockState(at())).toBe("empty");
  });
  it("is streaming while the session runs", () => {
    expect(dockState(at({ status: "streaming" }))).toBe("streaming");
    expect(dockState(at({ last: { status: "running" } }))).toBe("streaming");
    expect(dockState(at({ last: { status: "queued" } }))).toBe("streaming");
    expect(dockState(at({ last: { status: "auditing" } }))).toBe("streaming");
  });
  it("is asking when an approval has no outcome, EVEN IF the turn looks like it is running", () => {
    expect(dockState(at({ status: "streaming", last: { status: "running" }, pendingApprovals: 1 }))).toBe("asking");
  });
  it("is failed when the last turn failed, and failure outranks the streaming status", () => {
    expect(dockState(at({ last: { status: "failed" } }))).toBe("failed");
    expect(dockState(at({ status: "failed", last: { status: "completed" } }))).toBe("failed");
  });
  it("a blocked or cancelled turn is not a failure: it is ready for the next prompt", () => {
    expect(dockState(at({ last: { status: "blocked" } }))).toBe("empty");
    expect(dockState(at({ last: { status: "cancelled" } }))).toBe("empty");
  });
});

describe("dockTitle", () => {
  it("names each state in the user's language", () => {
    expect(dockTitle("asking", true)).toBe("needs your decision");
    expect(dockTitle("failed", true)).toBe("that turn failed");
    expect(dockTitle("streaming", true)).toBe("working");
    expect(dockTitle("empty", false)).toBe("new conversation");
    // A session with a finished turn is a conversation, not a new one.
    expect(dockTitle("empty", true, true)).toBe("conversation");
    expect(dockTitle("empty", true, false)).toBe("new conversation");
  });
});

describe("dockStateWord", () => {
  it("is one short word, because the header's width belongs to the binding", () => {
    expect(dockStateWord("asking", true, true)).toBe("decide");
    expect(dockStateWord("failed", true, true)).toBe("failed");
    expect(dockStateWord("streaming", true, true)).toBe("working");
    expect(dockStateWord("empty", true, true)).toBe("ready");
    expect(dockStateWord("empty", false, false)).toBe("new");
    for (const w of ["decide", "failed", "working", "ready", "new"]) expect(w.length).toBeLessThan(8);
  });
});

describe("suggestionsFor — three things to do with what is open", () => {
  it("suggests cell actions when a cell is selected", () => {
    const s = suggestionsFor(withCell(focusFor(makeDoc("notebook", "/a/nb")), 3));
    expect(s).toHaveLength(3);
    expect(s[0].label).toBe("Explain cell 3");
    expect(s[0].prompt).toContain("cell 3");
    expect(s[1].prompt).toContain("cell 3");
  });
  it("suggests notebook actions when a notebook has no cell", () => {
    const s = suggestionsFor(focusFor(makeDoc("notebook", "/a/nb")));
    expect(s[0].label).toBe("Explain this notebook");
    expect(s.every((x) => x.prompt.length > 20)).toBe(true);
  });
  it("suggests file actions for a file and table actions for a table", () => {
    expect(suggestionsFor(focusFor(makeDoc("file", "/a/x.py")))[0].label).toBe("Explain this file");
    expect(suggestionsFor(focusFor(makeDoc("table", "m.s.t")))[0].label).toBe("Profile this table");
  });
  it("suggests how to begin when nothing is open", () => {
    const s = suggestionsFor(NO_FOCUS);
    expect(s[1].label).toBe("Open something from Files");
    expect(s.every((x) => !/unlock|smarter|connectors/i.test(x.prompt + x.label))).toBe(true);
  });
});

describe("announce — once per turn, never per token", () => {
  it("says the answer is ready when a run ends", () => {
    expect(announce({ turns: 1, running: true }, { turns: 1, running: false })).toBe("the answer is ready");
  });
  it("says the agent is working when a run starts", () => {
    expect(announce({ turns: 0, running: false }, { turns: 1, running: true })).toBe("the agent is working");
  });
  it("says nothing while tokens stream", () => {
    expect(announce({ turns: 1, running: true }, { turns: 1, running: true })).toBe("");
    expect(announce({ turns: 1, running: false }, { turns: 1, running: false })).toBe("");
  });
});

describe("dockStateWord — the last turn's outcome", () => {
  it("does not say ready after a turn that ended blocked, stopped or interrupted", () => {
    expect(dockStateWord("empty", true, true, "completed")).toBe("ready");
    expect(dockStateWord("empty", true, true, "blocked")).toBe("blocked");
    expect(dockStateWord("empty", true, true, "cancelled")).toBe("stopped");
    expect(dockStateWord("empty", true, true, "interrupted")).toBe("interrupted");
  });
  it("leaves the other states alone", () => {
    expect(dockStateWord("streaming", true, true, "blocked")).toBe("working");
    expect(dockStateWord("failed", true, true, "failed")).toBe("failed");
    expect(dockStateWord("empty", false, false)).toBe("new");
  });
});

// -- the two infrastructure kinds: suggestions must be about their SUBJECT ----------------------
// Found by inspecting s2-project-1480.png: the dock offered "Explain this notebook" over a Lakebase
// project, a plausible button that is wrong about what is on screen (spec 013 [UI-3]).
describe("suggestionsFor, when the subject is infrastructure", () => {
  it("offers project questions over a Lakebase project, never notebook ones", () => {
    const items = suggestionsFor({ docId: "lakebase:projects/pg", doc: { kind: "lakebase", ref: "projects/pg", name: "pg" }, cell: null } as never);
    const labels = items.map((s) => s.label).join(" ");
    expect(labels).not.toMatch(/notebook/i);
    expect(labels).toContain("pg");
  });

  it("offers health and logs over an app, never notebook ones", () => {
    const items = suggestionsFor({ docId: "app:tickets", doc: { kind: "app", ref: "tickets", name: "tickets" }, cell: null } as never);
    const labels = items.map((s) => s.label).join(" ");
    expect(labels).not.toMatch(/notebook/i);
    expect(labels).toMatch(/working|reads|Fix/i);
  });

  it("still offers notebook questions for a notebook", () => {
    const items = suggestionsFor({ docId: "notebook:nb", doc: { kind: "notebook", ref: "nb", name: "nb" }, cell: null } as never);
    expect(items.map((s) => s.label).join(" ")).toMatch(/notebook/i);
  });
});
