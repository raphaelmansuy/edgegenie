/** A cell's output, in place under the cell that produced it (spec 006 X2–X4).
 *
 * This is the thing a notebook has and a code list does not: the result lives with the code. Databricks
 * has had it for a decade; before this, ours had nowhere for a result to go and the answer arrived in
 * a different pane.
 *
 * What a cell produced is drawn in the order it produced it (text, tables, plots, HTML), the way
 * Databricks and Jupyter do, and the error comes last, under whatever ran before it failed. Every state
 * is drawn from `domain/cellrun`, so the words and the tone are testable without a DOM.
 */
import { useEffect, useId, useMemo, useRef, useState } from "react";
import {
  badge, drawn, numericColumns, presentRows, showsMessage, summary, toTsv, truncationNote, typeGlyph, whenRan,
  type CellRun, type Output,
} from "../domain/cellrun";
import { canChart, validSpec, type ChartSpec, type TableView } from "../domain/chart";
import { viewOf } from "../domain/values";
import { ChartView } from "./ChartView";
import { FRAME_SANDBOX, frameDoc, frameHeight } from "../domain/htmlframe";
import { Markdown } from "./Markdown";
import { Alert, Check, ChevronDown, ChevronRight, Close, Sparkle } from "./Icons";

function downloadPng(b64: string, name: string) {
  const a = document.createElement("a");
  a.href = `data:image/png;base64,${b64}`;
  a.download = name;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

type TableOut = Extract<Output, { type: "table" }>;

/** One table value. A plain short value is just text. A nested value (array, map, struct) is shown as a
 *  value, and anything long is shortened with Expand and Copy; Copy always takes the whole value. */
function GridValue({ value, typeText }: { value: string; typeText?: string }) {
  const v = useMemo(() => viewOf(value, typeText), [value, typeText]);
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  if (!v.nested && !v.long) return <>{v.text}</>;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(v.copy);
      setNote("Copied");
    } catch {
      setNote("Could not copy");
    }
    window.setTimeout(() => setNote(""), 1600);
  };
  return (
    <span className={`cell-value${v.nested ? " is-nested" : ""}${open ? " is-open" : ""}`} title={typeText || undefined}>
      {open ? <pre className="cell-value-full">{v.full}</pre> : <span className="cell-value-text">{v.long ? v.short : v.text}</span>}
      {v.long && (
        <button type="button" className="cell-value-act" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {open ? "Collapse" : "Expand"}
        </button>
      )}
      {v.long && <button type="button" className="cell-value-act" onClick={() => void copy()} aria-label="Copy this value">Copy</button>}
      {note && <span className="cell-copied" role="status">{note}</span>}
    </span>
  );
}

