/** Mirror of tests/test_notebook_roundtrip.py, over the SAME corpus.
 *
 * The client serializer (domain/notebook.ts) and the server's (api/domain/notebook_write.py) are
 * two implementations of one format. Spec 003 D5 says one of them is authoritative and the other is
 * a mirror; this file is what keeps them honest. The corpus below is duplicated from the Python
 * test on purpose — if someone changes one side, one of the two suites fails rather than a notebook
 * being corrupted in the field.
 */
import { describe, expect, it } from "vitest";
import {
  checkCells, insertCell, MAX_CELLS, mergeWithNext, moveCell, newCell, parseCells, removeCell,
  serializeCells, setCellKind, splitCell, type Cell,
} from "./notebook";

const PREFIX: Record<string, string> = { PYTHON: "#", SQL: "--", SCALA: "//", R: "#" };

/** Build a SOURCE document the way Databricks writes one. */
function notebookText(lang: string, cells: [string, string][]): string {
  const p = PREFIX[lang];
  const out = [`${p} Databricks notebook source`];
  cells.forEach(([kind, source], i) => {
    if (i) out.push("", `${p} COMMAND ----------`, "");
    if (kind === "markdown") {
      for (const ln of source.split("\n")) out.push(ln ? `${p} MAGIC %md ${ln}` : `${p} MAGIC`);
    } else if (kind && kind !== lang.toLowerCase()) {
      const word = { sql: "sql", shell: "sh", pip: "pip", fs: "fs", r: "r", scala: "scala" }[kind] ?? kind;
      for (const ln of source.split("\n")) out.push(ln ? `${p} MAGIC %${word} ${ln}` : `${p} MAGIC`);
    } else {
      out.push(...source.split("\n"));
    }
  });
  return `${out.join("\n")}\n`;
}

const CORPUS: [string, [string, string][]][] = [
  ["PYTHON", [["", "print(1)"]]],
  ["PYTHON", [["", "print(1)"], ["", "print(2)"]]],
  ["PYTHON", [["markdown", "# Title"], ["", "x = 1"]]],
  ["PYTHON", [["", "x = 1"], ["sql", "select * from samples.nyctaxi.trips"]]],
  ["PYTHON", [["markdown", "# A\n\nSome prose.\n\n- one\n- two"], ["", "df = spark.table('t')"]]],
  ["SCALA", [["", "val x = 1"], ["", "println(x)"]]],
  ["SQL", [["", "select 1"], ["", "select 2"]]],
  ["R", [["", "x <- 1"]]],
  ["PYTHON", [["", "a\n\nb\n\n\nc"]]],
  ["PYTHON", [["", "  indented\n    deeper"]]],
  ["PYTHON", [["shell", "%sh\necho hi"], ["", "y = 2"]]],
  ["PYTHON", [["pip", "pip install pandas"]]],
];

const shape = (cells: readonly Cell[]) => cells.map((c) => [c.kind, c.language, c.source]);

describe("notebook round trip (shared corpus with the Python suite)", () => {
  it.each(CORPUS)("parse -> serialize -> parse is the identity (%s)", (lang, cells) => {
    const parsed = parseCells(notebookText(lang, cells), lang);
    const again = parseCells(serializeCells(parsed, lang), lang);
    expect(shape(again)).toEqual(shape(parsed));
  });

  it.each(CORPUS)("the canonical form is stable after one save (%s)", (lang, cells) => {
    const once = serializeCells(parseCells(notebookText(lang, cells), lang), lang);
    const twice = serializeCells(parseCells(once, lang), lang);
    expect(twice).toBe(once);
  });

  it("an empty notebook is a header and one newline", () => {
    expect(serializeCells([], "PYTHON")).toBe("# Databricks notebook source\n");
    expect(parseCells(serializeCells([], "PYTHON"), "PYTHON")).toEqual([]);
  });

  it("keeps indentation after a magic", () => {
    // The Python parser used to `.strip()` this and silently eat the tab. Both sides must agree.
    const text = "# Databricks notebook source\n# MAGIC %md \tindented\n# MAGIC more\n";
    const cells = parseCells(text, "PYTHON");
    expect(cells[0].source).toBe("\tindented\nmore");
  });
});

