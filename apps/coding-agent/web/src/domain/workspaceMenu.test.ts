import { describe, expect, it } from "vitest";
import {
  childPath, cloneName, downloadName, importFormat, isProtected, menuFor, readFavorites, toggleFavorite,
} from "./workspaceMenu";

const home = "/Users/tester@example.com";
const ids = (kind: string, path: string) =>
  menuFor({ kind, path, name: path.split("/").pop() || "" }, { home, favorite: false }).flat().flatMap((i) => [i.id, ...(i.children ?? []).map((c) => c.id)]);

describe("menuFor", () => {
  it("offers the Databricks folder menu, plus attach and use-as-folder", () => {
    expect(ids("directory", `${home}/proj`)).toEqual([
      "attach", "use-folder", "open", "copy", "copy-url", "copy-path",
      "create", "create-notebook", "create-file", "create-folder",
      "rename", "move", "clone", "import", "download", "download-dbc",
      "share", "favorite", "trash",
    ]);
  });

  it("offers notebook downloads and no create", () => {
    const got = ids("notebook", `${home}/n`);
    expect(got).toContain("download-html");
    expect(got).toContain("download-jupyter");
    expect(got).toContain("download-source");
    expect(got).not.toContain("create");
    expect(got).not.toContain("import");
    expect(got).not.toContain("use-folder");
  });

  it("greys out rename, move, clone and trash on a root, and keeps create", () => {
    const items = menuFor({ kind: "directory", path: home, name: "My home" }, { home, favorite: false }).flat();
    for (const id of ["rename", "move", "clone", "trash"]) {
      expect(items.find((i) => i.id === id)).toMatchObject({ enabled: false });
    }
    expect(items.find((i) => i.id === "create")?.enabled).toBe(true);
  });

  it("sends a Git folder's rename, move and clone to Databricks", () => {
    const items = menuFor({ kind: "repo", path: "/Repos/tester/demo", name: "demo" }, { home, favorite: true }).flat();
    expect(items.find((i) => i.id === "rename")).toMatchObject({ enabled: false });
    expect(items.find((i) => i.id === "clone")?.reason).toMatch(/Git/);
    expect(items.find((i) => i.id === "favorite")?.label).toBe("Remove from favorites");
    expect(items.find((i) => i.id === "trash")?.enabled).toBe(true);
  });
});

describe("paths and formats", () => {
  it("protects the same roots the server protects", () => {
    expect(isProtected("/Shared", home)).toBe(true);
    expect(isProtected(home, home)).toBe(true);
    expect(isProtected("/Repos/tester", home)).toBe(true);
    expect(isProtected(`${home}/agent_scratch`, home)).toBe(false);
    expect(isProtected("/Repos/tester/edgedata", home)).toBe(false);
  });

  it("rejects a name that would leave the folder", () => {
    expect(childPath("/a", " notes.py ")).toBe("/a/notes.py");
    expect(childPath("/a", "x/y")).toBeNull();
    expect(childPath("/a", "..")).toBeNull();
    expect(cloneName("demo")).toBe("demo (1)");
  });

  it("picks an import format from the extension and a download name from the format", () => {
    expect(importFormat("a.ipynb").format).toBe("JUPYTER");
    expect(importFormat("a.dbc").format).toBe("DBC");
    expect(importFormat("a.py").format).toBe("AUTO");
    expect(downloadName("taxi", "SOURCE", "SQL")).toBe("taxi.sql");
    expect(downloadName("taxi.py", "SOURCE", "PYTHON")).toBe("taxi.py");
    expect(downloadName("proj", "DBC")).toBe("proj.dbc");
  });

  it("toggles a favorite and ignores a corrupt store", () => {
    const item = { path: "/a/n", name: "n", kind: "notebook" };
    expect(toggleFavorite([], item)).toEqual([item]);
    expect(toggleFavorite([item], item)).toEqual([]);
    expect(readFavorites("not json")).toEqual([]);
    expect(readFavorites(JSON.stringify([item, { path: 1 }]))).toEqual([item]);
  });
});
