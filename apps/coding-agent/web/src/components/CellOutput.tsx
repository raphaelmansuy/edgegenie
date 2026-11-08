/** A cell's output, in place under the cell that produced it (spec 006 X2–X4).
 *
 * This is the thing a notebook has and a code list does not: the result lives with the code. Databricks
 * has had it for a decade; before this, ours had nowhere for a result to go and the answer arrived in
 * a different pane.
 *
 * Every state is drawn from `domain/cellrun`, so the words and the tone are testable without a DOM.
 */
import { useState } from "react";
import { badge, showsMessage, showsOutput, showsTable, summary, type CellRun } from "../domain/cellrun";
import { Alert, Check, ChevronDown, ChevronRight, Close, Sparkle } from "./Icons";

export function CellOutput({ run, onClear, onFix }: { run: CellRun; onClear: () => void; onFix?: () => void }) {
  const b = badge(run);
  const [folded, setFolded] = useState(false);
  const rows = run.rows ?? [];
  const cols = run.columns ?? [];

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
        {run.warehouse && <span className="cell-output-where" title={`Ran on ${run.warehouse}`}>{run.warehouse}</span>}
        <span className="cell-output-spacer" />
        {/* The one action a failure needs. It sends the engine's own words with the cell, so the
            agent starts from the cause instead of asking for it. */}
        {run.state === "failed" && onFix && (
          <button className="cell-fix" onClick={onFix} title="Send this error to the agent and ask for a fix">
            <Sparkle size={11} /> Fix with agent
          </button>
        )}
        <button className="cell-output-act" aria-expanded={!folded} onClick={() => setFolded((f) => !f)}
          title={folded ? "Show the output" : "Hide the output"} aria-label={folded ? "Show the output" : "Hide the output"}>
          {folded ? <ChevronRight size={11} /> : <ChevronDown size={11} />}
        </button>
        <button className="cell-output-act cell-clear" onClick={onClear} title="Clear this output" aria-label="Clear this output">
          <Close size={11} />
        </button>
      </div>

      {!folded && showsMessage(run) && (
        <p className="cell-output-msg" role={run.state === "failed" ? "alert" : "status"}>{run.error}</p>
      )}

      {!folded && showsOutput(run) && <pre className="cell-output-text" aria-label="Printed output">{run.output}</pre>}

      {!folded && showsTable(run) && (
        <div className="grid-wrap cell-output-grid">
          <table className="grid">
            <thead><tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>{cols.map((_, j) => (
                  <td key={j} className={r[j] !== null && r[j] !== "" && /^-?[\d.,]+$/.test(String(r[j])) ? "num" : ""}>
                    {r[j] === "" || r[j] === null ? <em>null</em> : r[j]}
                  </td>
                ))}</tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan={Math.max(1, cols.length)} className="cell-output-empty">no rows</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
