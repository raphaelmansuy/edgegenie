import { beforeEach, describe, expect, it } from "vitest";
import { forgetDocs, nameOf, recentDocs, rememberDoc } from "./recent";

beforeEach(() => { localStorage.clear(); forgetDocs(); });

const nb = (path: string) => ({ path, name: path.split("/").pop() ?? path, kind: "notebook" as const });

describe("recent documents", () => {
  it("keeps the most recent first", () => {
    rememberDoc(nb("/a/one"));
    rememberDoc(nb("/a/two"));
    expect(recentDocs().map((d) => d.path)).toEqual(["/a/two", "/a/one"]);
  });
  it("moves a re-opened document to the front instead of duplicating it", () => {
    rememberDoc(nb("/a/one"));
    rememberDoc(nb("/a/two"));
    rememberDoc(nb("/a/one"));
    expect(recentDocs().map((d) => d.path)).toEqual(["/a/one", "/a/two"]);
  });
  it("caps the list", () => {
    for (let i = 0; i < 12; i++) rememberDoc(nb(`/a/n${i}`));
    expect(recentDocs()).toHaveLength(6);
    expect(recentDocs()[0].path).toBe("/a/n11");
  });
  it("names a table by its last part, a file by its last segment", () => {
    expect(nameOf("table", "samples.nyctaxi.trips")).toBe("trips");
    expect(nameOf("notebook", "/Users/me/agent_scratch/x")).toBe("x");
  });
});
