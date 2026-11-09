import { describe, expect, it } from "vitest";
import { cellLabel, executionMap } from "./minimap";

const cells = [
  { id: "m", kind: "markdown", source: "# Revenue by hour" },
  { id: "a", kind: "code", source: "-- trips by hour\nselect 1" },
  { id: "s", kind: "code", source: "%skip\nselect 9" },
  { id: "b", kind: "code", source: "select * from missing_table" },
];

describe("execution map", () => {
  it("names a cell from its heading or its first comment, and skips prose", () => {
    expect(cellLabel(cells[0], 0)).toBe("Revenue by hour");
    expect(cellLabel(cells[1], 1)).toBe("trips by hour");
    const map = executionMap(cells, {}, ["a", "b"], null);
    expect(map.rows.map((r) => r.index)).toEqual([2, 3, 4]);
    expect(map.rows.map((r) => r.tone)).toEqual(["idle", "skip", "idle"]);
  });
  it("marks a batch: running, queued, failed, and where to jump", () => {
    const map = executionMap(cells, {
      a: { state: "succeeded" },
      b: { state: "failed" },
    }, ["a", "b"], ["b"]);
    expect(map.rows.find((r) => r.id === "a")?.tone).toBe("ok");
    expect(map.rows.find((r) => r.id === "b")?.tone).toBe("failed");
    expect(map.firstFailed).toBe(4);
    expect(map.lastSettled).toBe(4);
  });
});