describe("checkCells refuses what cannot be written back", () => {
  it("passes a clean document", () => {
    expect(checkCells(parseCells(notebookText("PYTHON", [["", "x = 1"]]), "PYTHON"))).toEqual([]);
  });

  it("refuses a truncated cell", () => {
    const cells: Cell[] = [{ id: "a", kind: "code", language: "python", source: "x", truncated: true }];
    expect(checkCells(cells)[0]).toContain("truncated");
  });

  it("refuses more cells than the format allows", () => {
    const cells = Array.from({ length: MAX_CELLS + 1 }, (_, i) => newCell("code", "python", `x${i}`));
    expect(checkCells(cells)[0]).toContain(String(MAX_CELLS));
  });
});

describe("cell operations", () => {
  const three = (): Cell[] => [
    newCell("code", "python", "a"),
    newCell("code", "python", "b"),
    newCell("code", "python", "c"),
  ];

  it("moves without changing any id", () => {
    const before = three();
    const after = moveCell(before, 2, 0);
    expect(after.map((c) => c.source)).toEqual(["c", "a", "b"]);
    expect(after.map((c) => c.id).sort()).toEqual(before.map((c) => c.id).sort());
  });

  it("clamps a move to the list", () => {
    expect(moveCell(three(), 0, 99).map((c) => c.source)).toEqual(["b", "c", "a"]);
    expect(moveCell(three(), 99, 0).map((c) => c.source)).toEqual(["a", "b", "c"]);
  });

  it("inserts at a position", () => {
    const out = insertCell(three(), 1, newCell("markdown", "markdown", "# h"));
    expect(out.map((c) => c.kind)).toEqual(["code", "markdown", "code", "code"]);
  });

  it("removes by id, not by index", () => {
    const cells = three();
    const out = removeCell(cells, cells[1].id);
    expect(out.map((c) => c.source)).toEqual(["a", "c"]);
  });

  it("converting kind leaves the source byte-identical", () => {
    const cells = three();
    const toMd = setCellKind(cells, cells[0].id, "markdown", "python");
    const back = setCellKind(toMd, cells[0].id, "code", "python");
    expect(back[0].source).toBe(cells[0].source);
    expect(back[0].kind).toBe("code");
  });

  it("a notebook saved after a move differs only by that move", () => {
    const before = three();
    const after = moveCell(before, 2, 0);
    expect(serializeCells(after).split("\n").length).toBe(serializeCells(before).split("\n").length);
    expect(checkCells(after)).toEqual([]);
  });
});

describe("a block that is only the notebook header is not a cell", () => {
  it("drops it, so cell 1 is the first real statement", () => {
    const src = [
      "-- Databricks notebook source",
      "-- COMMAND ----------",
      "select 1 as one",
    ].join("\n");
    const cells = parseCells(src, "SQL");
    expect(cells).toHaveLength(1);
    expect(cells[0].source.trim()).toBe("select 1 as one");
  });
  it("keeps a cell that has a header comment among real code", () => {
    const src = [
      "-- Databricks notebook source",
      "-- Databricks notebook source",
      "select 2",
    ].join("\n");
    const cells = parseCells(src, "SQL");
    expect(cells).toHaveLength(1);
    expect(cells[0].source).toContain("select 2");
  });
  it("keeps %skip as a directive in the notebook's language, not as a language of its own", () => {
    const src = ["# Databricks notebook source", "# MAGIC %skip", "# MAGIC select 1"].join("\n");
    const cells = parseCells(src, "PYTHON");
    expect(cells).toHaveLength(1);
    expect(cells[0].language).toBe("python");
    expect(cells[0].source).toBe("%skip\nselect 1");
  });
});

describe("merge and split", () => {
  const a = newCell("code", "sql", "select 1");
  const b = newCell("code", "sql", "select 2");
  it("joins a cell with the next and leaves the rest", () => {
    const merged = mergeWithNext([a, b], 0);
    expect(merged).toHaveLength(1);
    expect(merged[0].source).toBe("select 1\nselect 2");
    expect(merged[0].id).toBe(a.id);
  });
  it("splits at the caret and does nothing when nothing follows it", () => {
    const split = splitCell([a], 0, "select ".length);
    expect(split).toHaveLength(2);
    expect(split[0].source).toBe("select ");
    expect(split[1].source).toBe("1");
    expect(splitCell([a], 0, a.source.length)).toHaveLength(1);
  });
});
