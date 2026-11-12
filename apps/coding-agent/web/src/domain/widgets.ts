/**
 * Notebook widgets: the inputs a notebook asks its reader for (`dbutils.widgets`), and the `:name` markers a
 * SQL cell uses. Pure, so the rules are tested without a DOM.
 *
 * Two sources of widgets, one bar:
 *  - DECLARED: a Python cell called `dbutils.widgets.text(...)` and so on. The session reports the set it holds
 *    after every cell, and that set replaces what we had (a `remove` or a restarted session shows).
 *  - IMPLICIT: a SQL cell uses `:name` and nothing declared it. It gets a text box, so a SQL-only notebook can
 *    take a parameter too.
 *
 * Values are the person's. They are kept per notebook, sent with every cell, and never re-run anything by
 * themselves: Databricks re-runs dependent cells on change; here the bar says it does not.
 */

export type WidgetKind = "text" | "dropdown" | "combobox" | "multiselect";

/** A widget as a session reports it. */
export interface Widget {
  name: string;
  type: WidgetKind;
  default: string;
  label: string;
  choices: string[];
  /** The value the session had when it reported. The person's own value (in `values`) wins. */
  value?: string;
}

export interface WidgetState {
  declared: Widget[];
  /** The person's values by widget name. A name with no entry has its default. */
  values: Record<string, string>;
}

export const NO_WIDGETS: WidgetState = { declared: [], values: {} };

export const MAX_VALUE = 2000;

/** The named parameters a SQL statement uses, in order, once each. The same rules as the server's
 *  `sql_params`: a marker is `:name` not after a word character or another colon, and not in a string, a
 *  quoted name or a comment. */
export function sqlParams(sql: string): string[] {
  const names: string[] = [];
  const n = sql.length;
  const isWord = (c: string | undefined) => !!c && /[A-Za-z0-9_]/.test(c);
  let i = 0;
  while (i < n) {
    const c = sql[i];
    if (c === "'" || c === '"' || c === "`") {
      i += 1;
      while (i < n) {
        if (sql[i] === "\\" && c !== "`") { i += 2; continue; }
        if (sql[i] === c) {
          if (sql[i + 1] === c) { i += 2; continue; }
          break;
        }
        i += 1;
      }
      i += 1;
    } else if (sql.startsWith("--", i)) {
      const end = sql.indexOf("\n", i);
      i = end < 0 ? n : end;
    } else if (sql.startsWith("/*", i)) {
      const end = sql.indexOf("*/", i + 2);
      i = end < 0 ? n : end + 2;
    } else if (c === ":" && /[A-Za-z_]/.test(sql[i + 1] ?? "") && !(i > 0 && (isWord(sql[i - 1]) || sql[i - 1] === ":"))) {
      let j = i + 1;
      while (j < n && isWord(sql[j])) j += 1;
      const name = sql.slice(i + 1, j);
      if (!names.includes(name)) names.push(name);
      i = j;
    } else {
      i += 1;
    }
  }
  return names;
}

/** What the bar shows: one input per widget. */
export interface BarItem {
  name: string;
  label: string;
  kind: WidgetKind;
  choices: string[];
  default: string;
  /** True for a `:name` a SQL cell uses that no widget declares. */
  implicit: boolean;
}

interface CellLike { kind?: string; language?: string; source: string }

const isSql = (c: CellLike) => c.kind !== "markdown" && ((c.language ?? "").toLowerCase() === "sql" || /^\s*%sql\b/i.test(c.source));

export function barItems(declared: readonly Widget[], cells: readonly CellLike[]): BarItem[] {
  const items: BarItem[] = declared.map((w) => ({
    name: w.name, label: w.label || w.name, kind: w.type, choices: w.choices, default: w.default, implicit: false,
  }));
  const known = new Set(items.map((i) => i.name));
  for (const cell of cells) {
    if (!isSql(cell)) continue;
    for (const name of sqlParams(cell.source)) {
      if (known.has(name)) continue;
      known.add(name);
      items.push({ name, label: name, kind: "text", choices: [], default: "", implicit: true });
    }
  }
  return items;
}

const pieces = (v: string) => v.split(",").filter(Boolean);

/** The value a widget has: the person's if it is one the widget allows, else its default. The same rule the
 *  session applies, so what the bar shows is what `get` returns. */
export function valueOf(item: BarItem, values: Record<string, string>): string {
  const v = values[item.name];
  if (v === undefined) return item.default;
  if (item.kind === "dropdown") return item.choices.includes(v) ? v : item.default;
  if (item.kind === "multiselect") return pieces(v).every((p) => item.choices.includes(p)) ? v : item.default;
  return v.slice(0, MAX_VALUE);
}

/** The values to send for a SQL cell: only the markers it uses that have a widget behind them. */
export function paramsFor(source: string, items: readonly BarItem[], values: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const name of sqlParams(source)) {
    const item = items.find((i) => i.name === name);
    if (item) out[name] = valueOf(item, values);
  }
  return out;
}

/** The values to send with a Python cell: every declared widget's, so `get` sees what the bar shows. */
export function valuesForSession(declared: readonly Widget[], values: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const w of declared) {
    out[w.name] = valueOf({ name: w.name, label: w.label, kind: w.type, choices: w.choices, default: w.default, implicit: false }, values);
  }
  return out;
}

/** The set a session reported replaces the declared set. A run that did not report (SQL, one-shot) changes nothing. */
export function applyReport(state: WidgetState, reported: readonly Widget[] | undefined): WidgetState {
  return reported === undefined ? state : { ...state, declared: [...reported] };
}

export function setValue(state: WidgetState, name: string, value: string): WidgetState {
  return { ...state, values: { ...state.values, [name]: value.slice(0, MAX_VALUE) } };
}

/** Back to the defaults: forget every value the person set. */
export function resetValues(state: WidgetState): WidgetState {
  return { ...state, values: {} };
}

/** Choose or unchoose one option of a multiselect; the value stays in the widget's own order. */
export function toggleChoice(item: BarItem, current: string, choice: string): string {
  const on = new Set(pieces(current));
  if (on.has(choice)) on.delete(choice); else on.add(choice);
  return item.choices.filter((c) => on.has(c)).join(",");
}

/* ---- keeping them per notebook ---------------------------------------------------------------- */

export const KEY = "coding-agent:widgets:v1:";

export function load(path: string, storage: Pick<Storage, "getItem"> = localStorage): WidgetState {
  try {
    const raw = JSON.parse(storage.getItem(KEY + path) ?? "null") as Partial<WidgetState> | null;
    if (!raw || typeof raw !== "object") return NO_WIDGETS;
    const declared = Array.isArray(raw.declared) ? raw.declared.filter(valid) : [];
    const values: Record<string, string> = {};
    for (const [k, v] of Object.entries(raw.values ?? {})) if (typeof v === "string") values[k] = v.slice(0, MAX_VALUE);
    return { declared, values };
  } catch {
    return NO_WIDGETS;
  }
}

export function save(path: string, state: WidgetState, storage: Pick<Storage, "setItem" | "removeItem"> = localStorage): void {
  try {
    if (state.declared.length === 0 && Object.keys(state.values).length === 0) storage.removeItem(KEY + path);
    else storage.setItem(KEY + path, JSON.stringify(state));
  } catch {
    /* storage full or blocked: the widgets still work for this visit */
  }
}

function valid(w: unknown): w is Widget {
  const x = w as Widget;
  return !!x && typeof x.name === "string" && typeof x.default === "string" && Array.isArray(x.choices)
    && ["text", "dropdown", "combobox", "multiselect"].includes(x.type);
}
