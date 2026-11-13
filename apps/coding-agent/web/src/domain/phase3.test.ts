/** Phase 3 on the client: threads, proposals, and the two decisions each exists to make.
 *
 *  `[R-14]` parallel conversations · `[R-22]` a proposed edit.
 *
 *  Both are tested from the case that goes wrong, because the cheap version of each is a silent one:
 *  a tab strip where a background turn looks finished, and a proposal that overwrites unsaved text.
 */
import { describe, expect, it } from "vitest";
import {
  afterClose, close, cursorKey, documentTitle, isOpen, open, strip, threadOf, type ThreadInput,
} from "./threads";
import {
  apply, decide, refresh, summary, type CellChange, type Proposal,
} from "./proposal";

const s = (over: Partial<ThreadInput> = {}): ThreadInput => ({
  id: "s1", title: "Revenue", status: "ready", approvals: 0, ...over,
});

describe("threads: a tab's status comes from its own events", () => {
  it("marks a streaming session as working whether or not it is the active tab", () => {
    expect(threadOf(s({ status: "streaming" }), false).status).toBe("working");
    expect(threadOf(s({ status: "streaming" }), true).status).toBe("working");
  });

  it("lets an approval outrank streaming, because a waiting turn is not making progress", () => {
    const t = threadOf(s({ status: "streaming", approvals: 1 }), false);
    expect(t.status).toBe("needs-you");
    expect(t.approvals).toBe(1);
  });

  it("treats a session needing a restore as a decision for a human", () => {
    expect(threadOf(s({ requiresResume: true }), false).status).toBe("needs-you");
  });

  it("counts what you cannot see, so a background turn is not silent", () => {
    const st = strip([
      s({ id: "a", status: "streaming" }),
      s({ id: "b", approvals: 2 }),
      s({ id: "c", status: "ready" }),
    ], "c");
    expect(st.working).toBe(1);
    expect(st.needsYou).toBe(1);
  });

  it("puts the counts in the browser tab's title", () => {
    const one = strip([s({ id: "a", approvals: 1 })], "a");
    expect(documentTitle(one)).toBe("(1) OpenGenie");
    expect(documentTitle(strip([s({ id: "a" })], "a"))).toBe("OpenGenie");
  });

  it("keeps tab order when a background turn finishes", () => {
    const ids = ["a", "b", "c"];
    const before = strip(ids.map((id) => s({ id })), "a").threads.map((t) => t.id);
    const after = strip(ids.map((id) => s({ id, status: id === "c" ? "streaming" : "ready" })), "a")
      .threads.map((t) => t.id);
    expect(after).toEqual(before);
  });

  it("never opens the same conversation twice", () => {
    const list = open([s({ id: "a" })], s({ id: "a" }));
    expect(list.filter((x) => x.id === "a")).toHaveLength(1);
  });

  it("is open? — so the strip cannot duplicate a session the shell already holds", () => {
    expect(isOpen([s({ id: "a" })], "a")).toBe(true);
    expect(isOpen([s({ id: "a" })], "b")).toBe(false);
  });

  it("lands somewhere after a close, and nowhere only when nothing is left", () => {
    expect(afterClose(["a", "b", "c"], "b", "b")).toBe("c");
    expect(afterClose(["a", "b", "c"], "b", "a")).toBe("a");
    expect(afterClose(["a"], "a", "a")).toBeNull();
    expect(close([s({ id: "a" }), s({ id: "b" })], "a").map((x) => x.id)).toEqual(["b"]);
  });

  it("names a cursor per session rather than one global one", () => {
    expect(cursorKey("abc")).toBe("stream:abc");
    expect(cursorKey("abc")).not.toBe(cursorKey("def"));
  });
});

const change = (over: Partial<CellChange> = {}): CellChange => ({
  key: "c3", index: 2, kind: "replace", before: "a", after: "b", reason: "the column was renamed", ...over,
});
const proposal = (over: Partial<Proposal> = {}): Proposal => ({
  id: "p1", docId: "notebook:/x", version: "v3", cells: [change()], state: "ready", ...over,
});

