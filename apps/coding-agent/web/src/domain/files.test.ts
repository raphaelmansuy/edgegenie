import { describe, expect, it } from "vitest";
import { crumbsFor, emptyCopy, filterNodes, parentOf, readView, sortNodes, typeLabel, whereLabel } from "./files";
import type { WsNode } from "../components/WorkspaceTree";

const n = (name: string, kind: WsNode["kind"], extra: Partial<WsNode> = {}): WsNode => ({
  path: `/x/${name}`, name, kind, hasChildren: kind === "directory", ...extra,
});

describe("sortNodes — folders first, then name, case-insensitively", () => {
  it("puts folders above files", () => {
    const got = sortNodes([n("b.py", "file"), n("a_folder", "directory"), n("a.py", "file")]);
    expect(got.map((x) => x.name)).toEqual(["a_folder", "a.py", "b.py"]);
  });
  it("sorts numbers by value, not by character", () => {
    expect(sortNodes([n("cell10", "file"), n("cell2", "file")]).map((x) => x.name)).toEqual(["cell2", "cell10"]);
  });
  it("ignores case and does not mutate the input", () => {
    const input = [n("Beta", "file"), n("alpha", "file")];
    expect(sortNodes(input).map((x) => x.name)).toEqual(["alpha", "Beta"]);
    expect(input.map((x) => x.name)).toEqual(["Beta", "alpha"]);
  });
  it("treats a repo as a folder", () => {
    expect(sortNodes([n("z.py", "file"), n("r", "repo")]).map((x) => x.name)).toEqual(["r", "z.py"]);
  });
});

describe("filterNodes", () => {
  it("matches name or path, ignoring case, and returns everything for a blank query", () => {
    const nodes = [n("Revenue", "notebook"), n("notes", "file")];
    expect(filterNodes(nodes, "rev").map((x) => x.name)).toEqual(["Revenue"]);
    expect(filterNodes(nodes, "/x/notes").map((x) => x.name)).toEqual(["notes"]);
    expect(filterNodes(nodes, "   ")).toHaveLength(2);
  });
});

describe("typeLabel", () => {
  it("uses the words a Databricks user expects", () => {
    expect(typeLabel("directory")).toBe("Folder");
    expect(typeLabel("repo")).toBe("Repo");
    expect(typeLabel("notebook")).toBe("Notebook");
    expect(typeLabel("file")).toBe("File");
  });
});

describe("crumbsFor", () => {
  it("replaces the segments the root already names, rather than repeating them", () => {
    expect(crumbsFor("My home", "/Users/a/agent_scratch", "/Users/a")).toEqual([
      { name: "My home", path: "/Users/a" },
      { name: "agent_scratch", path: "/Users/a/agent_scratch" },
    ]);
  });
  it("is just the root when the folder IS the root", () => {
    expect(crumbsFor("My home", "/Users/a", "/Users/a")).toEqual([{ name: "My home", path: "/Users/a" }]);
  });
  it("falls back to the real segments when the path is outside the root", () => {
    expect(crumbsFor("Shared", "/Repos/x/y", "/Shared").map((c) => c.name))
      .toEqual(["Shared", "Repos", "x", "y"]);
  });
  it("handles no root at all", () => {
    expect(crumbsFor("My home", "/")).toEqual([{ name: "My home", path: "/" }]);
  });
});

describe("whereLabel", () => {
  it("says · for the folder being browsed, and the relative path otherwise", () => {
    expect(whereLabel("/Users/a/x.py", "/Users/a")).toBe("·");
    expect(whereLabel("/Users/a/sub/x.py", "/Users/a")).toBe("sub");
    expect(whereLabel("/Shared/x/y.py", "/Users/a")).toBe("/Shared/x");
  });
});

describe("parentOf", () => {
  it("returns the containing folder, and null at a root", () => {
    expect(parentOf("/a/b/c")).toBe("/a/b");
    expect(parentOf("/a")).toBeNull();
    expect(parentOf("/")).toBeNull();
  });
});

describe("the view toggle and the empty copy", () => {
  it("defaults to tree and accepts list", () => {
    expect(readView(null)).toBe("tree");
    expect(readView("nonsense")).toBe("tree");
    expect(readView("list")).toBe("list");
  });
  it("names an action instead of saying nothing here", () => {
    expect(emptyCopy("", true)).toContain("Use +");
    expect(emptyCopy("", false)).not.toContain("+");
    expect(emptyCopy("rev", true)).toContain("rev");
  });
});
