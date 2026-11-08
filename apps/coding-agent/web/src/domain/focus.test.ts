import { describe, expect, it } from "vitest";
import { makeDoc } from "./docs";
import {
  cellRef, focusFor, focusLabel, folderOf, NO_FOCUS, parseCellRef, sameFocus, withCell, withoutDoc,
} from "./focus";

const nb = makeDoc("notebook", "/Users/a/agent_scratch/revenue_by_hour");
const file = makeDoc("file", "/Users/a/agent_scratch/notes.md");
const table = makeDoc("table", "main.sales.orders");

describe("focusFor", () => {
  it("opens a document with no cell selected", () => {
    expect(focusFor(nb)).toEqual({
      docId: nb.id,
      doc: { kind: "notebook", ref: nb.ref, name: nb.name },
      cell: null,
    });
  });
  it("is empty for no document", () => {
    expect(focusFor(null)).toEqual(NO_FOCUS);
    expect(focusFor(undefined)).toEqual(NO_FOCUS);
  });
});

describe("withCell", () => {
  it("selects a cell and keeps the document", () => {
    const f = withCell(focusFor(nb), 3);
    expect(f.cell).toBe(3);
    expect(f.doc?.ref).toBe(nb.ref);
  });
  it("clears the cell with null or 0, and refuses a cell with no document", () => {
    expect(withCell(focusFor(nb), null).cell).toBeNull();
    expect(withCell(focusFor(nb), 0).cell).toBeNull();
    expect(withCell(withCell(focusFor(nb), 2), null).cell).toBeNull();
    expect(withCell(NO_FOCUS, 4)).toEqual(NO_FOCUS);
  });
  it("floors a fractional index rather than trusting it", () => {
    expect(withCell(focusFor(nb), 2.9).cell).toBe(2);
  });
});

describe("closing the document", () => {
  it("clears everything, so no prompt can attach a closed file", () => {
    expect(withoutDoc()).toEqual(NO_FOCUS);
  });
});

describe("identity", () => {
  it("compares by document and cell, not by object identity", () => {
    expect(sameFocus(focusFor(nb), focusFor(makeDoc("notebook", nb.ref)))).toBe(true);
    expect(sameFocus(focusFor(nb), withCell(focusFor(nb), 1))).toBe(false);
    expect(sameFocus(focusFor(nb), focusFor(file))).toBe(false);
    expect(sameFocus(NO_FOCUS, NO_FOCUS)).toBe(true);
  });
});

describe("folderOf", () => {
  it("is the containing folder of a workspace path", () => {
    expect(folderOf(focusFor(nb))).toBe("/Users/a/agent_scratch");
    expect(folderOf(focusFor(makeDoc("file", "/Shared/x.py")))).toBe("/Shared");
    expect(folderOf(focusFor(makeDoc("file", "/top")))).toBe("/");
  });
  it("is empty for a table (it has no folder) and for nothing open", () => {
    expect(folderOf(focusFor(table))).toBe("");
    expect(folderOf(NO_FOCUS)).toBe("");
  });
});

describe("the label the dock header shows", () => {
  it("names the document, then the cell", () => {
    expect(focusLabel(focusFor(nb))).toBe("revenue_by_hour");
    expect(focusLabel(withCell(focusFor(nb), 3))).toBe("revenue_by_hour · cell 3");
    expect(focusLabel(NO_FOCUS)).toBe("nothing open");
  });
});

describe("cell references", () => {
  it("round-trips a path and an index", () => {
    const f = withCell(focusFor(nb), 3);
    expect(cellRef(f)).toBe(`${nb.ref}#3`);
    expect(parseCellRef(cellRef(f)!)).toEqual({ path: nb.ref, cell: 3 });
  });
  it("refuses anything that is not a cell reference, rather than guessing", () => {
    expect(parseCellRef("/a/b")).toBeNull();
    expect(parseCellRef("/a/b#0")).toBeNull();
    expect(parseCellRef("/a/b#x")).toBeNull();
    expect(parseCellRef("/a/b#1.5")).toBeNull();
    expect(parseCellRef("#3")).toBeNull();
  });
  it("has no reference without a cell", () => {
    expect(cellRef(focusFor(nb))).toBeNull();
    expect(cellRef(NO_FOCUS)).toBeNull();
  });
});
