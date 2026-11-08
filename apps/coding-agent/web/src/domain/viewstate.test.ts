import { beforeEach, describe, expect, it } from "vitest";
import { clampTo, forget, recall, remember } from "./viewstate";

beforeEach(() => { sessionStorage.clear(); forget("/a"); forget("/b"); });

describe("viewstate", () => {
  it("remembers a place per path and merges patches", () => {
    remember("/a", { cell: 3, caret: 12, mode: "edit" });
    remember("/a", { scroll: 640 });
    expect(recall("/a")).toEqual({ cell: 3, caret: 12, mode: "edit", scroll: 640 });
    expect(recall("/b")).toBeNull();
  });
  it("forgets", () => {
    remember("/a", { cell: 1 });
    forget("/a");
    expect(recall("/a")).toBeNull();
  });
  it("pulls a stale place back inside a notebook that shrank", () => {
    const s = clampTo({ cell: 9, caret: 500, mode: "edit", scroll: 0 }, 4, () => 20);
    expect(s).toMatchObject({ cell: 4, caret: 20 });
    expect(clampTo({ cell: 2, caret: 3, mode: "edit", scroll: 0 }, 0, () => 0).cell).toBe(0);
  });
});
