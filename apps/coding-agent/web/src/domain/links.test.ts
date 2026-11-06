import { describe, expect, it } from "vitest";
import { splitPaths, workspaceUrl } from "./links";

const ws = { host: "https://dbc-1.cloud.databricks.com/", orgId: "747" };

describe("workspaceUrl", () => {
  it("goes straight to the editor when the object id is known", () => {
    expect(workspaceUrl(ws, { kind: "notebook", ref: "/Users/a@b.c/x", objectId: "38490" }))
      .toBe("https://dbc-1.cloud.databricks.com/editor/notebooks/38490?o=747");
    expect(workspaceUrl(ws, { kind: "file", ref: "/Users/a/f.py", objectId: "5" })).toContain("/editor/files/5");
    expect(workspaceUrl(ws, { kind: "directory", ref: "/Users/a", objectId: "9" })).toContain("/browse/folders/9");
  });
  it("falls back to the path redirect, encoded, without /Workspace", () => {
    expect(workspaceUrl(ws, { kind: "notebook", ref: "/Workspace/Users/a@b.c/my nb" }))
      .toBe("https://dbc-1.cloud.databricks.com/?o=747#workspace/Users/a%40b.c/my%20nb");
    expect(workspaceUrl({ host: "https://h" }, { kind: "notebook", ref: "/Users/a/x" })).toBe("https://h/#workspace/Users/a/x");
  });
  it("links a table to the catalog explorer, and refuses a malformed one", () => {
    expect(workspaceUrl(ws, { kind: "table", ref: "samples.nyctaxi.trips" }))
      .toBe("https://dbc-1.cloud.databricks.com/explore/data/samples/nyctaxi/trips?o=747");
    expect(workspaceUrl(ws, { kind: "table", ref: "samples.nyctaxi" })).toBeNull();
  });
  it("makes no link without a host or with a relative path", () => {
    expect(workspaceUrl(null, { kind: "notebook", ref: "/Users/a/x" })).toBeNull();
    expect(workspaceUrl({ host: "" }, { kind: "notebook", ref: "/Users/a/x" })).toBeNull();
    expect(workspaceUrl(ws, { kind: "notebook", ref: "relative/x" })).toBeNull();
  });
});

describe("splitPaths", () => {
  it("finds paths in prose and leaves trailing punctuation outside", () => {
    expect(splitPaths("Wrote /Users/a@b.c/agent_scratch/hello_world. Then ran it.")).toEqual([
      { text: "Wrote " },
      { text: "/Users/a@b.c/agent_scratch/hello_world", path: "/Users/a@b.c/agent_scratch/hello_world" },
      { text: ". Then ran it." },
    ]);
  });
  it("does not link volumes or ordinary words", () => {
    expect(splitPaths("see /Volumes/main/x/y and a/b")).toEqual([{ text: "see /Volumes/main/x/y and a/b" }]);
  });
});
