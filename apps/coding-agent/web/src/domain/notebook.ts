/** The document model: cells, and the exact inverse round trip. Pure — no React, no CodeMirror.
 *
 * This mirrors `api/domain/notebook.py` + `notebook_write.py`. It exists on the client because the
 * editor has to reason about cells without a round trip (add, move, convert, diff), and because a
 * save must be able to show you what it is about to write.
 *
 * ## One definition of the format
 *
 * The server is the authority on serialization (spec 003 D5). This module is a *mirror*, and it is
 * verified against the server with a shared corpus (`notebook.corpus.test.ts`), so a drift between
 * the two is a test failure rather than a corrupted notebook. Two independent serializers that
 * nobody compares is exactly the DRY violation the spec forbids.
 */

export type CellKind = "code" | "markdown";

export interface Cell {
  /** Stable across a reorder. Derived from position + a content hint at parse, preserved after. */
  id: string;
  kind: CellKind;
  language: string;
  source: string;
  truncated?: boolean;
}

/** Databricks SOURCE-format comment prefix per notebook language. Mirrors `PREFIX` in Python. */
const PREFIX: Record<string, string> = { PYTHON: "#", R: "#", SQL: "--", SCALA: "//" };

const MAGICS: Record<string, string> = {
  md: "markdown", sql: "sql", python: "python", scala: "scala", r: "r",
  sh: "shell", fs: "fs", pip: "pip", run: "run",
};

const MAGIC_FOR: Record<string, string> = Object.fromEntries(
  Object.entries(MAGICS).map(([word, lang]) => [lang, word]),
);

export const MAX_CELLS = 400;
export const MAX_CELL_CHARS = 20_000;

const prefix = (language: string) => PREFIX[(language || "PYTHON").toUpperCase()] ?? "#";

/** A stable id for a cell at a position. Content is mixed in so a re-order is visible in the id
 *  space while still being deterministic for the same document, which keeps tests readable. */
function idAt(index: number, source: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < source.length; i += 1) {
    h ^= source.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return `c${index}-${(h >>> 0).toString(36)}`;
}

/** Split a magic body line back into its content, dropping the magic token and one space. */
function afterMagic(line: string): string {
  const trimmed = line.trim();
  if (!trimmed.startsWith("%")) return line;
  const word = trimmed.slice(1).split(/\s/)[0] ?? "";
  let rest = trimmed.slice(1 + word.length);
  if (rest.startsWith(" ")) rest = rest.slice(1);
  return rest;
}

export function parseCells(text: string, language = "PYTHON"): Cell[] {
  const lang = (language || "PYTHON").toLowerCase();
  const pre = prefix(language);
  const sep = `${pre} COMMAND ----------`;
  const header = `${pre} Databricks notebook source`;

  const lines = text.replace(/\r\n/g, "\n").split("\n");
  if (lines.length && lines[0].trim() === header) lines.shift();

  const blocks: string[][] = [[]];
  for (const ln of lines) {
    if (ln.trim() === sep) blocks.push([]);
    else blocks[blocks.length - 1].push(ln);
  }

  const cells: Cell[] = [];
  for (const raw of blocks) {
    let b = raw.slice();
    while (b.length && !b[0].trim()) b.shift();
    while (b.length && !b[b.length - 1].trim()) b.pop();
    if (!b.length) continue;
    /* A block whose only content is the notebook header is not a cell.
       This happened for real: an import wrote the header, a separator, then the query, and the
       header became cell 1 — which then rendered as SQL, was "runnable", and failed at the warehouse
       with a PARSE_SYNTAX_ERROR about '#'. A cell that is only provenance is not executable code. */
    if (b.every((ln) => ln.trim() === "" || ln.trim() === header)) continue;
    cells.push(cellOf(cells.length, b, lang, pre));
    if (cells.length >= MAX_CELLS) break;
  }
  return cells;
}

function cellOf(index: number, block: string[], lang: string, pre: string): Cell {
  const magic = `${pre} MAGIC`;
  const allMagic = block.every((ln) => ln.startsWith(magic) || !ln.trim());
  if (allMagic && block[0].startsWith(magic)) {
    const body = block.map((ln) => (ln.slice(magic.length).startsWith(" ") ? ln.slice(magic.length + 1) : ln.slice(magic.length)));
    const first = (body[0] ?? "").trim();
    if (first.startsWith("%")) {
      const word = (first.slice(1).split(/\s/)[0] ?? "").toLowerCase();
      const rest = [afterMagic(body[0]), ...body.slice(1)].filter((r, i) => i > 0 || r);
      const kind: CellKind = word === "md" ? "markdown" : "code";
      return make(index, kind, MAGICS[word] ?? (word || lang), rest.join("\n"));
    }
    return make(index, "code", lang, body.join("\n"));
  }
  return make(index, "code", lang, block.join("\n"));
}