/** One result table: its own filter, sort and copy, so two `display()` calls do not share a search box. */
function TableOutput({ table, total, label, view, onView }: {
  table: TableOut; total?: number; label: string; view?: TableView; onView?: (v: TableView) => void;
}) {
  const rows = table.rows;
  const cols = table.columns;
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<{ col: number; dir: "asc" | "desc" } | null>(null);
  const [copied, setCopied] = useState("");
  const shown = presentRows(rows, { text: query, sortCol: sort?.col ?? null, sortDir: sort?.dir ?? "asc" });
  const numeric = numericColumns(cols, rows, table.types);
  const chartable = canChart(table);
  const spec = validSpec(table, view?.spec);
  const charting = view?.mode === "chart" && chartable.ok && spec !== null;
  const setView = (mode: TableView["mode"], next?: ChartSpec) => onView?.({ mode, spec: next ?? spec ?? undefined });
  const sortBy = (col: number) => setSort((s) => (
    s?.col === col ? { col, dir: s.dir === "asc" ? "desc" : "asc" } : { col, dir: "asc" }
  ));
  const copy = async () => {
    try {
      // Nested values copy as the values they are shown as, not as the engine's JSON of strings.
      const typed = table.typeTexts?.some(Boolean);
      const rowsOut = typed
        ? shown.map((r) => r.map((v, j) => (v === null || v === undefined ? null : viewOf(v, table.typeTexts?.[j]).copy)))
        : shown;
      await navigator.clipboard.writeText(toTsv(cols, rowsOut));
      setCopied("Copied");
    } catch {
      setCopied("Could not copy");
    }
    window.setTimeout(() => setCopied(""), 1600);
  };

  return (
    <div className="cell-output-grid" aria-label={label}>
      <div className="cell-output-tools">
        {onView && (
          <span className="cell-view-switch" role="group" aria-label="Show as">
            <button type="button" aria-pressed={!charting} onClick={() => setView("table")}>Table</button>
            <button type="button" aria-pressed={charting} disabled={!chartable.ok} title={chartable.ok ? "Show this result as a chart" : chartable.why}
              onClick={() => setView("chart")}>Chart</button>
          </span>
        )}
        {charting ? <span className="cell-filter-n">{rows.length} {rows.length === 1 ? "row" : "rows"}</span> : <input className="cell-filter" aria-label="Filter rows" placeholder="Filter rows"
          value={query} onChange={(e) => setQuery(e.target.value)} />}
        {!charting && <span className="cell-filter-n">{shown.length === rows.length ? `${rows.length}` : `${shown.length} of ${rows.length}`}</span>}
        <button type="button" className="cell-output-act cell-copy" onClick={() => void copy()}
          aria-label="Copy the visible rows">Copy</button>
        {copied && <span className="cell-copied" role="status">{copied}</span>}
      </div>
      {charting && spec ? <ChartView table={table} spec={spec} onSpec={(next) => setView("chart", next)} /> : <div className="grid-wrap">
        <table className="grid">
          <thead><tr>{cols.map((c, j) => {
            const type = table.typeTexts?.[j] || table.types?.[j];
            const glyph = typeGlyph(table.types?.[j]);
            return (
              <th key={j} className={numeric[j] ? "is-num" : ""} title={type ? `${c} · ${type}` : c}
                aria-sort={sort?.col === j ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}>
                <button type="button" className="cell-sort" onClick={() => sortBy(j)}>
                  {glyph && <span className="cell-type" aria-hidden>{glyph}</span>}
                  {c}{sort?.col === j ? (sort.dir === "asc" ? " ↑" : " ↓") : ""}
                </button>
              </th>
            );
          })}</tr></thead>
          <tbody>
            {shown.map((r, i) => (
              <tr key={i}>{cols.map((_, j) => (
                <td key={j} className={numeric[j] ? "is-num" : ""}>
                  {r[j] === null || r[j] === undefined ? <em className="cell-null">null</em>
                    : <GridValue value={r[j] as string} typeText={table.typeTexts?.[j]} />}
                </td>
              ))}</tr>
            ))}
            {shown.length === 0 && (
              <tr><td colSpan={Math.max(1, cols.length)} className="cell-output-empty">
                {rows.length === 0 ? "no rows" : "No rows match"}
              </td></tr>
            )}
          </tbody>
        </table>
      </div>}
      {table.truncated && <p className="cell-output-note">{truncationNote(rows.length, total)}</p>}
    </div>
  );
}

/** HTML a cell produced, in a frame that cannot reach the app (see `domain/htmlframe`). */
function HtmlOutput({ html }: { html: string }) {
  const id = useId();
  const frame = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState(48);
  useEffect(() => {
    const on = (e: MessageEvent) => {
      if (e.source !== frame.current?.contentWindow) return;
      const h = frameHeight(e.data, id);
      if (h !== null) setHeight(h);
    };
    window.addEventListener("message", on);
    return () => window.removeEventListener("message", on);
  }, [id]);
  return (
    <div className="cell-output-html">
      <iframe ref={frame} title="HTML output" sandbox={FRAME_SANDBOX} srcDoc={frameDoc(html, id)}
        style={{ height }} />
    </div>
  );
}

