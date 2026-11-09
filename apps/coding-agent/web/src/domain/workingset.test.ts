import { beforeEach, describe, expect, it, vi } from "vitest";
import { makeDoc } from "./docs";
import { parseWorkingSet, readWorkingSet, saveWorkingSet } from "./workingset";

beforeEach(() => sessionStorage.clear());
describe("working set recovery", () => {
  it("restores ordered canonical references, selection and reopen metadata without content", () => {
    const docs = [makeDoc("file", "/Workspace/Repos/me/app.yml"), makeDoc("table", "main.demo.orders")];
    saveWorkingSet("workspace|alice", docs, docs[1].id, [{ doc: docs[0], index: 0 }]);
    const saved = readWorkingSet("workspace|alice");
    expect(saved.docs.map((d) => d.id)).toEqual(docs.map((d) => d.id));
    expect(saved.active).toBe(docs[1].id); expect(saved.closed[0].index).toBe(0);
    expect(sessionStorage.getItem(sessionStorage.key(0)!)).not.toMatch(/text|content|token|rev|name/);
  });
  it("isolates workspaces and accounts", () => {
    const d = makeDoc("notebook", "/Shared/revenue");
    saveWorkingSet("ws|alice", [d], d.id, []);
    expect(readWorkingSet("ws|bob").docs).toEqual([]); expect(readWorkingSet("other|alice").docs).toEqual([]);
  });
  it("tolerates corrupt, incompatible and malformed records and deduplicates identities", () => {
    for (const input of [null, "{", "[]", '{"version":2,"docs":[]}']) expect(parseWorkingSet(input).docs).toEqual([]);
    const d = { kind: "file", ref: "/Shared/a" };
    expect(parseWorkingSet(JSON.stringify({ version: 1, active: "missing", docs: [d, d, null, { kind: "file", ref: "relative" }] })).docs).toHaveLength(1);
  });
  it("bounds stored metadata and survives blocked storage", () => {
    const docs = Array.from({ length: 150 }, (_, i) => makeDoc("file", `/Shared/${i}`));
    saveWorkingSet("scope", docs, docs[0].id, docs.map((doc, index) => ({ doc, index })));
    expect(readWorkingSet("scope").docs).toHaveLength(100); expect(readWorkingSet("scope").closed).toHaveLength(20);
    const get = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(readWorkingSet("scope").docs).toEqual([]); get.mockRestore();
    const set = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("full"); });
    expect(() => saveWorkingSet("scope", docs, "chat", [])).not.toThrow(); set.mockRestore();
  });
});