function make(index: number, kind: CellKind, language: string, source: string): Cell {
  const truncated = source.length > MAX_CELL_CHARS;
  const text = truncated ? source.slice(0, MAX_CELL_CHARS) : source;
  return { id: idAt(index, text), kind, language, source: text, ...(truncated ? { truncated } : {}) };
}

/** The magic a cell needs, or null when it is plain code in the notebook's own language. */
function magicFor(cell: Cell, notebookLanguage: string): string | null {
  if (cell.kind === "markdown") return "md";
  const lang = (cell.language || "").toLowerCase();
  if (!lang || lang === notebookLanguage.toLowerCase()) return null;
  return MAGIC_FOR[lang] ?? null;
}

/** Cells -> SOURCE text. Mirror of the Python, including the trailing-blank MAGIC fallback. */
export function serializeCells(cells: readonly Cell[], language = "PYTHON"): string {
  const pre = prefix(language);
  const lang = (language || "PYTHON").toLowerCase();
  const out: string[] = [`${pre} Databricks notebook source`];

  cells.forEach((cell, i) => {
    if (i) out.push("", `${pre} COMMAND ----------`, "");
    let magic = magicFor(cell, lang);
    // A trailing blank line cannot survive the plain form (the parser trims it), so switch to the
    // MAGIC form, which keeps every line. Same rule as the Python serializer.
    if (magic === null && cell.source.endsWith("\n")) magic = MAGIC_FOR[lang] ?? lang;
    if (magic) {
      const body = cell.source.split("\n");
      out.push(body[0] ? `${pre} MAGIC %${magic} ${body[0]}` : `${pre} MAGIC %${magic}`);
      for (const ln of body.slice(1)) out.push(ln ? `${pre} MAGIC ${ln}` : `${pre} MAGIC`);
    } else {
      out.push(...cell.source.split("\n"));
    }
  });

  return `${out.join("\n")}\n`;
}

/** Would this list survive a save and re-read? Mirrors `check()` in Python by *doing* the trip. */
export function checkCells(cells: readonly Cell[], language = "PYTHON"): string[] {
  const problems: string[] = [];
  if (cells.length > MAX_CELLS) problems.push(`${cells.length} cells, limit ${MAX_CELLS}`);
  cells.forEach((c) => {
    if (c.truncated) problems.push(`cell ${c.id}: truncated, saving would drop the rest`);
    else if (c.source.length > MAX_CELL_CHARS) problems.push(`cell ${c.id}: over ${MAX_CELL_CHARS} characters`);
  });
  if (problems.length) return problems;

  const back = parseCells(serializeCells(cells, language), language);
  if (back.length !== cells.length) {
    return [`${cells.length} cells would be read back as ${back.length}`];
  }
  cells.forEach((before, i) => {
    const after = back[i];
    if (before.kind !== after.kind || before.language !== after.language || before.source !== after.source) {
      problems.push(`cell ${i + 1}: leading or trailing blank lines cannot be written and read back`);
    }
  });
  return problems;
}

/* ---------------------------------------------------------------- cell operations */

let seq = 0;
const nextId = () => `n${Date.now().toString(36)}-${(seq += 1).toString(36)}`;

export function newCell(kind: CellKind, language: string, source = ""): Cell {
  return { id: nextId(), kind, language: kind === "markdown" ? "markdown" : language, source };
}

/** Move by index, preserving every id. The reason ids exist: a move is one operation, not N edits. */
export function moveCell(cells: readonly Cell[], from: number, to: number): Cell[] {
  if (from === to || from < 0 || from >= cells.length) return cells.slice();
  const out = cells.slice();
  const [moved] = out.splice(from, 1);
  out.splice(Math.max(0, Math.min(to, out.length)), 0, moved);
  return out;
}

export function removeCell(cells: readonly Cell[], id: string): Cell[] {
  return cells.filter((c) => c.id !== id);
}

export function insertCell(cells: readonly Cell[], at: number, cell: Cell): Cell[] {
  const out = cells.slice();
  out.splice(Math.max(0, Math.min(at, out.length)), 0, cell);
  return out;
}

/** Change a cell's kind without touching its source (NB-3: the text must be identical on the way
 *  back, so converting twice returns the same cell). */
export function setCellKind(cells: readonly Cell[], id: string, kind: CellKind, language: string): Cell[] {
  return cells.map((c) => (c.id === id
    ? { ...c, kind, language: kind === "markdown" ? "markdown" : language }
    : c));
}

export function updateCellSource(cells: readonly Cell[], id: string, source: string): Cell[] {
  return cells.map((c) => (c.id === id ? { ...c, source } : c));
}