export function CellOutput({ run, onClear, onFix, folded: foldedProp, onToggleFold, onView }: {
  run: CellRun; onClear: () => void; onFix?: () => void;
  /** The person switched a result table between table and chart, or changed the chart. Kept with the run. */
  onView?: (table: number, view: TableView) => void;
  /** When set, the parent owns the fold (command-mode O and this chevron are the same control). */
  folded?: boolean;
  onToggleFold?: () => void;
}) {
  const b = badge(run);
  const [localFold, setLocalFold] = useState(false);
  const folded = foldedProp ?? localFold;
  const toggleFold = () => (onToggleFold ? onToggleFold() : setLocalFold((f) => !f));
  const outputs = drawn(run);
  const tableCount = outputs.filter((o) => o.type === "table").length;
  const imageCount = outputs.filter((o) => o.type === "image").length;
  let tableAt = 0;
  let imageAt = 0;
  const ran = whenRan(run);

  return (
    <div className="cell-output" data-state={run.state}>
      <div className="cell-output-bar">
        <span className={`cell-state tone-${b.tone}`}>
          {run.state === "succeeded" ? <Check size={11} />
            : run.state === "running" ? <span className="spin" aria-hidden />
            : <Alert size={11} />}
          {b.word}
        </span>
        {/* A run in flight has no duration yet: "0ms" beside "running" reads as a frozen counter. */}
        {run.state !== "running" && <span className="cell-output-when">{summary(run)}</span>}
        {ran && <span className="cell-output-by" title={run.finishedAt}>{ran}</span>}
        {run.warehouse && <span className="cell-output-where" title={`Ran on ${run.warehouse}`}>{run.warehouse}</span>}
        <span className="cell-output-spacer" />
        {/* The one action a failure needs. It sends the engine's own words with the cell, so the
            agent starts from the cause instead of asking for it. */}
        {run.state === "failed" && onFix && (
          <button className="cell-fix" onClick={onFix} title="Send this error to the agent and ask for a fix">
            <Sparkle size={11} /> Fix with agent
          </button>
        )}
        <button className="cell-output-act" aria-expanded={!folded} onClick={toggleFold}
          title={folded ? "Show the output" : "Hide the output"} aria-label={folded ? "Show the output" : "Hide the output"}>
          {folded ? <ChevronRight size={11} /> : <ChevronDown size={11} />}
        </button>
        <button className="cell-output-act cell-clear" onClick={onClear} title="Clear this output" aria-label="Clear this output">
          <Close size={11} />
        </button>
      </div>

      {/* A run in flight says what it is waiting for, above the (not yet existing) output. */}
      {!folded && run.state === "running" && showsMessage(run) && (
        <p className="cell-output-msg" role="status">{run.error}</p>
      )}

      {!folded && outputs.map((o, i) => {
        if (o.type === "text") {
          return (
            <pre key={i} className={`cell-output-text is-${o.stream}`}
              aria-label={o.stream === "stderr" ? "Error stream" : o.stream === "notice" ? "Notice" : "Printed output"}>{o.text}</pre>
          );
        }
        if (o.type === "image") {
          // Databricks and Jupyter both put the figure under the cell, in order, with a download control.
          const n = (imageAt += 1);
          return (
            <div key={i} className="cell-output-images" aria-label={imageCount === 1 ? "Plot" : `Plot ${n}`}>
              <figure className="cell-output-figure">
                <img className="cell-output-plot" src={`data:image/png;base64,${o.png}`}
                  alt={imageCount === 1 ? "Plot" : `Plot ${n}`} />
                <button type="button" className="cell-output-dl"
                  title="Download this plot as PNG" aria-label={`Download plot ${n} as PNG`}
                  onClick={() => downloadPng(o.png, imageCount === 1 ? "plot.png" : `plot-${n}.png`)}>
                  Download PNG
                </button>
              </figure>
            </div>
          );
        }
        if (o.type === "html") return <HtmlOutput key={i} html={o.html} />;
        if (o.type === "markdown") return <div key={i} className="cell-output-md" aria-label="Markdown"><Markdown text={o.text} /></div>;
        const n = (tableAt += 1);
        return (
          <TableOutput key={i} table={o} label={tableCount === 1 ? "Result" : `Result ${n}`}
            total={!run.outputs?.length ? run.totalRows : undefined}
            view={run.views?.[String(n - 1)]} onView={onView && run.state !== "running" ? (v) => onView(n - 1, v) : undefined} />
        );
      })}

      {/* The error comes last: Databricks shows what the cell printed, then why it stopped. */}
      {!folded && run.state !== "running" && showsMessage(run) && (
        <p className="cell-output-msg" role={run.state === "failed" ? "alert" : "status"}>{run.error}</p>
      )}
    </div>
  );
}
