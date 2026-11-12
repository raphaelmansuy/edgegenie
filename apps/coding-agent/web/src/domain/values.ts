/**
 * Nested values (array, map, struct) and long values, shown the way Databricks shows them.
 *
 * The SQL API sends a nested value as JSON text in which EVERY leaf is a string: `["1","2"]` for an
 * `ARRAY<INT>`. Shown as it came, that reads as an array of strings. The column's type text says what the
 * leaves are, so the numbers are drawn as numbers: `[1,2]`. A Python table carries real numbers already and
 * the same code draws it. Without a type text a value is left exactly as it came: guessing which strings are
 * numbers would be wrong for `ARRAY<STRING>` holding "1".
 *
 * Numbers are never reformatted beyond that. A decimal keeps its scale (`1.50`), a bigint its digits.
 */

export type SqlType =
  | { k: "array"; of: SqlType }
  | { k: "map"; key: SqlType; value: SqlType }
  | { k: "struct"; fields: { name: string; type: SqlType }[] }
  | { k: "leaf"; name: string };

const MAX_DEPTH = 12;

/** `ARRAY<INT>`, `MAP<STRING, INT>`, `STRUCT<x: INT NOT NULL, y: STRING>`, or Spark's `struct<x:int,y:string>`.
 *  Null when the text is not a type this understands: the value is then shown as it came. */
export function parseType(text: string | undefined): SqlType | null {
  if (!text) return null;
  let i = 0;
  const s = text.trim();
  const ws = () => { while (i < s.length && /\s/.test(s[i])) i += 1; };
  const eat = (c: string) => { ws(); if (s[i] === c) { i += 1; return true; } return false; };
  const word = (): string => {
    ws();
    if (s[i] === "`") {
      const end = s.indexOf("`", i + 1);
      if (end < 0) throw new Error("open quote");
      const w = s.slice(i + 1, end);
      i = end + 1;
      return w;
    }
    const m = /^[A-Za-z_][\w$]*/.exec(s.slice(i));
    if (!m) throw new Error("expected a name");
    i += m[0].length;
    return m[0];
  };
  const suffixes = () => {            // NOT NULL, COMMENT '...' after a struct field
    for (;;) {
      ws();
      const m = /^(NOT\s+NULL|COMMENT\s+'(?:[^']|'')*')/i.exec(s.slice(i));
      if (!m) return;
      i += m[0].length;
    }
  };
  const type = (depth: number): SqlType => {
    if (depth > MAX_DEPTH) throw new Error("too deep");
    const name = word().toLowerCase();
    if (name === "array") {
      if (!eat("<")) throw new Error("expected <");
      const of = type(depth + 1);
      if (!eat(">")) throw new Error("expected >");
      return { k: "array", of };
    }
    if (name === "map") {
      if (!eat("<")) throw new Error("expected <");
      const key = type(depth + 1);
      if (!eat(",")) throw new Error("expected ,");
      const value = type(depth + 1);
      if (!eat(">")) throw new Error("expected >");
      return { k: "map", key, value };
    }
    if (name === "struct") {
      if (!eat("<")) throw new Error("expected <");
      const fields: { name: string; type: SqlType }[] = [];
      if (!eat(">")) {
        do {
          const fieldName = word();
          if (!eat(":")) throw new Error("expected :");
          const t = type(depth + 1);
          suffixes();
          fields.push({ name: fieldName, type: t });
        } while (eat(","));
        if (!eat(">")) throw new Error("expected >");
      }
      return { k: "struct", fields };
    }
    if (eat("(")) {                    // DECIMAL(5,2), VARCHAR(10)
      while (i < s.length && s[i] !== ")") i += 1;
      if (!eat(")")) throw new Error("expected )");
    }
    return { k: "leaf", name };
  };
  try {
    const t = type(0);
    ws();
    return i === s.length ? t : null;
  } catch {
    return null;
  }
}

const BARE = new Set([
  "tinyint", "smallint", "int", "integer", "bigint", "long", "short", "byte", "float", "double", "real",
  "decimal", "dec", "numeric", "boolean", "bool",
]);

export const isNested = (type: SqlType | null): type is Exclude<SqlType, { k: "leaf" }> => !!type && type.k !== "leaf";

function write(node: unknown, type: SqlType, pretty: boolean, depth: number): string {
  if (node === null || node === undefined) return "null";
  const nl = (d: number) => (pretty ? `\n${"  ".repeat(d)}` : "");
  const items = (parts: string[], open: string, close: string) =>
    parts.length === 0 ? `${open}${close}` : `${open}${nl(depth + 1)}${parts.join(`,${nl(depth + 1)}`)}${nl(depth)}${close}`;
  if (type.k === "array") {
    if (!Array.isArray(node)) return JSON.stringify(node);
    return items(node.map((x) => write(x, type.of, pretty, depth + 1)), "[", "]");
  }
  if (type.k === "map") {
    if (typeof node !== "object" || Array.isArray(node)) return JSON.stringify(node);
    return items(Object.entries(node as Record<string, unknown>)
      .map(([k, v]) => `${JSON.stringify(k)}:${pretty ? " " : ""}${write(v, type.value, pretty, depth + 1)}`), "{", "}");
  }
  if (type.k === "struct") {
    if (typeof node !== "object" || Array.isArray(node)) return JSON.stringify(node);
    const o = node as Record<string, unknown>;
    return items(type.fields.map((f) => `${JSON.stringify(f.name)}:${pretty ? " " : ""}${write(o[f.name], f.type, pretty, depth + 1)}`), "{", "}");
  }
  if (typeof node === "object") return JSON.stringify(node);
  return BARE.has(type.name) ? String(node) : JSON.stringify(String(node));
}

/** The value as a typed nested value, or null when it is not one this can read (then show it as it came).
 *  `pretty` breaks it over lines, for the expanded view. */
export function formatNested(raw: string, typeText: string | undefined, pretty = false): string | null {
  const type = parseType(typeText);
  if (!isNested(type)) return null;
  let node: unknown;
  try {
    node = JSON.parse(raw);
  } catch {
    return null;
  }
  return write(node, type, pretty, 0);
}

export const LONG_VALUE = 120;

export interface CellView {
  /** What the cell shows, before any shortening. */
  text: string;
  /** What Copy puts on the clipboard. */
  copy: string;
  /** The expanded form: nested values broken over lines. */
  full: string;
  nested: boolean;
  /** Longer than a cell should hold: it is shortened, with Expand and Copy. */
  long: boolean;
  /** The shortened text, when long. */
  short: string;
}

export function viewOf(raw: string, typeText?: string): CellView {
  const nested = formatNested(raw, typeText);
  const text = nested ?? raw;
  const long = text.length > LONG_VALUE;
  return {
    text, copy: text, nested: nested !== null,
    full: nested !== null ? formatNested(raw, typeText, true) ?? nested : raw,
    long, short: long ? `${text.slice(0, LONG_VALUE).trimEnd()}…` : text,
  };
}