describe("proposal: two hard cases, both decided before a byte is written", () => {
  it("keeps when the document is clean and at the same version", () => {
    const d = decide(proposal(), { version: "v3", dirty: false });
    expect(d.canKeep).toBe(true);
    expect(d.blockedReason).toBe("");
  });

  it("HOLDS on a dirty document, because applying would destroy unsaved text", () => {
    const d = decide(proposal(), { version: "v3", dirty: true });
    expect(d.canKeep).toBe(false);
    expect(d.canReject).toBe(true);
    expect(d.blockedReason).toMatch(/unsaved/);
  });

  it("HOLDS when the document moved on, rather than failing at the moment Keep is pressed", () => {
    const d = decide(proposal(), { version: "v4", dirty: false });
    expect(d.canKeep).toBe(false);
    expect(d.blockedReason).toMatch(/changed since/);
  });

  it("does nothing once a proposal is decided", () => {
    for (const state of ["accepted", "rejected"] as const) {
      const d = decide(proposal({ state }), { version: "v3", dirty: false });
      expect(d.canKeep).toBe(false);
      expect(d.canReject).toBe(false);
    }
  });

  it("is total: no proposal or no document is a sentence, not a crash", () => {
    const d = decide(null, null);
    expect(d.canKeep).toBe(false);
    expect(d.blockedReason).toBeTruthy();
  });

  it("refreshes itself when the document changes under it", () => {
    expect(refresh(proposal(), { version: "v3", dirty: true }).state).toBe("held-dirty");
    expect(refresh(proposal(), { version: "v9", dirty: false }).state).toBe("held-stale");
    expect(refresh(proposal({ state: "held-dirty" }), { version: "v3", dirty: false }).state).toBe("ready");
  });

  it("never re-opens a decided proposal", () => {
    expect(refresh(proposal({ state: "accepted" }), { version: "v3", dirty: false }).state).toBe("accepted");
  });
});

describe("proposal: applying is a pure list operation, so 'reject' is provably a no-write", () => {
  const cells = [
    { key: "c1", source: "one" },
    { key: "c3", source: "three" },
  ];

  it("replaces a cell in place", () => {
    expect(apply(cells, [change({ key: "c1", after: "ONE" })])).toEqual([
      { key: "c1", source: "ONE" }, { key: "c3", source: "three" },
    ]);
  });

  it("inserts after the named cell", () => {
    const out = apply(cells, [change({ key: "c1", kind: "insert", after: "new" })]);
    expect(out.map((c) => c.source)).toEqual(["one", "new", "three"]);
  });

  it("appends an insert whose anchor is gone, rather than losing the cell", () => {
    const out = apply(cells, [change({ key: "gone", kind: "insert", after: "new" })]);
    expect(out.at(-1)?.source).toBe("new");
  });

  it("deletes the named cell and nothing else", () => {
    expect(apply(cells, [change({ key: "c1", kind: "delete", after: "" })])).toEqual([
      { key: "c3", source: "three" },
    ]);
  });

  it("does not mutate the input, so rejecting leaves the original byte-identical", () => {
    const before = JSON.stringify(cells);
    apply(cells, [change({ key: "c1", after: "ONE" })]);
    expect(JSON.stringify(cells)).toBe(before);
  });

  it("an empty change list is identity", () => {
    expect(apply(cells, [])).toEqual(cells);
  });
});

describe("proposal: the header sentence", () => {
  it("counts each kind of change", () => {
    const p = proposal({ cells: [change({ kind: "replace" }), change({ kind: "insert" }), change({ kind: "delete" })] });
    expect(summary(p)).toBe("1 cell changed, 1 added, 1 removed");
  });

  it("says nothing for an empty proposal", () => {
    expect(summary(proposal({ cells: [] }))).toBe("");
    expect(summary(null)).toBe("");
  });
});
