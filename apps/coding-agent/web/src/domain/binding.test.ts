import { describe, expect, it } from "vitest";
import { autoAttachment, attachmentsFor } from "./binding";
import { makeDoc } from "./docs";
import { focusFor, NO_FOCUS, withCell } from "./focus";

const nb = makeDoc("notebook", "/Users/a/agent_scratch/nb");
const file = makeDoc("file", "/Users/a/notes.md");
const table = makeDoc("table", "main.sales.orders");

describe("attachmentsFor", () => {
  it("attaches the open document", () => {
    expect(attachmentsFor(focusFor(nb))).toEqual([
      { kind: "notebook", ref: nb.ref, name: "nb" },
    ]);
  });
  it("attaches a cell INSTEAD of its document, never both", () => {
    const got = attachmentsFor(withCell(focusFor(nb), 3));
    expect(got).toEqual([{ kind: "cell", ref: `${nb.ref}#3`, name: "nb · cell 3" }]);
    expect(got.some((a) => a.kind === "notebook")).toBe(false);
  });
  it("attaches a table by its three-part name", () => {
    expect(attachmentsFor(focusFor(table))).toEqual([
      { kind: "table", ref: "main.sales.orders", name: "orders" },
    ]);
  });
  it("attaches a file as a file", () => {
    expect(attachmentsFor(focusFor(file))[0].kind).toBe("file");
  });
  it("attaches nothing when nothing is open", () => {
    expect(attachmentsFor(NO_FOCUS)).toEqual([]);
  });
});

describe("autoAttachment", () => {
  it("is the single binding, for the composer's automatic chip", () => {
    expect(autoAttachment(focusFor(nb))?.ref).toBe(nb.ref);
    expect(autoAttachment(withCell(focusFor(nb), 2))?.kind).toBe("cell");
    expect(autoAttachment(NO_FOCUS)).toBeNull();
  });
});
